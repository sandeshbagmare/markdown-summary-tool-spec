"""Mechanical verifier — pure regex + string matching, no LLM."""

from __future__ import annotations

import re
from typing import Any

# Matches numbers with optional commas, currency symbols, and percent signs.
# Examples: 1,234  $1,234.56  42%  -3.14  1,000,000  9999
_NUMBER_RE = re.compile(
    r"""
    (?P<prefix>[$€£¥])?                      # optional currency
    (?P<sign>-)?                             # optional minus
    (?P<int>\d{1,3}(?:,\d{3})+|\d+)           # integer part (comma-grouped or plain)
    (?:\.(?P<frac>\d+))?                     # optional fractional part
    (?P<suffix>%?)                           # optional percent
    """,
    re.VERBOSE,
)


def _parse_number(raw: str) -> float | None:
    s = raw.strip().replace(",", "").replace("$", "").replace("€", "").replace("£", "").replace("¥", "").replace("%", "")
    if not s or s in ("-", "."):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_numbers(markdown: str) -> list[float]:
    """Extract all numeric values from *markdown*.

    Handles commas, currency symbols ($, EUR, GBP, JPY), and percentages.
    Returns a list of floats in order of appearance.
    """
    results: list[float] = []
    for m in _NUMBER_RE.finditer(markdown):
        # Skip bare single digits that are likely list markers or headings
        # but keep them if they have currency/percent context
        raw = m.group(0)
        # Filter out matches that are just a single digit with no prefix/suffix
        # and are likely markdown list numbering — keep them anyway for
        # hallucination detection; the verifier handles tolerance.
        val = _parse_number(raw)
        if val is not None:
            results.append(val)
    return results


def _normalize_formatted(formatted: str) -> str:
    return formatted.strip()


def _formatted_variants(formatted: str) -> list[str]:
    """Return string variants to search for in markdown."""
    variants = [formatted]
    # Without commas
    no_comma = formatted.replace(",", "")
    if no_comma not in variants:
        variants.append(no_comma)
    # Without currency
    stripped = formatted.replace("$", "").replace("€", "").replace("£", "").replace("¥", "").strip()
    if stripped not in variants and stripped:
        variants.append(stripped)
    return variants


def verify(
    markdown: str,
    facts: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Verify that *markdown* only contains numbers grounded in *facts*.

    Checks:
    1. Every fact's ``formatted`` value appears in the markdown (within
       tolerance for numeric facts). Missing facts are reported.
    2. Every number found in the markdown corresponds to some fact value
       (within tolerance). Hallucinated numbers are reported.

    Args:
        markdown: The LLM-generated markdown to verify.
        facts: List of fact dicts with ``value``, ``formatted``, ``tolerance``.

    Returns:
        ``(passed, violations)`` — *passed* is True iff no violations.
    """
    violations: list[str] = []

    # Build lookup of expected numeric values
    expected: list[dict[str, Any]] = []
    for f in facts:
        formatted = f.get("formatted", "")
        if formatted in ("—", "error", "", None):
            continue
        raw_val = f.get("value")
        tolerance = f.get("tolerance")
        fid = f.get("id", "?")
        # Parse numeric value
        num: float | None = None
        if isinstance(raw_val, (int, float)):
            num = float(raw_val)
        elif isinstance(raw_val, str):
            num = _parse_number(raw_val)
            if num is None:
                # Non-numeric fact (e.g. group label) — check string presence
                pass
        expected.append({"id": fid, "formatted": str(formatted), "value": num, "tolerance": tolerance})

    # --- Check 1: each expected formatted value appears in markdown ---
    for exp in expected:
        formatted: str = exp["formatted"]
        fid: str = exp["id"]
        num: float | None = exp["value"]
        tol: float | None = exp["tolerance"]

        # Try exact / variant string match first
        found = any(v in markdown for v in _formatted_variants(formatted))
        if found:
            continue

        # For numeric facts, also try tolerance-based matching against extracted numbers
        if num is not None:
            nums = extract_numbers(markdown)
            tolerance = tol if tol is not None else 1e-9
            # Use relative tolerance for large numbers, absolute for small
            matched = False
            for n in nums:
                if abs(n - num) <= max(tolerance, abs(num) * 1e-9):
                    matched = True
                    break
                # Also handle percentage: fact 0.42 vs markdown "42%"
                if abs(n - num * 100) <= max(tolerance, abs(num * 100) * 1e-9):
                    matched = True
                    break
            if matched:
                continue

        violations.append(f"missing fact '{fid}': expected '{formatted}' not found in markdown")

    # Collect all numbers that appear in fact descriptions/provenance (structural, not hallucinated)
    desc_numbers: set[float] = set()
    for f in facts:
        for key in ("description", "group"):
            v = f.get("provenance", {}).get(key) if isinstance(f.get("provenance"), dict) else None
            if v:
                for m in _NUMBER_RE.finditer(str(v)):
                    pv = _parse_number(m.group(0))
                    if pv is not None:
                        desc_numbers.add(pv)
        # also check id
        for m in _NUMBER_RE.finditer(str(f.get("id",""))):
            pv = _parse_number(m.group(0))
            if pv is not None:
                desc_numbers.add(pv)

    # --- Check 2: every number in markdown is grounded in some fact ---
    md_numbers = extract_numbers(markdown)
    for n in md_numbers:
        if n in desc_numbers:
            continue
        grounded = False
        for exp in expected:
            ev = exp["value"]
            if ev is None:
                continue
            tol = exp["tolerance"] if exp["tolerance"] is not None else 1e-9
            if abs(n - ev) <= max(tol, abs(ev) * 1e-9):
                grounded = True
                break
            if abs(n - ev * 100) <= max(tol, abs(ev * 100) * 1e-9):
                grounded = True
                break
            # Also check formatted string numeric parse
            fv = _parse_number(exp["formatted"])
            if fv is not None and abs(n - fv) <= max(tol, abs(fv) * 1e-9):
                grounded = True
                break
        if not grounded:
            # Allow small integers 0-10 that are likely structural (list counts, etc.)
            # Only flag if the number is not trivially structural
            # We flag all ungrounded numbers to be strict; callers can filter
            violations.append(f"hallucinated number '{n:g}' not grounded in any fact")

    passed = len(violations) == 0
    return passed, violations
