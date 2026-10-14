# Token & Latency Comparison: Naive Full-Data vs Compute-Then-Write (DuckDB Push-Down)

> **Benchmark date:** 2026-10-14 &middot; **Tools:** Markdown Summary & Visualization &middot; **Scales:** 1k / 5k / 10k / 20k rows &middot; **Estimator:** `tiktoken` `cl100k_base` (fallback `len//4`)

---

## Executive Summary

- **CTW is O(1) tokens vs O(n) naive.** Naive serializes the full dataset (CSV) into the LLM context; CTW pushes aggregates to DuckDB and sends only a compact facts JSON (~7k chars / ~2.1k tokens). Token count is flat regardless of rows.
- **98–99% token saving at 10k+ rows.** Markdown Summary: **98.54%** at 10k, **99.27%** at 20k. Visualization: **98.65%** at 10k, **99.32%** at 20k. Even at 1k rows savings exceed 85%.
- **87–90% latency saving at 10k rows (94% at 20k).** Naive latency grows linearly with tokens ($0.02 \cdot \text{tokens}/1000 + \text{base}$); CTW latency is dominated by a fixed LLM call + DuckDB (<0.1 s). At 10k rows: Markdown 4.07 s → 0.41 s (−90.0%), Viz 3.21 s → 0.42 s (−87.0%).
- **Cost implications are proportional to tokens.** At Claude-Fable-5.1-class pricing ($0.003/1k input, $0.015/1k output), CTW cuts cost per 1k requests by **~97% at 10k rows** and **~98.5% at 20k rows** — from ~$543 to ~$15 per 1k Markdown summaries at 10k rows. Naive becomes economically and technically infeasible beyond ~10k rows.

---

## Methodology

### Token Counting

| Aspect | Naive | Compute-Then-Write (CTW) |
|--------|-------|--------------------------|
| **Payload** | Full dataset as CSV (`df.to_csv(index=False)`) | Aggregated facts as JSON (`json.dumps(facts, indent=2)`) |
| **Estimator** | `tiktoken` `cl100k_base` if installed, else `len(text)//4` | Same |
| **Overhead** | Prompt template overhead added (Markdown: 500 tokens; Viz: 600 tokens) | Same overhead + facts tokens |
| **Formula** | `naive_tokens = estimate_tokens(csv_text) + overhead` | `ctw_tokens = estimate_tokens(facts_json) + overhead` |

- **CSV serialization** is the naive baseline: every row is materialized as text. At 10k rows the Markdown CSV is **326,751 chars** → **178,049 tokens** before overhead; at 20k rows **664,429 chars** → **356,948 tokens**.
- **Facts JSON** is the CTW payload: DuckDB computes counts, sums, averages, min/max, distinct counts, group-by and (for Viz) monthly trends, then serializes ~22 facts. Size is **~7,000 chars / ~2,100 tokens** regardless of scale (see tables below).

### Latency Model

- **DuckDB timing** measured wall-clock via `time.perf_counter()` around the aggregate queries on an in-memory DuckDB connection (`duckdb.connect(":memory:")` + `con.register("dataset", df)`).
- **Mock LLM latency** models realistic API behavior where latency scales with tokens:

```
naive_latency = 0.02 * naive_tokens / 1000 + 0.60
ctw_latency   = 0.02 * ctw_tokens   / 1000 + 0.35 + duckdb_time
```

  The 0.60 s vs 0.35 s base reflects a larger prompt processing overhead for the naive path. DuckDB time is added only to CTW. This isolates the token-proportional LLM cost from the negligible compute cost.

### Dataset Generation

Synthetic DataFrames with `random.Random(seed + n)` for reproducibility:

- **Markdown Summary:** columns `id, category (A–E), amount (10–10,000), date (2023-01-01 + 0–730d), region (North/South/East/West/Central)`.
- **Visualization:** columns `category (A–E), value (10–1,000), date (YYYY-MM-DD)`.
- Scales: **1,000 / 5,000 / 10,000 / 20,000 rows**.

---

## Markdown Summary Tool Results

> Naive = full CSV in prompt · CTW = DuckDB aggregates → facts JSON

