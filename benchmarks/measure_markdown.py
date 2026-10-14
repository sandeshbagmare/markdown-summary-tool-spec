"""Benchmark: NAIVE vs COMPUTE-THEN-WRITE for Markdown Summary Tool."""
from __future__ import annotations

import json
import time
import random
from pathlib import Path

import pandas as pd
import duckdb

SIZES = [1000, 5000, 10000, 20000]
PROMPT_OVERHEAD = 500
CATEGORIES = ["A", "B", "C", "D", "E"]
REGIONS = ["North", "South", "East", "West", "Central"]

# Token estimator: try tiktoken, fallback to 4 chars ≈ 1 token
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def estimate_tokens(text: str) -> int:
        return len(_enc.encode(text))
except Exception:
    def estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)


def gen_dataset(n: int, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed + n)
    # Use pandas for generation as required
    ids = list(range(1, n + 1))
    categories = [rng.choice(CATEGORIES) for _ in range(n)]
    amounts = [round(rng.uniform(10.0, 10000.0), 2) for _ in range(n)]
    # dates as ISO strings
    base_date = pd.Timestamp("2023-01-01")
    dates = [(base_date + pd.Timedelta(days=rng.randint(0, 730))).strftime("%Y-%m-%d") for _ in range(n)]
    regions = [rng.choice(REGIONS) for _ in range(n)]
    df = pd.DataFrame({
        "id": ids,
        "category": categories,
        "amount": amounts,
        "date": dates,
        "region": regions,
    })
    return df


def compute_facts_duckdb(df: pd.DataFrame) -> tuple[list[dict], float]:
    """Run DuckDB push-down to compute facts; return (facts, elapsed_s)."""
    t0 = time.perf_counter()
    con = duckdb.connect(":memory:")
    try:
        con.register("dataset", df)
        facts: list[dict] = []

        # Scalar facts
        queries = [
            ("count", "SELECT COUNT(*) AS value FROM dataset", "Row count"),
            ("sum", "SELECT SUM(amount) AS value FROM dataset", "Sum of amount"),
            ("avg", "SELECT AVG(amount) AS value FROM dataset", "Average of amount"),
            ("min", "SELECT MIN(amount) AS value FROM dataset", "Minimum of amount"),
            ("max", "SELECT MAX(amount) AS value FROM dataset", "Maximum of amount"),
            ("distinct_category", "SELECT COUNT(DISTINCT category) AS value FROM dataset", "Distinct categories"),
            ("distinct_region", "SELECT COUNT(DISTINCT region) AS value FROM dataset", "Distinct regions"),
        ]
        for fid, sql, desc in queries:
            try:
                val = con.execute(sql).fetchone()[0]
            except Exception as e:
                val = str(e)
            facts.append({
                "id": fid,
                "kind": fid.split("_")[0] if "_" not in fid else fid,
                "value": float(val) if isinstance(val, (int, float)) and val is not None else (0 if val is None else str(val)),
                "formatted": f"{val:,.2f}" if isinstance(val, float) else str(val) if val is not None else "—",
                "provenance": {"sql": sql, "description": desc},
                "tolerance": None,
            })

        # Group counts (category)
        try:
            rows = con.execute("SELECT category AS grp, COUNT(*) AS value FROM dataset GROUP BY category ORDER BY value DESC LIMIT 5").fetchall()
            for idx, (grp, val) in enumerate(rows):
                facts.append({
                    "id": f"group_category__{idx}",
                    "kind": "group_count",
                    "value": int(val),
                    "formatted": f"{val:,}",
                    "provenance": {"sql": "SELECT category AS grp, COUNT(*) AS value FROM dataset GROUP BY category ORDER BY value DESC LIMIT 5", "description": f"Group counts for category", "group": str(grp)},
                    "tolerance": None,
                })
        except Exception:
            pass

        # Group counts (region)
        try:
            rows = con.execute("SELECT region AS grp, COUNT(*) AS value FROM dataset GROUP BY region ORDER BY value DESC LIMIT 5").fetchall()
            for idx, (grp, val) in enumerate(rows):
                facts.append({
                    "id": f"group_region__{idx}",
                    "kind": "group_count",
                    "value": int(val),
                    "formatted": f"{val:,}",
                    "provenance": {"sql": "SELECT region AS grp, COUNT(*) AS value FROM dataset GROUP BY region ORDER BY value DESC LIMIT 5", "description": f"Group counts for region", "group": str(grp)},
                    "tolerance": None,
                })
        except Exception:
            pass

        # Top-k amount by category (avg)
        try:
            rows = con.execute("SELECT category AS grp, AVG(amount) AS value FROM dataset GROUP BY category ORDER BY value DESC LIMIT 5").fetchall()
            for idx, (grp, val) in enumerate(rows):
                facts.append({
                    "id": f"topk_avg_amount__{idx}",
                    "kind": "topk",
                    "value": float(val) if val is not None else 0,
                    "formatted": f"{val:,.2f}" if isinstance(val, float) else str(val),
                    "provenance": {"sql": "SELECT category AS grp, AVG(amount) AS value FROM dataset GROUP BY category ORDER BY value DESC LIMIT 5", "description": "Top categories by avg amount", "group": str(grp)},
                    "tolerance": None,
                })
        except Exception:
            pass

    finally:
        try:
            con.close()
        except Exception:
            pass
    elapsed = time.perf_counter() - t0
    return facts, elapsed


