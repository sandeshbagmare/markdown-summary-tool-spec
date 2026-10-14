"""Fact planner — deterministic rule-based FactSpec generation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class FactSpec:
    id: str
    kind: str  # count | sum | avg | min | max | group_count | topk | distinct | null_rate
    sql: str
    description: str
    tolerance: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def _safe_ident(name: str) -> str:
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
        return name
    return '"' + name.replace('"', '""') + '"'


class FactPlanner:
    """Deterministic planner that emits FactSpecs from profiles + question.

    No LLM required for MVP.  Heuristics:
    * Always emit row counts per dataset.
    * For numeric columns: sum / avg / min / max.
    * For low-cardinality string columns: group counts / top-k.
    * Question keywords (total, average, top, max, etc.) bias extra specs.
    """

    def plan(
        self,
        profiles: dict[str, Any],
        question: str,
        *,
        topk_limit: int = 5,
    ) -> list[FactSpec]:
        # Normalize profiles — accept DatasetProfile objects or dicts
        norm: dict[str, Any] = {}
        for name, p in profiles.items():
            if hasattr(p, "to_dict"):
                norm[name] = p.to_dict()
            elif hasattr(p, "__dict__") and hasattr(p, "row_count"):
                # dataclass
                norm[name] = {
                    "name": p.name,
                    "row_count": p.row_count,
                    "columns": [
                        {"name": c.name, "inferred_type": c.inferred_type, "distinct_count": c.distinct_count}
                        for c in getattr(p, "columns", [])
                    ],
                }
            else:
                norm[name] = p

        q_lower = question.lower()
        specs: list[FactSpec] = []

        for ds_name, prof in norm.items():
            tbl = _safe_ident(ds_name)
            row_count = prof.get("row_count", 0)

            # Always: row count
            specs.append(
                FactSpec(
                    id=f"{ds_name}__count",
                    kind="count",
                    sql=f"SELECT COUNT(*) AS value FROM {tbl}",
                    description=f"Row count for '{ds_name}'",
                )
            )

            if row_count == 0:
                continue

            columns: list[dict[str, Any]] = prof.get("columns", [])

            for col in columns:
                cname = col.get("name", "")
                ctype = col.get("inferred_type", "string")
                distinct = col.get("distinct_count")
                safe_col = _safe_ident(cname)

                if ctype in ("integer", "float"):
                    # sum / avg / min / max for numeric
                    specs.append(
                        FactSpec(
                            id=f"{ds_name}__{cname}__sum",
                            kind="sum",
                            sql=f"SELECT SUM({safe_col}) AS value FROM {tbl}",
                            description=f"Sum of {cname} in '{ds_name}'",
                        )
                    )
                    specs.append(
                        FactSpec(
                            id=f"{ds_name}__{cname}__avg",
                            kind="avg",
                            sql=f"SELECT AVG({safe_col}) AS value FROM {tbl}",
                            description=f"Average of {cname} in '{ds_name}'",
                        )
                    )
                    specs.append(
                        FactSpec(
                            id=f"{ds_name}__{cname}__min",
                            kind="min",
                            sql=f"SELECT MIN({safe_col}) AS value FROM {tbl}",
                            description=f"Minimum of {cname} in '{ds_name}'",
                        )
                    )
                    specs.append(
                        FactSpec(
                            id=f"{ds_name}__{cname}__max",
                            kind="max",
                            sql=f"SELECT MAX({safe_col}) AS value FROM {tbl}",
                            description=f"Maximum of {cname} in '{ds_name}'",
                        )
                    )

                elif ctype in ("string", "boolean"):
                    # Group counts for low-cardinality columns
                    if distinct is not None and distinct <= 50:
                        specs.append(
                            FactSpec(
                                id=f"{ds_name}__{cname}__group_count",
                                kind="group_count",
                                sql=f"SELECT {safe_col} AS grp, COUNT(*) AS value FROM {tbl} GROUP BY {safe_col} ORDER BY value DESC LIMIT {topk_limit}",
                                description=f"Group counts for {cname} in '{ds_name}'",
                            )
                        )
                    # Top-k always for string cols mentioned in question
                    if cname.lower() in q_lower:
                        specs.append(
                            FactSpec(
                                id=f"{ds_name}__{cname}__topk",
                                kind="topk",
                                sql=f"SELECT {safe_col} AS grp, COUNT(*) AS value FROM {tbl} GROUP BY {safe_col} ORDER BY value DESC LIMIT {topk_limit}",
                                description=f"Top {topk_limit} values of {cname} in '{ds_name}'",
                            )
                        )

        # Question-driven extras: if question mentions specific agg keywords, ensure coverage
        # (already covered above, but add distinct counts if asked)
        if any(kw in q_lower for kw in ("distinct", "unique", "how many different")):
            for ds_name, prof in norm.items():
                tbl = _safe_ident(ds_name)
                for col in prof.get("columns", []):
                    cname = col.get("name", "")
                    safe_col = _safe_ident(cname)
                    if cname.lower() in q_lower:
                        specs.append(
                            FactSpec(
                                id=f"{ds_name}__{cname}__distinct",
                                kind="distinct",
                                sql=f"SELECT COUNT(DISTINCT {safe_col}) AS value FROM {tbl}",
                                description=f"Distinct count of {cname} in '{ds_name}'",
                            )
                        )

        # Deduplicate by id (keep first)
        seen: set[str] = set()
        deduped: list[FactSpec] = []
        for s in specs:
            if s.id not in seen:
                seen.add(s.id)
                deduped.append(s)
        return deduped
