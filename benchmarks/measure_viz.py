"""Benchmark: NAIVE vs R-COMPUTE-THEN-WRITE for Visualization Tool."""
from __future__ import annotations

import json
import time
import random
from pathlib import Path

import pandas as pd
import duckdb

SIZES = [1000, 5000, 10000, 20000]
PROMPT_OVERHEAD_NAIVE = 600
PROMPT_OVERHEAD_CTW = 600
CATEGORIES = ["A", "B", "C", "D", "E"]

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def estimate_tokens(text: str) -> int:
        return len(_enc.encode(text))
    _estimator = "tiktoken cl100k_base"
except Exception:
    def estimate_tokens(text: str) -> int:
        return max(1, len(text) // 4)
    _estimator = "len//4 fallback"


def gen_dataset(n: int, seed: int = 42) -> pd.DataFrame:
    rng = random.Random(seed + n)
    categories = [rng.choice(CATEGORIES) for _ in range(n)]
    values = [round(rng.uniform(10.0, 1000.0), 2) for _ in range(n)]
    base_date = pd.Timestamp("2023-01-01")
    dates = [(base_date + pd.Timedelta(days=rng.randint(0, 730))).strftime("%Y-%m-%d") for _ in range(n)]
    df = pd.DataFrame({
        "category": categories,
        "value": values,
        "date": dates,
    })
    return df


def compute_facts_duckdb(df: pd.DataFrame) -> tuple[list[dict], float]:
    t0 = time.perf_counter()
    con = duckdb.connect(":memory:")
    try:
        con.register("dataset", df)
        facts: list[dict] = []

        # Scalar stats
        row = con.execute("SELECT COUNT(*) AS cnt, SUM(value) AS sum_v, AVG(value) AS avg_v, MIN(value) AS min_v, MAX(value) AS max_v FROM dataset").fetchone()
        cnt, sum_v, avg_v, min_v, max_v = row
        facts.append({"id": "count", "kind": "count", "value": int(cnt), "sql": "SELECT COUNT(*) FROM dataset"})
        facts.append({"id": "sum", "kind": "sum", "value": float(sum_v) if sum_v is not None else 0, "sql": "SELECT SUM(value) FROM dataset"})
        facts.append({"id": "avg", "kind": "avg", "value": float(avg_v) if avg_v is not None else 0, "sql": "SELECT AVG(value) FROM dataset"})
        facts.append({"id": "min", "kind": "min", "value": float(min_v) if min_v is not None else 0, "sql": "SELECT MIN(value) FROM dataset"})
        facts.append({"id": "max", "kind": "max", "value": float(max_v) if max_v is not None else 0, "sql": "SELECT MAX(value) FROM dataset"})

        # Group-by category
        rows = con.execute('SELECT category, SUM(value) AS sum_v, AVG(value) AS avg_v, COUNT(*) AS cnt FROM dataset GROUP BY category ORDER BY sum_v DESC').fetchall()
        for cat, s, a, c in rows:
            facts.append({"id": f"group_{cat}", "kind": "group_sum", "category": cat, "sum": float(s), "avg": float(a), "count": int(c)})

        # Optional: date trend (monthly avg) — limited to 12 rows to keep JSON small
        try:
            rows = con.execute("SELECT substr(date, 1, 7) AS month, AVG(value) AS avg_v, COUNT(*) AS cnt FROM dataset GROUP BY month ORDER BY month LIMIT 12").fetchall()
            for month, a, c in rows:
                facts.append({"id": f"trend_{month}", "kind": "trend", "month": month, "avg": float(a), "count": int(c)})
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
    print(f"Using token estimator: {_estimator}")
    print(f"Prompt overhead naive: {PROMPT_OVERHEAD_NAIVE}, ctw: {PROMPT_OVERHEAD_CTW}")
    print()

    for n in SIZES:
        df = gen_dataset(n)

        # NAIVE: CSV serialization + prompt overhead
        csv_text = df.to_csv(index=False)
        naive_tokens = estimate_tokens(csv_text) + PROMPT_OVERHEAD_NAIVE

        # CTW: DuckDB aggregates -> small JSON + prompt overhead
        facts, duckdb_time = compute_facts_duckdb(df)
        facts_json = json.dumps(facts, indent=2, ensure_ascii=False, default=str)
        facts_tokens_raw = estimate_tokens(facts_json)
        ctw_tokens = facts_tokens_raw + PROMPT_OVERHEAD_CTW

        # Latency models
        naive_latency = 0.02 * naive_tokens / 1000 + 0.6
        ctw_latency = 0.02 * ctw_tokens / 1000 + 0.35 + duckdb_time

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
        })

    # Write JSON
    out_path = Path(__file__).parent / "viz_results.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Results written to {out_path}\n")

    # Markdown table to stdout
    print("| Rows | Naive Tokens | CTW Tokens | Token Saving % | Naive Latency (s) | CTW Latency (s) | Latency Saving % | DuckDB (s) |")
    print("|-----:|------------:|-----------:|---------------:|------------------:|----------------:|-----------------:|-----------:|")
    for r in results:
        print(f"| {r['rows']:,} | {r['naive_tokens']:,} | {r['ctw_tokens']:,} | {r['token_saving_pct']:.1f}% | {r['naive_latency_s']:.3f} | {r['ctw_latency_s']:.3f} | {r['latency_saving_pct']:.1f}% | {r['duckdb_time_s']:.4f} |")

    print("\nDone.")


if __name__ == "__main__":
    main()
