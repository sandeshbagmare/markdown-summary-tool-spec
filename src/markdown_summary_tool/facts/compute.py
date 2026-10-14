"""Fact computation — executes FactSpecs via DuckDBEngine and formats results."""

from __future__ import annotations

import locale
from typing import Any

from markdown_summary_tool.facts.planner import FactSpec


def _format_value(value: Any, kind: str) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        # Use 2 decimal places for avg/sum, strip trailing zeros otherwise
        if kind in ("avg", "sum"):
            return f"{value:,.2f}"
        # For other kinds, show up to 6 significant digits
        return f"{value:,.6g}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def compute_facts(
    engine: Any,
    fact_specs: list[FactSpec],
    *,
    locale_str: str = "en-US",
) -> list[dict[str, Any]]:
    """Execute each FactSpec via *engine* and return list of Fact dicts.

    Each returned dict matches the ``Fact`` schema (id, kind, value,
    formatted, provenance, tolerance).
    """
    facts: list[dict[str, Any]] = []

    for spec in fact_specs:
        try:
            rows = engine.query(spec.sql)
        except Exception as exc:
            facts.append(
                {
                    "id": spec.id,
                    "kind": spec.kind,
                    "value": str(exc),
                    "formatted": "error",
                    "provenance": {"sql": spec.sql, "description": spec.description, "error": str(exc)},
                    "tolerance": spec.tolerance,
                }
            )
            continue

        if not rows:
            facts.append(
                {
                    "id": spec.id,
                    "kind": spec.kind,
                    "value": 0,
                    "formatted": _format_value(0, spec.kind),
                    "provenance": {"sql": spec.sql, "description": spec.description},
                    "tolerance": spec.tolerance,
                }
            )
            continue

        # Group/topk specs return multiple rows — emit one fact per group row
        if spec.kind in ("group_count", "topk"):
            for idx, row in enumerate(rows):
                grp = row.get("grp")
                val = row.get("value")
                facts.append(
                    {
                        "id": f"{spec.id}__{idx}",
                        "kind": spec.kind,
                        "value": val if isinstance(val, (int, float)) else str(val) if val is not None else 0,
                        "formatted": _format_value(val, spec.kind),
                        "provenance": {
                            "sql": spec.sql,
                            "description": spec.description,
                            "group": str(grp) if grp is not None else None,
                        },
                        "tolerance": spec.tolerance,
                    }
                )
            if not rows:
                facts.append(
                    {
                        "id": spec.id,
                        "kind": spec.kind,
                        "value": 0,
                        "formatted": "—",
                        "provenance": {"sql": spec.sql, "description": spec.description},
                        "tolerance": spec.tolerance,
                    }
                )
            continue

        # Scalar specs: single value
        first = rows[0]
        # Value is in "value" column, or first column
        if "value" in first:
            raw = first["value"]
        else:
            raw = next(iter(first.values()), None)

        # Normalize numeric types
        if isinstance(raw, (int, float)) and raw is not None:
            value: Any = raw
        elif raw is None:
            value = 0 if spec.kind == "count" else None
            if value is None:
                facts.append(
                    {
                        "id": spec.id,
                        "kind": spec.kind,
                        "value": "",
                        "formatted": "—",
                        "provenance": {"sql": spec.sql, "description": spec.description},
                        "tolerance": spec.tolerance,
                    }
                )
                continue
        else:
            value = raw

        facts.append(
            {
                "id": spec.id,
                "kind": spec.kind,
                "value": value,
                "formatted": _format_value(value, spec.kind),
                "provenance": {"sql": spec.sql, "description": spec.description},
                "tolerance": spec.tolerance,
            }
        )

    return facts
