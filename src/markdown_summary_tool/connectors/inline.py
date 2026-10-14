"""Inline connector — parses inline_json / inline_csv DataRefs into rows."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from markdown_summary_tool.connectors.base import Connector, ConnectorError


class InlineConnector(Connector):
    """Connector for ``inline_json`` and ``inline_csv`` DataRefs.

    Parameters
    ----------
    data_ref:
        A ``DataRef``-like mapping with ``kind``, ``data``, and ``options``.
        Accepts either a ``DataRef`` instance or a plain dict.
    """

    def __init__(self, data_ref: Any) -> None:
        if isinstance(data_ref, dict):
            self.kind: str = data_ref.get("kind", "")
            self.data: Any = data_ref.get("data")
            self.options: dict[str, Any] = data_ref.get("options") or {}
            self.name: str = data_ref.get("name", "inline")
        else:
            self.kind = getattr(data_ref, "kind", "")
            self.data = getattr(data_ref, "data", None)
            self.options = getattr(data_ref, "options", None) or {}
            self.name = getattr(data_ref, "name", "inline")

    async def fetch(self) -> list[dict[str, Any]]:
        if self.kind == "inline_json":
            return self._parse_json()
        if self.kind == "inline_csv":
            return self._parse_csv()
        raise ConnectorError(f"InlineConnector does not support kind '{self.kind}'")

    # -- parsers ---------------------------------------------------------

    def _parse_json(self) -> list[dict[str, Any]]:
        raw = self.data
        # data may already be a list/dict or a JSON string
        if isinstance(raw, str):
            raw = raw.strip()
            if not raw:
                return []
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ConnectorError(f"invalid JSON for dataset '{self.name}': {exc}") from exc
        if raw is None:
            return []
        if isinstance(raw, dict):
            # single object -> wrap
            raw = [raw]
        if not isinstance(raw, list):
            raise ConnectorError(f"inline_json data for '{self.name}' must be a JSON array or object")
        rows: list[dict[str, Any]] = []
        for i, item in enumerate(raw):
            if not isinstance(item, dict):
                raise ConnectorError(f"inline_json row {i} in '{self.name}' is not an object")
            rows.append(dict(item))
        self.check_row_guard(len(rows))
        dedup_key: str | None = self.options.get("dedup_key")
        if dedup_key or self.options.get("dedup"):
            rows = self.dedup(rows, dedup_key)
        return rows

    def _parse_csv(self) -> list[dict[str, Any]]:
        raw = self.data
        if raw is None:
            return []
        if not isinstance(raw, str):
            raise ConnectorError(f"inline_csv data for '{self.name}' must be a string")
        text = raw.strip()
        if not text:
            return []
        delimiter: str = self.options.get("delimiter") or self.options.get("sep") or ","
        # handle escaped tab
        if delimiter == "\\t":
            delimiter = "\t"
        try:
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            if reader.fieldnames is None:
                return []
            rows = [dict(r) for r in reader]
        except Exception as exc:
            raise ConnectorError(f"CSV parse error for '{self.name}': {exc}") from exc
        self.check_row_guard(len(rows))
        dedup_key = self.options.get("dedup_key")
        if dedup_key or self.options.get("dedup"):
            rows = self.dedup(rows, dedup_key)
        return rows
