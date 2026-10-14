"""Connector registry — register custom connectors per repo.

Usage:
    from repo_adapter.connectors import ConnectorRegistry, BaseRepoConnector

    registry = ConnectorRegistry()
    registry.register("my_db", MyDBConnector)

    # In pipeline:
    connector = registry.get(kind, data_ref)
    rows = await connector.fetch()
"""

from __future__ import annotations

from typing import Any

from markdown_summary_tool.connectors.base import Connector, ConnectorError


class BaseRepoConnector(Connector):
    """Base for repo-specific connectors. Subclass and implement fetch()."""

    def __init__(self, data_ref: Any) -> None:
        if isinstance(data_ref, dict):
            self.data_ref = data_ref
            self.name = data_ref.get("name", "dataset")
            self.options = data_ref.get("options") or {}
        else:
            self.data_ref = data_ref
            self.name = getattr(data_ref, "name", "dataset")
            self.options = getattr(data_ref, "options", None) or {}

    async def fetch(self) -> list[dict[str, Any]]:
        raise NotImplementedError


class ConnectorRegistry:
    """Registry mapping kind -> Connector class."""

    def __init__(self) -> None:
        self._registry: dict[str, type[Connector]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        from markdown_summary_tool.connectors.http import HttpConnector
        from markdown_summary_tool.connectors.inline import InlineConnector
        self._registry["inline_json"] = InlineConnector
        self._registry["inline_csv"] = InlineConnector
        self._registry["url"] = HttpConnector

    def register(self, kind: str, connector_cls: type[Connector]) -> None:
        self._registry[kind] = connector_cls

    def get(self, kind: str, data_ref: Any) -> Connector:
        cls = self._registry.get(kind)
        if cls is None:
            raise ConnectorError(f"Unknown connector kind '{kind}'. Registered: {list(self._registry)}")
        return cls(data_ref)

    def kinds(self) -> list[str]:
        return list(self._registry.keys())

    def describe(self) -> dict[str, str]:
        return {k: v.__name__ for k, v in self._registry.items()}
