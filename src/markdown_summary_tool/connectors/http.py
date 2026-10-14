"""HTTP connector — fetches url-kind DataRefs via httpx with pagination."""

from __future__ import annotations

import csv
import io
import json
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from markdown_summary_tool.connectors.base import Connector, ConnectorError


def _merge_query_param(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    qs[key] = [value]
    new_query = urlencode({k: v[0] if len(v) == 1 else v for k, v in qs.items()}, doseq=False)
    return urlunparse(parsed._replace(query=new_query))


class HttpConnector(Connector):
    """Connector for ``url`` DataRefs.

    Follows ``Link: <...>; rel="next"`` pagination and common JSON body
    cursor/offset/page_token patterns.  Handles both JSON and CSV
    content-types.
    """

    def __init__(
        self,
        data_ref: Any,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        if isinstance(data_ref, dict):
            self.url: str = data_ref.get("url") or ""
            self.options: dict[str, Any] = data_ref.get("options") or {}
            self.name: str = data_ref.get("name", "url")
        else:
            self.url = getattr(data_ref, "url", "") or ""
            self.options = getattr(data_ref, "options", None) or {}
            self.name = getattr(data_ref, "name", "url")
        self._client = client
        self._timeout = timeout
        if not self.url:
            raise ConnectorError("HttpConnector requires a url")

    async def fetch(self) -> list[dict[str, Any]]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout, follow_redirects=True)
        try:
            return await self._fetch_paginated(client)
        finally:
            if owns_client:
                await client.aclose()

    async def _fetch_paginated(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        url: str | None = self.url
        page_count = 0
        pagination_param: str = self.options.get("pagination_param") or "cursor"
        dedup_key: str | None = self.options.get("dedup_key")

        while url is not None:
            page_count += 1
            self.check_page_guard(page_count)

            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise ConnectorError(f"HTTP {exc.response.status_code} fetching '{self.name}': {url}") from exc
            except httpx.RequestError as exc:
                raise ConnectorError(f"request failed for '{self.name}': {exc}") from exc

            content_type = resp.headers.get("content-type", "").lower()
            rows, body_for_pagination = self._parse_response(resp, content_type)
            all_rows.extend(rows)
            self.check_row_guard(len(all_rows))

            # Determine next page
            next_token = self._next_token(resp, body_for_pagination)
            if next_token is None:
                break
            # If token looks like a full URL, use it directly
            if next_token.startswith("http://") or next_token.startswith("https://"):
                url = next_token
            else:
                url = _merge_query_param(self.url if page_count == 1 else url, pagination_param, next_token)
                # For subsequent pages, build from current url
                # Re-parse to avoid stacking params incorrectly — use current url as base
                # Actually use the last url as base for next iteration
                # We already set url above; on next loop it will be fetched

            # Safety: if next_token equals current url param value, avoid infinite loop
            # (handled by page guard, but break early if no progress)
            if page_count > 1 and url == self.url:
                break

        if dedup_key or self.options.get("dedup"):
            all_rows = self.dedup(all_rows, dedup_key)
        return all_rows

    # -- response parsing ------------------------------------------------

    def _parse_response(
        self, resp: httpx.Response, content_type: str
    ) -> tuple[list[dict[str, Any]], Any]:
        if "text/csv" in content_type or "application/csv" in content_type:
            return self._parse_csv_body(resp.text), None
        # Try JSON first for json content-type or when body looks like JSON
        text = resp.text.strip()
        if not text:
            return [], None
        # Heuristic: if content-type says json, parse as json
        if "json" in content_type:
            return self._parse_json_body(text), self._json_for_pagination(text)
        # Auto-detect: try JSON, fall back to CSV
        if text[:1] in ("{", "["):
            try:
                return self._parse_json_body(text), self._json_for_pagination(text)
            except ConnectorError:
                pass
        # Fallback: CSV
        try:
            return self._parse_csv_body(text), None
        except Exception:
            # Last resort: try JSON again and surface error
            return self._parse_json_body(text), self._json_for_pagination(text)

    def _parse_json_body(self, text: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConnectorError(f"invalid JSON response for '{self.name}': {exc}") from exc
        # Common envelope patterns: {data: [...]} or {rows: [...]} or {items: [...]} or {results: [...]}
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            for key in ("data", "rows", "items", "results", "records"):
                if key in data and isinstance(data[key], list):
                    rows = data[key]
                    break
            else:
                # Single object
                rows = [data]
        else:
            raise ConnectorError(f"unexpected JSON shape for '{self.name}'")
        result: list[dict[str, Any]] = []
        for item in rows:
            if isinstance(item, dict):
                result.append(dict(item))
        return result

    @staticmethod
    def _json_for_pagination(text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return None

    def _parse_csv_body(self, text: str) -> list[dict[str, Any]]:
        delimiter: str = self.options.get("delimiter") or ","
        if delimiter == "\\t":
            delimiter = "\t"
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if reader.fieldnames is None:
            return []
        return [dict(r) for r in reader]

    def _next_token(self, resp: httpx.Response, body: Any) -> str | None:
        # 1. Link header
        link = resp.headers.get("Link") or resp.headers.get("link") or ""
        if link:
            for part in link.split(","):
                if 'rel="next"' in part or "rel='next'" in part:
                    s = part.find("<")
                    e = part.find(">", s)
                    if s != -1 and e != -1:
                        return part[s + 1 : e].strip()
        # 2. Body pagination
        if isinstance(body, dict):
            token = self.extract_pagination_token(body, dict(resp.headers))
            # extract_pagination_token already checks Link header, but we
            # want body-only here to avoid double-counting; still fine
            if token and token.startswith("http"):
                return token
            if token:
                # token might be a cursor value, not a URL
                # Only return if it differs from what we already handled
                # Check if Link header already gave us a URL — prefer Link
                if link and 'rel="next"' in link:
                    return None  # already handled
                return token
        return None
