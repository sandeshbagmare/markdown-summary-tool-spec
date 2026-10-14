"""Abstract connector with pagination, dedup, and row/page guards."""

from __future__ import annotations

import abc
from typing import Any


class ConnectorError(RuntimeError):
    pass


class Connector(abc.ABC):
    """Base for all dataset connectors.

    Subclasses implement :meth:`fetch` which must return ``list[dict]``.
    Helpers enforce the global guards required by the spec:
    * at most 1000 pages per fetch
    * at most 10M rows total
    """

    MAX_PAGES: int = 1000
    MAX_ROWS: int = 10_000_000

    @abc.abstractmethod
    async def fetch(self) -> list[dict[str, Any]]:
        """Fetch all rows for the dataset."""

    # -- helpers for subclasses ------------------------------------------

    @staticmethod
    def dedup(rows: list[dict[str, Any]], key: str | None = None) -> list[dict[str, Any]]:
        """Deduplicate rows.

        If *key* is given, rows with duplicate values for that key are
        collapsed (first occurrence wins).  Otherwise rows are deduped by
        full-content equality.
        """
        if not rows:
            return rows
        if key is not None:
            seen: set[Any] = set()
            out: list[dict[str, Any]] = []
            for r in rows:
                k = r.get(key)
                # None keys are not deduped — they are considered distinct
                if k is None:
                    out.append(r)
                    continue
                if k not in seen:
                    seen.add(k)
                    out.append(r)
            return out
        # full-row dedup
        seen_tuples: set[str] = set()
        out2: list[dict[str, Any]] = []
        for r in rows:
            token = str(sorted(r.items()))
            if token not in seen_tuples:
                seen_tuples.add(token)
                out2.append(r)
        return out2

    @classmethod
    def check_page_guard(cls, page_count: int) -> None:
        if page_count > cls.MAX_PAGES:
            raise ConnectorError(f"pagination exceeded {cls.MAX_PAGES} pages (got {page_count})")

    @classmethod
    def check_row_guard(cls, row_count: int) -> None:
        if row_count > cls.MAX_ROWS:
            raise ConnectorError(f"dataset exceeded {cls.MAX_ROWS} rows (got {row_count})")

    @staticmethod
    def extract_pagination_token(
        body: dict[str, Any] | list[Any],
        headers: dict[str, str] | None = None,
    ) -> str | None:
        """Try to extract a next-page token from common pagination patterns.

        Checks (in order):
        1. ``Link`` header with ``rel="next"``
        2. Body keys: ``next_cursor``, ``next_page_token``, ``cursor``, ``offset``, ``next``
        """
        if headers:
            link = headers.get("Link") or headers.get("link") or ""
            if link:
                # Link: <https://...?cursor=abc>; rel="next"
                for part in link.split(","):
                    if 'rel="next"' in part or "rel='next'" in part:
                        start = part.find("<")
                        end = part.find(">", start)
                        if start != -1 and end != -1:
                            return part[start + 1 : end].strip()
        if isinstance(body, dict):
            for k in ("next_cursor", "next_page_token", "page_token", "cursor", "next", "offset"):
                v = body.get(k)
                if v is not None and str(v).strip() != "":
                    return str(v)
            # nested pagination object
            pagination = body.get("pagination")
            if isinstance(pagination, dict):
                for k in ("next_cursor", "next_page_token", "cursor", "next"):
                    v = pagination.get(k)
                    if v:
                        return str(v)
        return None
