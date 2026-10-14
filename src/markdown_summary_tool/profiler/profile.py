"""Dataset profiler — row count, column types, null rates, cardinality, sample."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class ColumnProfile:
    name: str
    inferred_type: str  # "integer" | "float" | "boolean" | "datetime" | "string" | "null" | "mixed"
    null_count: int
    null_rate: float
    distinct_count: int | None  # None if too large / not computed
    sample_values: list[Any] = field(default_factory=list)


@dataclass
class DatasetProfile:
    name: str
    row_count: int
    column_count: int
    columns: list[ColumnProfile] = field(default_factory=list)
    sample_rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": [
                {
                    "name": c.name,
                    "inferred_type": c.inferred_type,
                    "null_count": c.null_count,
                    "null_rate": c.null_rate,
                    "distinct_count": c.distinct_count,
                    "sample_values": c.sample_values,
                }
                for c in self.columns
            ],
            "sample_rows": self.sample_rows,
            "warnings": self.warnings,
        }


def _infer_type(values: list[Any]) -> str:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "null"
    types = set()
    for v in non_null:
        if isinstance(v, bool):
            types.add("boolean")
        elif isinstance(v, int):
            types.add("integer")
        elif isinstance(v, float):
            types.add("float")
        elif isinstance(v, (datetime, date)):
            types.add("datetime")
        else:
            types.add("string")
    if len(types) == 1:
        return next(iter(types))
    if types == {"integer", "float"}:
        return "float"
    return "mixed"


def profile_dataset(
    name: str,
    rows: list[dict[str, Any]],
    *,
    sample_size: int = 5,
    max_distinct: int = 10_000,
) -> DatasetProfile:
    """Profile a single dataset."""
    if not rows:
        return DatasetProfile(name=name, row_count=0, column_count=0, sample_rows=[])

    # Union of all column names
    all_cols: list[str] = []
    seen: set[str] = set()
    for r in rows:
        for k in r:
            if k not in seen:
                seen.add(k)
                all_cols.append(k)

    row_count = len(rows)
    columns: list[ColumnProfile] = []
    warnings: list[str] = []

    for col in all_cols:
        vals = [r.get(col) for r in rows]
        null_count = sum(1 for v in vals if v is None)
        null_rate = null_count / row_count if row_count else 0.0
        inferred = _infer_type(vals)

        # Cardinality (cap to avoid huge sets)
        distinct: int | None = None
        try:
            uniq: set[Any] = set()
            for v in vals:
                if v is None:
                    continue
                # Use string repr for unhashable
                try:
                    uniq.add(v)
                except TypeError:
                    uniq.add(str(v))
                if len(uniq) > max_distinct:
                    distinct = max_distinct + 1  # sentinel: > max
                    break
            if distinct is None:
                distinct = len(uniq)
        except Exception:
            distinct = None

        sample_vals = [v for v in vals if v is not None][:3]

        if null_rate == 1.0:
            warnings.append(f"column '{col}' is entirely null")

        columns.append(
            ColumnProfile(
                name=col,
                inferred_type=inferred,
                null_count=null_count,
                null_rate=round(null_rate, 4),
                distinct_count=distinct,
                sample_values=sample_vals,
            )
        )

    sample_rows = rows[:sample_size]

    if row_count == 0:
        warnings.append(f"dataset '{name}' is empty")

    return DatasetProfile(
        name=name,
        row_count=row_count,
        column_count=len(all_cols),
        columns=columns,
        sample_rows=sample_rows,
        warnings=warnings,
    )


def profile(
    datasets: dict[str, list[dict[str, Any]]],
    *,
    sample_size: int = 5,
) -> dict[str, DatasetProfile]:
    """Profile multiple datasets at once."""
    return {name: profile_dataset(name, rows, sample_size=sample_size) for name, rows in datasets.items()}
