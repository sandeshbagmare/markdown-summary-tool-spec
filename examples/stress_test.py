"""Stress test: 10k + 1k rows, both tools, timing + correctness.

Runnable as:  python examples/stress_test.py
Uses MockLLMClient for determinism (no API call).
"""

from __future__ import annotations

import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from markdown_summary_tool.llm.client import MockLLMClient
from markdown_summary_tool.tools.summarize_tool import create_markdown_summary
from visualization_tool.tool import create_visualization

REGIONS = ["East", "West", "North", "South"]
CATEGORIES = ["Electronics", "Books", "Clothing", "Food", "Toys"]
CUSTOMERS = [f"Customer_{i:04d}" for i in range(200)]


def gen_orders(n: int, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(n):
        rows.append(
            {
                "customer": rng.choice(CUSTOMERS),
                "amount": round(rng.uniform(5, 1000), 2),
                "region": rng.choice(REGIONS),
                "date": f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
                "order_id": f"O{i:06d}",
            }
        )
    return rows


def gen_products(n: int, seed: int = 99) -> list[dict]:
    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(n):
        rows.append(
            {
                "category": rng.choice(CATEGORIES),
                "price": round(rng.uniform(5, 2000), 2),
                "stock": rng.randint(0, 500),
                "sku": f"SKU{i:06d}",
            }
        )
    return rows


def expected_aggregates(orders: list[dict]) -> dict:
    total = sum(r["amount"] for r in orders)
    by_region: dict[str, float] = {}
    for r in orders:
        by_region[r["region"]] = by_region.get(r["region"], 0) + r["amount"]
    return {"total": total, "by_region": by_region, "count": len(orders)}


def _call(tool, **kw):  # type: ignore[no-untyped-def]
    return tool.invoke(kw) if hasattr(tool, "invoke") else tool(**kw)


def run_summarize(datasets_json: str, question: str) -> tuple[dict, float]:
    t0 = time.perf_counter()
    raw = _call(create_markdown_summary, datasets_json=datasets_json, question=question)
    elapsed = time.perf_counter() - t0
    parsed = json.loads(raw)
    return parsed, elapsed


def run_viz(datasets_json: str, question: str, chart_type: str = "auto") -> tuple[dict, float]:
    t0 = time.perf_counter()
    raw = _call(create_visualization, datasets_json=datasets_json, question=question, chart_type=chart_type)
    elapsed = time.perf_counter() - t0
    parsed = json.loads(raw)
    return parsed, elapsed


def main() -> None:
    print("=== Stress Test: DeepAgent Tools ===\n")

    # Dataset 1: 10k orders
    orders_10k = gen_orders(10_000, seed=42)
    # Dataset 2: 1k products
    products_1k = gen_products(1_000, seed=99)

    exp = expected_aggregates(orders_10k)
    print(f"Dataset A: orders 10k rows  total={exp['total']:.2f}  regions={len(exp['by_region'])}")
    print(f"Dataset B: products 1k rows  categories={len(set(r['category'] for r in products_1k))}")

    datasets_10k = json.dumps([{"kind": "inline_json", "name": "orders", "data": orders_10k}])
    datasets_1k = json.dumps([{"kind": "inline_json", "name": "products", "data": products_1k}])
    datasets_both = json.dumps(
        [
            {"kind": "inline_json", "name": "orders", "data": orders_10k},
            {"kind": "inline_json", "name": "products", "data": products_1k},
        ]
    )

    results: list[dict] = []

    # Test 1: summarize 10k
    print("\n--- Test 1: summarize 10k orders ---")
    parsed, elapsed = run_summarize(datasets_10k, "Summarize total and average amount by region")
    ok = "markdown" in parsed and "facts" in parsed and not parsed.get("error_code")
    fact_count = len(parsed.get("facts", []))
    verified = parsed.get("meta", {}).get("verified")
    print(f"  time={elapsed:.3f}s  facts={fact_count}  verified={verified}  ok={ok}")
    # Verify facts contain numeric values that are plausible (non-empty formatted)
    has_values = any(f.get("formatted") not in ("—", "error", "") for f in parsed.get("facts", []))
    print(f"  has_values={has_values}")
    results.append({"test": "summarize_10k", "elapsed": elapsed, "facts": fact_count, "ok": ok and has_values})

    # Test 2: visualize 10k
    print("\n--- Test 2: visualize 10k orders (bar) ---")
    parsed2, elapsed2 = run_viz(datasets_10k, "Bar chart of amount by region", chart_type="bar")
    ok2 = "chart_spec" in parsed2 and not parsed2.get("error_code")
    spec = parsed2.get("chart_spec", {})
    has_vega = "$schema" in spec and "mark" in spec
    row_count = parsed2.get("meta", {}).get("row_count", 0)
    print(f"  time={elapsed2:.3f}s  chart_type={parsed2.get('meta', {}).get('chart_type')}  rows={row_count}  has_vega={has_vega}  ok={ok2}")
    results.append({"test": "visualize_10k", "elapsed": elapsed2, "rows": row_count, "ok": ok2 and has_vega})

    # Test 3: summarize 1k
    print("\n--- Test 3: summarize 1k products ---")
    parsed3, elapsed3 = run_summarize(datasets_1k, "Summarize price and stock by category")
    ok3 = "markdown" in parsed3 and not parsed3.get("error_code")
    fact_count3 = len(parsed3.get("facts", []))
    print(f"  time={elapsed3:.3f}s  facts={fact_count3}  ok={ok3}")
    results.append({"test": "summarize_1k", "elapsed": elapsed3, "facts": fact_count3, "ok": ok3})

    # Test 4: visualize 1k
    print("\n--- Test 4: visualize 1k products (auto) ---")
    parsed4, elapsed4 = run_viz(datasets_1k, "Show distribution of price by category")
    ok4 = "chart_spec" in parsed4 and not parsed4.get("error_code")
    print(f"  time={elapsed4:.3f}s  chart_type={parsed4.get('meta', {}).get('chart_type')}  ok={ok4}")
    results.append({"test": "visualize_1k", "elapsed": elapsed4, "ok": ok4})

    # Test 5: summarize both datasets together
    print("\n--- Test 5: summarize both datasets (10k + 1k) ---")
    parsed5, elapsed5 = run_summarize(datasets_both, "Summarize orders and products")
    ok5 = "markdown" in parsed5 and not parsed5.get("error_code")
    fact_count5 = len(parsed5.get("facts", []))
    print(f"  time={elapsed5:.3f}s  facts={fact_count5}  ok={ok5}")
    results.append({"test": "summarize_both", "elapsed": elapsed5, "facts": fact_count5, "ok": ok5})

    # Test 6: visualize both (should pick first non-empty)
    print("\n--- Test 6: visualize both datasets ---")
    parsed6, elapsed6 = run_viz(datasets_both, "Bar chart overview", chart_type="bar")
    ok6 = "chart_spec" in parsed6 and not parsed6.get("error_code")
    print(f"  time={elapsed6:.3f}s  ok={ok6}")
    results.append({"test": "visualize_both", "elapsed": elapsed6, "ok": ok6})

    # Summary
    print("\n=== Summary ===")
    total_time = sum(r["elapsed"] for r in results)
    all_ok = all(r["ok"] for r in results)
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        print(f"  {status}  {r['test']:20s}  {r['elapsed']:.3f}s  { {k:v for k,v in r.items() if k not in ('test','elapsed','ok')}}")
    print(f"\nTotal time: {total_time:.3f}s  Overall: {'PASS' if all_ok else 'FAIL'}")
    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