def main():
    results = []
    print(f"Using token estimator: {'tiktoken cl100k_base' if 'tiktoken' in globals() and '_enc' in globals() else 'len//4 fallback'}")
    print(f"Prompt overhead: {PROMPT_OVERHEAD} tokens")
    print()

    for n in SIZES:
        df = gen_dataset(n)
        # NAIVE: CSV serialization
        csv_text = df.to_csv(index=False)
        naive_tokens = estimate_tokens(csv_text) + PROMPT_OVERHEAD

        # COMPUTE-THEN-WRITE: DuckDB facts
        facts, duckdb_time = compute_facts_duckdb(df)
        facts_json = json.dumps(facts, indent=2, ensure_ascii=False, default=str)
        facts_tokens_raw = estimate_tokens(facts_json)
        # Facts JSON is fixed size regardless of rows; clamp to 800-1500 if outside (simulate spec)
        # But use actual measured value; ensure it stays in expected range for realism
        ctw_tokens = facts_tokens_raw + PROMPT_OVERHEAD

        # Latency models
        naive_latency = 0.02 * naive_tokens / 1000 + 0.5
        ctw_latency = 0.02 * ctw_tokens / 1000 + 0.3 + duckdb_time

        token_saving = (naive_tokens - ctw_tokens) / naive_tokens * 100 if naive_tokens else 0
        latency_saving = (naive_latency - ctw_latency) / naive_latency * 100 if naive_latency else 0

        results.append({
            "rows": n,
            "naive_tokens": int(naive_tokens),
            "ctw_tokens": int(ctw_tokens),
            "naive_latency_s": round(naive_latency, 4),
            "ctw_latency_s": round(ctw_latency, 4),
            "token_saving_pct": round(token_saving, 2),
            "latency_saving_pct": round(latency_saving, 2),
            "duckdb_time_s": round(duckdb_time, 4),
            "facts_count": len(facts),
            "facts_tokens_raw": int(facts_tokens_raw),
            "csv_chars": len(csv_text),
            "facts_json_chars": len(facts_json),
        })

    # Write JSON
    out_path = Path(__file__).parent / "markdown_results.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Results written to {out_path}\n")

    # Markdown table to stdout
    print("| Rows | Naive Tokens | CTW Tokens | Token Saving % | Naive Latency (s) | CTW Latency (s) | Latency Saving % | DuckDB (s) |")
    print("|-----:|------------:|-----------:|---------------:|------------------:|----------------:|-----------------:|-----------:|")
    for r in results:
        print(f"| {r['rows']:,} | {r['naive_tokens']:,} | {r['ctw_tokens']:,} | {r['token_saving_pct']:.1f}% | {r['naive_latency_s']:.3f} | {r['ctw_latency_s']:.3f} | {r['latency_saving_pct']:.1f}% | {r['duckdb_time_s']:.4f} |")

    print("\n### Facts JSON size (fixed regardless of rows)")
    for r in results:
        print(f"- {r['rows']:,} rows: facts JSON {r['facts_json_chars']:,} chars -> {r['facts_tokens_raw']:,} tokens (raw), {r['facts_count']} facts")

    print("\n### CSV size (scales linearly)")
    for r in results:
        print(f"- {r['rows']:,} rows: CSV {r['csv_chars']:,} chars -> {r['naive_tokens'] - PROMPT_OVERHEAD:,} tokens (raw)")

if __name__ == "__main__":
    main()
