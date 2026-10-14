"""DeepAgent + subagents wiring — attaches all tools, parallel execution for speed.

- DeepAgent (deepagents.create_deep_agent) with 4 tools: markdown, visualization, dashboard, command.
- Subagents: asyncio.gather parallel tool calls for dashboard/markdown+viz combos.
- Falls back gracefully if deepagents not installed or API keys missing.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

SYSTEM_PROMPT = """You are a data analysis assistant with four tools:

- create_markdown_summary: TEXT summaries (verified markdown + HTML). Args: datasets_json, question, options_json.
- create_visualization: SINGLE chart (Vega-Lite + HTML). Args: datasets_json, question, chart_type, options_json.
- create_dashboard: MULTI-chart dashboard (2-6 charts, grid/row, HTML). Args: datasets_json, question, charts_json, options_json.
- create_command_summary: EXTENSIBLE command → markdown+HTML for any requirement. Args: datasets_json, command, options_json.

Rules:
- For text summaries, use create_markdown_summary or create_command_summary.
- For single charts, use create_visualization.
- For dashboards / multiple charts, use create_dashboard.
- When user asks for both summary + chart, call both in parallel.
- Never invent numbers; rely on tool-returned facts.
- All tools return self-contained HTML (preamble + body + postamble) — surface it.
"""


def _get_tools() -> list[Any]:
    from markdown_summary_tool.tools.command_tool import create_command_summary
    from markdown_summary_tool.tools.summarize_tool import create_markdown_summary
    from visualization_tool.tool import create_dashboard, create_visualization

    return [create_markdown_summary, create_visualization, create_dashboard, create_command_summary]


def _try_create_deep_agent(tools: list[Any], system_prompt: str):
    try:
        from deepagents import create_deep_agent  # type: ignore

        return create_deep_agent, True
    except ImportError:
        return None, False


def build_deep_agent(model: str = "claude-fable-5.1"):
    """Build a DeepAgent with all 4 tools. Returns (agent, is_real)."""
    tools = _get_tools()
    factory, is_real = _try_create_deep_agent(tools, SYSTEM_PROMPT)
    if not is_real or factory is None:
        return None, False
    agent = factory(model=model, tools=tools, system_prompt=SYSTEM_PROMPT)
    return agent, True


# ── Subagents: parallel execution helpers ────────────────────────────────

async def run_parallel(
    calls: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run multiple tool calls in parallel via asyncio.to_thread (subagents).

    Each call: {tool: str, kwargs: dict}. Returns list of parsed JSON results.
    Tool names: create_markdown_summary | create_visualization | create_dashboard | create_command_summary
    """
    name_to_tool = {t.name: t for t in _get_tools()}  # type: ignore[attr-defined]

    async def _one(call: dict[str, Any]) -> dict[str, Any]:
        name = call.get("tool", "")
        kwargs = call.get("kwargs", {})
        fn = name_to_tool.get(name)
        if fn is None:
            return {"error_code": "unknown_tool", "message": f"unknown tool {name}"}
        try:
            raw = await asyncio.to_thread(fn.invoke, kwargs)  # type: ignore[attr-defined]
            return json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception as exc:
            return {"error_code": "tool_failed", "message": str(exc), "tool": name}

    return list(await asyncio.gather(*[_one(c) for c in calls]))


async def run_markdown_and_dashboard(
    datasets_json: str,
    question: str,
    options_json: str = "{}",
) -> dict[str, Any]:
    """Subagent example: markdown summary + dashboard in parallel."""
    calls = [
        {"tool": "create_markdown_summary", "kwargs": {"datasets_json": datasets_json, "question": question, "options_json": options_json}},
        {"tool": "create_dashboard", "kwargs": {"datasets_json": datasets_json, "question": question, "charts_json": "[]", "options_json": options_json}},
    ]
    results = await run_parallel(calls)
    return {"markdown_result": results[0], "dashboard_result": results[1]}


def demo_subagents_sync() -> None:
    """Quick sync demo of subagents (no API keys needed — uses MockLLM)."""
    datasets_json = json.dumps([{"kind": "inline_json", "name": "orders", "data": [
        {"customer": "Alice", "amount": 120.5, "region": "East"},
        {"customer": "Bob", "amount": 80.0, "region": "West"},
        {"customer": "Alice", "amount": 200.0, "region": "East"},
        {"customer": "Carol", "amount": 50.0, "region": "West"},
        {"customer": "Dave", "amount": 310.0, "region": "East"},
    ]}])
    result = asyncio.run(run_markdown_and_dashboard(datasets_json, "Summarize and dashboard by region"))
    print(json.dumps({k: {"keys": list(v.keys()), "verified": v.get("meta", {}).get("verified"), "html_len": len(v.get("html") or "")} for k, v in result.items()}, indent=2))


if __name__ == "__main__":
    # Try DeepAgent
    agent, is_real = build_deep_agent()
    print(f"DeepAgent: {'real' if is_real else 'mock (deepagents not installed or no keys)'}")
    if agent is not None:
        print(f"Tools: {[t.name for t in _get_tools()]}")  # type: ignore[attr-defined]
    print("\n--- Subagents parallel demo ---")
    demo_subagents_sync()
