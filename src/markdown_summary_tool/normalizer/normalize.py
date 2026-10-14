"""Row normalization: coerce types, handle nulls, trim strings, parse dates."""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any

try:
    from dateutil import parser as date_parser  # type: ignore[import-untyped]
except ImportError:
    date_parser = None  # type: ignore[assignment]

NULL_TOKENS = {"", "null", "NULL", "None", "none", "N/A", "n/a", "NA", "#N/A", "-", "--"}
DATE_HINT_RE = re.compile(r"date|time|created|updated|timestamp", re.IGNORECASE)


def _is_null_token(value: str) -> bool:
    return value.strip() in NULL_TOKENS


def _try_number(value: str) -> int | float | None:
    s = value.strip().replace(",", "")
    if not s or s in ("-", "--"):
        return None
    # strip currency / percent wrappers
    s_clean = s.replace("$", "").replace("%", "").strip()
    try:
        if "." in s_clean or "e" in s_clean.lower():
            return float(s_clean)
        return int(s_clean)
    except ValueError:
        return None


def _try_date(value: str) -> datetime | date | None:
    if date_parser is None:
        # fallback: try ISO format only
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
        return None
    try:
        return date_parser.parse(value.strip())
    except (ValueError, OverflowError):
        return None


def _coerce_value(value: Any, col: str, warnings: list[str]) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool, datetime, date)):
        return value
    if not isinstance(value, str):
        return value
    s = value.strip()
    if _is_null_token(s):
        return None
    # Trim strings — always
    # Try numeric coercion
    num = _try_number(s)
    if num is not None:
        # Only coerce if the entire string was numeric (allow commas/currency)
        cleaned = s.replace(",", "").replace("$", "").replace("%", "").strip()
        # Verify round-trip: str(num) should be close to cleaned
        try:
            if isinstance(num, int) and str(num) == cleaned:
                return num
            if isinstance(num, float) and cleaned.lower() not in ("inf", "-inf", "nan"):
                # Accept float if parsing consumed the whole string
                float(cleaned)
                return num
        except ValueError:
            pass
    # Try date coercion for date-hinted columns
    if DATE_HINT_RE.search(col):
        dt = _try_date(s)
        if dt is not None:
            return dt
    # Also try date for ISO-like strings regardless of column name
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        dt = _try_date(s)
        if dt is not None:
            return dt
    return s


def normalize_rows(
    rows: list[dict[str, Any]],
    *,
    warnings: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize a list of rows.

    Returns ``(normalized_rows, warnings)``.
    """
    if warnings is None:
        warnings: list[str] = []
    if not rows:
        return [], warnings

    # Collect column null counts for warnings
    col_nulls: dict[str, int] = {}
    col_total = len(rows)
    normalized: list[dict[str, Any]] = []

    for idx, row in enumerate(rows):
        new_row: dict[str, Any] = {}
        for col, val in row.items():
            coerced = _coerce_value(val, col, warnings)
            new_row[col] = coerced
            if coerced is None and val is not None and not (isinstance(val, str) and _is_null_token(val)):
                # Genuine null after coercion — track
                pass
            if coerced is None:
                col_nulls[col] = col_nulls.get(col, 0) + 1
        normalized.append(new_row)

    # Emit warnings for fully-null columns
    for col, null_count in col_nulls.items():
        if null_count == col_total and col_total > 0:
            warnings.append(f"column '{col}' is entirely null ({col_total} rows)")

    # Warn about empty dataset
    if not normalized:
        warnings.append("dataset is empty after normalization")

    return normalized, warnings


def normalize(
    rows: list[dict[str, Any]],
    *,
    warnings: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Alias for :func:`normalize_rows` (backwards compat)."""
    return normalize_rows(rows, warnings=warnings)