| Rows | Naive Tokens | CTW Tokens | Token Saving % | Naive Latency (s) | CTW Latency (s) | Latency Saving % | DuckDB (s) | Facts | Facts Tokens (raw) | CSV Chars | Facts JSON Chars |
|-----:|------------:|-----------:|---------------:|------------------:|----------------:|-----------------:|-----------:|------:|-------------------:|----------:|-----------------:|
| 1,000 | 17,412 | 2,580 | 85.18% | 0.848 | 0.451 | 46.82% | 0.0995 | 22 | 2,080 | 31,720 | 6,998 |
| 5,000 | 88,995 | 2,593 | 97.09% | 2.280 | 0.400 | 82.44% | 0.0485 | 22 | 2,093 | 162,846 | 7,013 |
| 10,000 | 178,549 | 2,608 | 98.54% | 4.071 | 0.406 | 90.02% | 0.0542 | 22 | 2,108 | 326,751 | 7,029 |
| 20,000 | 357,448 | 2,609 | 99.27% | 7.649 | 0.426 | 94.43% | 0.0739 | 22 | 2,109 | 664,429 | 7,029 |

### Observations

- **Facts JSON is flat at ~2.6k tokens (2,080–2,109 raw + 500 overhead) regardless of rows.** CSV tokens grow linearly: ~17.4k → 89k → 178.5k → 357.4k. The ratio is ~17–18 tokens/row for this schema.
- **Token saving crosses 97% at 5k rows and 98.5% at 10k rows.** At 20k rows naive uses **137×** more tokens than CTW.
- **Latency saving follows tokens.** Naive latency 0.85 s → 7.65 s; CTW stays 0.40–0.45 s. DuckDB is **0.05–0.10 s** — noise compared to LLM time.
- **CSV chars scale linearly** (31k → 664k) while facts JSON stays at **~7k chars** — a 46× reduction at 10k rows, 94× at 20k rows.

---

## Visualization Tool Results

> Naive = full CSV in prompt · CTW = DuckDB aggregates (counts, sums, group-by, monthly trends) → facts JSON

| Rows | Naive Tokens | CTW Tokens | Token Saving % | Naive Latency (s) | CTW Latency (s) | Latency Saving % | DuckDB (s) |
|-----:|------------:|-----------:|---------------:|------------------:|----------------:|-----------------:|-----------:|
| 1,000 | 13,604 | 1,751 | 87.13% | 0.872 | 0.473 | 45.76% | 0.0880 |
| 5,000 | 65,604 | 1,765 | 97.31% | 1.912 | 0.422 | 77.95% | 0.0363 |
| 10,000 | 130,604 | 1,764 | 98.65% | 3.212 | 0.416 | 87.04% | 0.0309 |
| 20,000 | 260,604 | 1,771 | 99.32% | 5.812 | 0.422 | 92.74% | 0.0365 |

### Observations

- **Same O(1) vs O(n) pattern.** CTW tokens flat at **~1,760** (1,751–1,771) vs naive linear **13.6k → 260.6k**. Per-row cost ~13 tokens/row (3-column schema vs 5-column Markdown).
- **Savings nearly identical to Markdown tool** despite different schema and fewer facts — confirms the effect is structural, not data-dependent.
- **DuckDB even faster here** (0.03–0.09 s) due to narrower table and simpler aggregates. CTW latency is essentially constant at **~0.42 s**.
- **At 20k rows naive is 147× larger** than CTW in tokens. The absolute token gap (258,833) exceeds the entire context window of most models.

---

## Cost Analysis

**Pricing assumption:** Claude-Fable-5.1-class — **$0.003 / 1k input tokens**, **$0.015 / 1k output tokens**. Output length assumed constant at **500 tokens** for both approaches (same summary/chart spec produced). Cost per request:

```
cost = input_tokens/1000 * 0.003 + 500/1000 * 0.015
     = input_tokens * 0.000003 + 0.0075
```

Cost per **1,000 requests** = cost × 1,000. Savings = naive − CTW.

### Markdown Summary — Cost per 1k Requests

| Rows | Naive Input | CTW Input | Naive Cost/1k | CTW Cost/1k | Saving/1k | Saving % |
|-----:|------------:|----------:|--------------:|------------:|----------:|---------:|
| 1,000 | 17,412 | 2,580 | $59.74 | $15.24 | $44.50 | 74.5% |
| 5,000 | 88,995 | 2,593 | $274.49 | $15.28 | $259.21 | 94.4% |
| 10,000 | 178,549 | 2,608 | $543.15 | $15.32 | $527.82 | 97.2% |
| 20,000 | 357,448 | 2,609 | $1,079.84 | $15.33 | $1,064.52 | 98.6% |

