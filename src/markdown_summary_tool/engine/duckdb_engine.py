"""DuckDB in-memory engine — registers DataFrames, runs SQL push-down."""

from __future__ import annotations

import re
from typing import Any

import duckdb
import pandas as pd


_SAFE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_table_name(name: str) -> str:
    if _SAFE_NAME_RE.match(name):
        return name
    # Quote as identifier
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


class DuckDBEngine:
    """In-memory DuckDB engine with DataFrame registration and SQL push-down.

    All numeric facts are computed via SQL over the full registered data
    (never sampling for final numbers).
    """

    def __init__(self) -> None:
        self._con = duckdb.connect(":memory:")
        self._tables: set[str] = set()
        self._closed = False

    # -- registration ----------------------------------------------------

    def register(self, name: str, rows: list[dict[str, Any]]) -> None:
        """Register *rows* under table *name*.

        Re-registering the same name replaces the previous table.
        Empty *rows* creates an empty table with no columns (queries
        should handle this gracefully).
        """
        self._ensure_open()
        safe = _safe_table_name(name)
        # Drop existing
        if name in self._tables:
            self._con.execute(f"DROP TABLE IF EXISTS {safe}")
            self._tables.discard(name)
        if not rows:
            # Create empty table with a dummy column so queries don't fail on missing table
            self._con.execute(f"CREATE TABLE {safe} (\"__empty\" INTEGER)")
            # Delete the dummy column's implicit row — keep table empty
            self._tables.add(name)
            return
        df = pd.DataFrame(rows)
        # Register via temporary view then persist as table for SQL access
        self._con.register(f"__tmp_{name}", df)
        self._con.execute(f"CREATE TABLE {safe} AS SELECT * FROM \"__tmp_{name}\"")
        self._con.unregister(f"__tmp_{name}")
        self._tables.add(name)

    # -- query -----------------------------------------------------------

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Execute *sql* and return rows as ``list[dict]``."""
        self._ensure_open()
        try:
            result = self._con.execute(sql)
            cols = [d[0] for d in result.description] if result.description else []
            rows = result.fetchall()
            return [dict(zip(cols, r)) for r in rows]
        except duckdb.Error as exc:
            raise RuntimeError(f"DuckDB query failed: {exc}\nSQL: {sql}") from exc

    def query_scalar(self, sql: str) -> Any:
        """Execute *sql* expected to return a single scalar value."""
        rows = self.query(sql)
        if not rows:
            return None
        first_row = rows[0]
        if not first_row:
            return None
        return next(iter(first_row.values()))

    # -- aggregate helpers (all via SQL push-down) -----------------------

    def count(self, table: str, where: str | None = None) -> int:
        safe = _safe_table_name(table)
        sql = f"SELECT COUNT(*) AS cnt FROM {safe}"
        if where:
            sql += f" WHERE {where}"
        val = self.query_scalar(sql)
        return int(val) if val is not None else 0

    def sum(self, table: str, column: str, where: str | None = None) -> float | None:
        safe = _safe_table_name(table)
        col = _safe_table_name(column)
        sql = f"SELECT SUM({col}) AS v FROM {safe}"
        if where:
            sql += f" WHERE {where}"
        val = self.query_scalar(sql)
        return float(val) if val is not None else None

    def avg(self, table: str, column: str, where: str | None = None) -> float | None:
        safe = _safe_table_name(table)
        col = _safe_table_name(column)
        sql = f"SELECT AVG({col}) AS v FROM {safe}"
        if where:
            sql += f" WHERE {where}"
        val = self.query_scalar(sql)
        return float(val) if val is not None else None

    def min(self, table: str, column: str, where: str | None = None) -> Any:
        safe = _safe_table_name(table)
        col = _safe_table_name(column)
        sql = f"SELECT MIN({col}) AS v FROM {safe}"
        if where:
            sql += f" WHERE {where}"
        return self.query_scalar(sql)

    def max(self, table: str, column: str, where: str | None = None) -> Any:
        safe = _safe_table_name(table)
        col = _safe_table_name(column)
        sql = f"SELECT MAX({col}) AS v FROM {safe}"
        if where:
            sql += f" WHERE {where}"
        return self.query_scalar(sql)

    def group_by(
        self,
        table: str,
        by: str | list[str],
        agg: str = "COUNT(*) AS cnt",
        order_by: str | None = None,
        limit: int | None = None,
        where: str | None = None,
    ) -> list[dict[str, Any]]:
        safe = _safe_table_name(table)
        if isinstance(by, str):
            by = [by]
        by_cols = ", ".join(_safe_table_name(c) for c in by)
        sql = f"SELECT {by_cols}, {agg} FROM {safe}"
        if where:
            sql += f" WHERE {where}"
        sql += f" GROUP BY {by_cols}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {limit}"
        return self.query(sql)

    # -- lifecycle -------------------------------------------------------

    def close(self) -> None:
        if not self._closed:
            try:
                self._con.close()
            except Exception:
                pass
            self._closed = True

    def __enter__(self) -> DuckDBEngine:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("DuckDBEngine is closed")
