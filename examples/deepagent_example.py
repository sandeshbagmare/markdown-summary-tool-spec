"""DeepAgent example using both markdown summary and visualization tools.

Runnable as:  python examples/deepagent_example.py
If API_BASE / API_KEY are not set, runs in mock mode (no API call).
"""

from __future__ import annotations

import json
import os
import sys

# Ensure src is importable when running as script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from markdown_summary_tool.llm.client import get_llm_client
from markdown_summary_tool.tools.summarize_tool import create_markdown_summary
from visualization_tool.tool import create_visualization

SYSTEM_PROMPT = """You are a data analysis assistant with two tools:

- create_markdown_summary: use for TEXT summaries of datasets. Pass datasets_json (JSON array of DataRef), a question, and optional options_json. Returns verified markdown with facts.
- create_visualization: use for CHARTS. Pass datasets_json, a question describing the desired chart, chart_type (auto/bar/line/pie/scatter), and optional options_json. Returns a Vega-Lite chart_spec.

Rules:
- For summarization requests, call create_markdown_summary.
- For visualization / chart requests, call create_visualization.
- When the user asks for both, call both tools and combine results.
- Never invent numbers; rely on tool-returned facts.
"""

SAMPLE_ORDERS = [
    {"customer": "Alice", "amount": 120.5, "region": "East", "date": "2026-01-10"},
    {"customer": "Bob", "amount": 80.0, "region": "West", "date": "2026-01-11"},
    {"customer": "Alice", "amount": 200.0, "region": "East", "date": "2026-01-12"},
    {"customer": "Carol", "amount": 50.0, "region": "West", "date": "2026-01-13"},
    {"customer": "Dave", "amount": 300.0, "region": "East", "date": "2026-01-14"},
]

SAMPLE_PRODUCTS = [
    {"category": "Electronics", "price": 999.0, "stock": 12},
    {"category": "Books", "price": 19.99, "stock": 100},
    {"category": "Electronics", "price": 499.0, "stock": 5},
]


def _build_datasets_json(rows: list[dict], name: str = "orders") -> str:
    return json.dumps([{"kind": "inline_json", "name": name, "data": rows}])


def _try_create_deep_agent(tools, system_prompt: str):
    try:
        from deepagents import create_deep_agent  # type: ignore

        return create_deep_agent, True
    except ImportError:
        pass

    # Fallback mock that just reports what it would do
    def mock_create_deep_agent(*_a, **_kw):
        class MockAgent:
            def invoke(self, inp):
                return {"messages": [{"content": "Mock agent — would call tools for: " + str(inp)}]}

        return MockAgent()

    return mock_create_deep_agent, False


def main() -> None:
    api_base = os.environ.get("API_BASE", "").strip()
    api_key = os.environ.get("API_KEY", "").strip()
    has_keys = bool(api_base and api_key)
    llm = get_llm_client()
    print(f"LLM client: {type(llm).__name__} (mock={not has_keys})")
    print(f"Model: claude-fable-5.1")
    print(f"System prompt: {SYSTEM_PROMPT[:80]}...")

    tools = [create_markdown_summary, create_visualization]
    print(f"Tools: {[t.name for t in tools]}")

    create_deep_agent, is_real = _try_create_deep_agent(tools, SYSTEM_PROMPT)
    if is_real and has_keys:
        print("Creating DeepAgent with deepagents.create_deep_agent ...")
        agent = create_deep_agent(
            model="claude-fable-5.1",
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
        )
        print("Invoking agent with sample question ...")
        result = agent.invoke(
            {"messages": [{"role": "user", "content": "Summarize total amount by region and show a bar chart of amount by region."}]}
        )
        print(json.dumps(result, indent=2, default=str)[:3000])
    else:
        if not is_real:
            print("(deepagents not installed — running in mock mode, calling tools directly)")
        elif not has_keys:
            print("(API_BASE/API_KEY not set — running in mock mode, calling tools directly)")

        def _call(tool, **kw):  # type: ignore[no-untyped-def]
            return tool.invoke(kw) if hasattr(tool, "invoke") else tool(**kw)

        datasets_json = _build_datasets_json(SAMPLE_ORDERS, "orders")
        print("\n--- create_markdown_summary ---")
        raw = _call(create_markdown_summary, datasets_json=datasets_json, question="Summarize total and average amount by region")
        parsed = json.loads(raw)
        print(f"markdown preview: {parsed.get('markdown', '')[:300]}")
        print(f"facts: {len(parsed.get('facts', []))}  verified: {parsed.get('meta', {}).get('verified')}")

        print("\n--- create_visualization ---")
        raw2 = _call(create_visualization, datasets_json=datasets_json, question="Bar chart of amount by region", chart_type="bar")
        parsed2 = json.loads(raw2)
        spec = parsed2.get("chart_spec", {})
        print(f"chart_type: {parsed2.get('meta', {}).get('chart_type')}  mark: {spec.get('mark')}  rows: {parsed2.get('meta', {}).get('row_count')}")
        print(f"vega spec keys: {list(spec.keys())}")

        # Also demo with second dataset
        datasets_json2 = json.dumps(
            [
                {"kind": "inline_json", "name": "orders", "data": SAMPLE_ORDERS},
                {"kind": "inline_json", "name": "products", "data": SAMPLE_PRODUCTS},
            ]
        )
        print("\n--- Multi-dataset summarization ---")
        raw3 = _call(create_markdown_summary, datasets_json=datasets_json2, question="Summarize orders and products")
        parsed3 = json.loads(raw3)
        print(f"facts: {len(parsed3.get('facts', []))}  warnings: {parsed3.get('warnings', [])[:2]}")


if __name__ == "__main__":
    main()