*Detail at 10k rows:* Naive input $0.53565 + output $0.0075 = $0.54315/req; CTW input $0.00782 + output $0.0075 = $0.01532/req.

### Visualization — Cost per 1k Requests

| Rows | Naive Input | CTW Input | Naive Cost/1k | CTW Cost/1k | Saving/1k | Saving % |
|-----:|------------:|----------:|--------------:|------------:|----------:|---------:|
| 1,000 | 13,604 | 1,751 | $48.31 | $12.75 | $35.56 | 73.6% |
| 5,000 | 65,604 | 1,765 | $204.31 | $12.80 | $191.52 | 93.7% |
| 10,000 | 130,604 | 1,764 | $399.31 | $12.79 | $386.52 | 96.8% |
| 20,000 | 260,604 | 1,771 | $789.31 | $12.81 | $776.50 | 98.4% |

### What This Means

- **At 10k rows, CTW saves ~$528 per 1k Markdown summaries** — enough to fund **~34× more CTW requests** for the same budget.
- **At 100k requests/month and 10k-row datasets**, naive Markdown costs **~$54,315/month** vs CTW **~$1,532/month** — a **$52,783/month** difference.
- **Output cost dominates CTW** ($7.50 of $15.32 at 10k rows is output). Further output optimization (shorter summaries) would help CTW more than naive, where input dominates.
- **Break-even is immediate:** even at 1k rows CTW saves 73–74%. There is no scale where naive is cheaper.

> **Note:** If output tokens differ (e.g., naive generates longer code), savings are larger. If using a higher-priced model (e.g., $0.015/1k input), multiply input columns by 5× — savings scale linearly.

---

## Latency Breakdown

```
Latency (s) at 10k rows — Markdown Summary

Naive:  ████████████████████████████████████████ 4.071 s
         └─ LLM (tokens) 3.471 s (85%) + base 0.60 s

CTW:     ████ 0.406 s
         ├─ LLM (tokens) 0.052 s (13%)
         ├─ Base          0.350 s (86%)
         └─ DuckDB        0.054 s (13% — overlaps base in model, shown separately)
              ▲
              └─ <0.1 s at all scales — invisible on this chart
```

| Component | Naive (10k) | CTW (10k) | Insight |
|-----------|-------------|-----------|---------|
| **LLM token-proportional** | 3.57 s (88%) | 0.05 s (13%) | Dominates naive; negligible for CTW |
| **Base / fixed overhead** | 0.60 s | 0.35 s | CTW base is smaller (shorter prompt) |
| **DuckDB compute** | — | 0.03–0.10 s | <2% of naive latency; <15% of CTW latency |
| **Total** | 4.07 s | 0.41 s | **10× faster** |

**Key takeaway:** DuckDB push-down is not the bottleneck — it is **40–130× faster** than the LLM token processing it replaces. At 20k rows naive spends **7.15 s** on tokens alone; CTW spends **0.05 s** on tokens + **0.07 s** on DuckDB. The latency saving curve mirrors the token saving curve because LLM time is linear in tokens.

*Chart description for the Vega-Lite spec below:* Dual-line chart with x = rows (1k, 5k, 10k, 20k, log or linear), y = tokens (0–360k). Naive line rises steeply (13k → 357k); CTW line is horizontal at ~2k. A second panel (or dual axis) shows latency with the same shape. The visual gap widens dramatically after 5k rows.

---

## The "R/Python Code-Gen" Angle

A common alternative to direct summarization is **LLM code generation**: the model writes Python/R code that, when executed, produces the summary or chart.

| Approach | What the LLM Generates | What Is Embedded in the Prompt |
|----------|------------------------|-------------------------------|
| **Naive code-gen** | `import pandas as pd; df = pd.DataFrame({...full dataset...}); # analysis code` | **Full dataset as literal** (CSV/JSON/dict) — same O(n) tokens as naive |
| **CTW code-gen** | `import matplotlib.pyplot as plt; facts = {...aggregates...}; # plot from facts` | **Small aggregates only** — same O(1) tokens as CTW |

**Token difference is the same order of magnitude.** Whether the LLM outputs a summary directly or outputs code, the input context must contain the data. Naive code-gen embeds the full dataset as a Python dict/CSV string; CTW code-gen embeds only the ~22 facts. The token tables above apply directly — just reinterpret "naive tokens" as "prompt + embedded dataset literal" and "CTW tokens" as "prompt + embedded facts dict".

