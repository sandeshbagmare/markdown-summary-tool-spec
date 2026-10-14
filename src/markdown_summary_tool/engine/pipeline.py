"""End-to-end pipeline: fetch -> normalize -> profile -> plan -> compute -> LLM -> verify -> sanitize."""

from __future__ import annotations

import json
import time
from typing import Any

from markdown_summary_tool.connectors.inline import InlineConnector
from markdown_summary_tool.engine.duckdb_engine import DuckDBEngine
from markdown_summary_tool.facts.compute import compute_facts
from markdown_summary_tool.facts.planner import FactPlanner
from markdown_summary_tool.llm.client import MockLLMClient
from markdown_summary_tool.llm.prompts import build_prompt
from markdown_summary_tool.normalizer.normalize import normalize_rows
from markdown_summary_tool.profiler.profile import profile_dataset
from markdown_summary_tool.sanitizer.sanitize import sanitize
from markdown_summary_tool.verifier.verify import verify
from markdown_summary_tool.verifier.repair import repair


async def _fetch_datasets(datasets: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
    warnings: list[str] = []
    result: dict[str, list[dict[str, Any]]] = {}
    for ds in datasets:
        kind = ds.get("kind", "")
        name = ds.get("name", "dataset")
        if kind in ("inline_json", "inline_csv"):
            conn = InlineConnector(ds)
            rows = await conn.fetch()
            result[name] = rows
        elif kind == "url":
            from markdown_summary_tool.connectors.http import HttpConnector
            conn = HttpConnector(ds)
            rows = await conn.fetch()
            result[name] = rows
        elif kind == "connector":
            warnings.append(f"connector kind for '{name}' not yet implemented — skipped")
            result[name] = []
        else:
            warnings.append(f"unknown dataset kind '{kind}' for '{name}' — skipped")
            result[name] = []
    return result, warnings


def _run_sync(request: dict[str, Any], llm: Any | None = None) -> dict[str, Any]:
    import asyncio

    return asyncio.run(_run_async(request, llm))


async def _run_async(request: dict[str, Any], llm: Any | None = None) -> dict[str, Any]:
    t0 = time.monotonic()
    datasets: list[dict[str, Any]] = request.get("datasets", [])
    question: str = request.get("question", "")
    options: dict[str, Any] = request.get("options") or {}
    redact: list[str] = options.get("redact") or []
    locale_str: str = options.get("locale") or "en-US"
    max_rows: int | None = options.get("max_rows")

    warnings: list[str] = []

    # 1. Fetch
    raw_datasets, fetch_warnings = await _fetch_datasets(datasets)
    warnings.extend(fetch_warnings)

    # 2. Normalize + cap rows
    normalized: dict[str, list[dict[str, Any]]] = {}
    for name, rows in raw_datasets.items():
        if max_rows is not None and len(rows) > max_rows:
            warnings.append(f"dataset '{name}' truncated from {len(rows)} to {max_rows} rows")
            rows = rows[:max_rows]
        normed, w = normalize_rows(rows)
        normalized[name] = normed
        warnings.extend(w)

    # 3. Profile
    profiles: dict[str, Any] = {}
    for name, rows in normalized.items():
        prof = profile_dataset(name, rows)
        profiles[name] = prof
        warnings.extend(prof.warnings)

    # 4. Register in DuckDB + plan + compute facts
    engine = DuckDBEngine()
    try:
        for name, rows in normalized.items():
            engine.register(name, rows)

        planner = FactPlanner()
        specs = planner.plan(profiles, question)
        facts = compute_facts(engine, specs, locale_str=locale_str)
    finally:
        engine.close()

    # 5. LLM verbalization
    if llm is None:
        llm = MockLLMClient()

    profile_summary = "; ".join(
        f"{p.name}: {p.row_count} rows, {p.column_count} cols" for p in profiles.values()
    )
    prompt = build_prompt(question, facts, warnings, profile_summary)
    facts_json = json.dumps(facts, indent=2, ensure_ascii=False, default=str)
    markdown = await llm.generate(prompt, facts_json)

    # 6. Verify + repair
    passed, violations = verify(markdown, facts)
    if not passed:
        markdown, passed, violations = await repair(markdown, facts, violations, llm)
        if not passed:
            warnings.append(f"verification still failing after repair: {violations}")

    # 7. Sanitize
    markdown = sanitize(markdown, redacted_columns=redact)

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    # 8. Self-contained HTML (pre + markdown + post)
    html: str | None = None
    if options.get("include_html", True):
        try:
            from markdown_summary_tool.presentation.html import build_report_html

            html = build_report_html(
                markdown=markdown,
                preamble=options.get("preamble") or "",
                postamble=options.get("postamble") or "",
                title=options.get("title") or "Summary Report",
                facts=facts,
                warnings=warnings if options.get("include_warnings", True) else None,
                meta={"elapsed_ms": elapsed_ms, "verified": passed, "violations": violations},
                theme=options.get("theme") or "light",
            )
        except Exception:
            html = None

    return {
        "markdown": markdown,
        "html": html,
        "preamble": options.get("preamble") or "",
        "postamble": options.get("postamble") or "",
        "facts": facts,
        "warnings": warnings,
        "artifacts": {},
        "meta": {
            "elapsed_ms": elapsed_ms,
            "fact_count": len(facts),
            "verified": passed,
            "violations": violations,
        },
    }


def run(request: dict[str, Any], llm: Any | None = None) -> dict[str, Any]:
    """Synchronous entry point for the pipeline (used by gateway via to_thread)."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Called from within an event loop — create a new loop in a thread
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_run_sync, request, llm)
            return fut.result()
    else:
        return asyncio.run(_run_async(request, llm))