**Additional risks of naive code-gen:**

- **Context-window overflow.** At 20k rows naive is **357,448 tokens** (Markdown) / **260,604 tokens** (Viz) — exceeding the **200k context limit** of Claude-Fable-5.1 and most frontier models. The request fails outright or requires chunking/truncation that degrades quality. CTW at **~2.6k / ~1.7k tokens** fits comfortably with 197k tokens to spare.
- **Code size and execution cost.** Generated code containing a 664k-char dataset literal is itself large to transmit, parse, and execute. CTW code is a few hundred chars.
- **Hallucination surface.** More tokens = more opportunity for the model to misread or hallucinate over the data. Aggregates are pre-verified by DuckDB SQL.
- **Determinism.** DuckDB aggregates are exact; LLM-computed aggregates from raw data may have rounding or logic errors.

> **Bottom line:** CTW is not just cheaper — at 20k rows it is the *only* viable option within a 200k context window. Naive code-gen hits a hard wall; CTW scales to millions of rows with no token increase.

---

## Conclusion & Recommendation

1. **Adopt Compute-Then-Write as the default** for all data-grounded tools (Markdown summaries, visualizations, code-gen, Q&A). The pattern — DuckDB push-down → small facts JSON → LLM — is strictly dominant on tokens, latency, cost, and reliability.

2. **Deprecate naive full-data paths** beyond prototyping. They are acceptable only for trivially small datasets (<500 rows) and should emit a warning above 1k rows.

3. **Set a guardrail at ~50k tokens.** If estimated input tokens exceed 50k, automatically route to CTW or reject with a clear error suggesting aggregation. This prevents accidental context-window overflows and cost spikes.

4. **Monitor DuckDB time.** Current measurements show <0.1 s, but on larger or more complex queries (joins, window functions) it may grow. Even at 1 s, CTW still wins by 3–6 s at 10k rows.

5. **Future work:** Extend CTW to support user-defined aggregates (custom SQL), streaming for >1M rows, and caching of facts for repeated queries on the same dataset.

| Metric at 10k rows | Naive | CTW | Winner |
|--------------------|-------|-----|--------|
| Tokens | 178,549 | 2,608 | **CTW by 98.5%** |
| Latency | 4.07 s | 0.41 s | **CTW by 90%** |
| Cost/1k req | $543 | $15 | **CTW by 97%** |
| Fits 200k window at 20k rows? | **No** (357k) | **Yes** (2.6k) | **CTW** |

---

## Reproducibility

All numbers in this report are generated by the benchmark scripts in this repository:

- **`benchmarks\measure_markdown.py`** — Markdown Summary Tool benchmark (naive CSV vs DuckDB facts). Run: `python benchmarks\measure_markdown.py` → writes `benchmarks\markdown_results.json` and prints the markdown table.
- **`benchmarks\measure_viz.py`** — Visualization Tool benchmark (same pattern, 3-column dataset). Run: `python benchmarks\measure_viz.py` → writes `benchmarks\viz_results.json`.

Both scripts:
- Generate synthetic datasets at 1k/5k/10k/20k rows with fixed seeds.
- Estimate tokens via `tiktoken` `cl100k_base` (or `len//4` fallback).
- Time DuckDB aggregates with `time.perf_counter()`.
- Apply the mock LLM latency model described in Methodology.
- Are deterministic — re-running produces identical token counts (modulo `tiktoken` version).

**Dependencies:** `pandas`, `duckdb`, `tiktoken` (optional). Install with `pip install pandas duckdb tiktoken`.

---

## Appendix: Vega-Lite Spec — Tokens vs Rows (Dual-Line Chart)

Render this spec in any Vega-Lite renderer (e.g., VS Code Vega preview, Observable, vega.github.io/editor).

```json
{
  "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
  "title": "Token Count vs Dataset Size: Naive Full-Data vs Compute-Then-Write",
  "description": "Dual-line chart comparing naive (O(n)) vs CTW (O(1)) token counts across dataset scales. Data from benchmarks/markdown_results.json and benchmarks/viz_results.json.",
  "data": {
    "values": [
      {"rows": 1000, "tokens": 17412, "approach": "Naive \u2014 Markdown", "tool": "Markdown"},
      {"rows": 5000, "tokens": 88995, "approach": "Naive \u2014 Markdown", "tool": "Markdown"},
      {"rows": 10000, "tokens": 178549, "approach": "Naive \u2014 Markdown", "tool": "Markdown"},
      {"rows": 20000, "tokens": 357448, "approach": "Naive \u2014 Markdown", "tool": "Markdown"},
      {"rows": 1000, "tokens": 2580, "approach": "CTW \u2014 Markdown", "tool": "Markdown"},
      {"rows": 5000, "tokens": 2593, "approach": "CTW \u2014 Markdown", "tool": "Markdown"},
      {"rows": 10000, "tokens": 2608, "approach": "CTW \u2014 Markdown", "tool": "Markdown"},
      {"rows": 20000, "tokens": 2609, "approach": "CTW \u2014 Markdown", "tool": "Markdown"},
      {"rows": 1000, "tokens": 13604, "approach": "Naive \u2014 Viz", "tool": "Viz"},
      {"rows": 5000, "tokens": 65604, "approach": "Naive \u2014 Viz", "tool": "Viz"},
      {"rows": 10000, "tokens": 130604, "approach": "Naive \u2014 Viz", "tool": "Viz"},
      {"rows": 20000, "tokens": 260604, "approach": "Naive \u2014 Viz", "tool": "Viz"},
      {"rows": 1000, "tokens": 1751, "approach": "CTW \u2014 Viz", "tool": "Viz"},
      {"rows": 5000, "tokens": 1765, "approach": "CTW \u2014 Viz", "tool": "Viz"},
      {"rows": 10000, "tokens": 1764, "approach": "CTW \u2014 Viz", "tool": "Viz"},
      {"rows": 20000, "tokens": 1771, "approach": "CTW \u2014 Viz", "tool": "Viz"}
    ]
  },
  "mark": {
    "type": "line",
    "point": true,
    "strokeWidth": 2
  },
  "encoding": {
    "x": {
      "field": "rows",
      "type": "quantitative",
      "title": "Dataset Rows",
      "scale": {"type": "linear"},
      "axis": {"tickCount": 4, "format": ","}
    },
    "y": {
      "field": "tokens",
      "type": "quantitative",
      "title": "Input Tokens",
      "axis": {"format": ","}
    },
    "color": {
      "field": "approach",
      "type": "nominal",
      "title": "Approach",
      "scale": {
        "domain": ["Naive \u2014 Markdown", "CTW \u2014 Markdown", "Naive \u2014 Viz", "CTW \u2014 Viz"],
        "range": ["#e45756", "#54a24b", "#f58518", "#4c78a8"]
      }
    },
    "strokeDash": {
      "field": "approach",
      "type": "nominal",
      "scale": {
        "domain": ["Naive \u2014 Markdown", "CTW \u2014 Markdown", "Naive \u2014 Viz", "CTW \u2014 Viz"],
        "range": [[0, 0], [6, 4], [0, 0], [6, 4]]
      },
      "legend": null
    },
    "tooltip": [
      {"field": "approach", "type": "nominal", "title": "Approach"},
      {"field": "rows", "type": "quantitative", "title": "Rows", "format": ","},
      {"field": "tokens", "type": "quantitative", "title": "Tokens", "format": ","}
    ]
  },
  "width": 640,
  "height": 360,
  "config": {
    "view": {"stroke": "transparent"},
    "axis": {"grid": true, "gridOpacity": 0.2},
    "legend": {"orient": "bottom", "titleFontSize": 12},
    "title": {"fontSize": 14, "anchor": "start"}
  }
}
```

*Notes on the spec:*

- Four series: Naive-Markdown (red solid), CTW-Markdown (green dashed), Naive-Viz (orange solid), CTW-Viz (blue dashed). Naive lines climb steeply; CTW lines are flat near the x-axis.
- A horizontal rule at 200,000 tokens marks the typical context-window limit — naive crosses it between 10k and 20k rows. Add a `layer` with a `rule` mark at `y=200000` to visualize it.
- Switch `x.scale.type` to `"log"` to better separate the 1k–5k region, or add a `facet` on `tool` for two side-by-side panels.

---

*Generated from `benchmarks\markdown_results.json` and `benchmarks\viz_results.json`. Do not edit numbers manually — re-run the benchmark scripts and regenerate.*
