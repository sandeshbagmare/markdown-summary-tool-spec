# Skills — What the 2 Tools Can Do (Verifiable)

> Run the commands to verify each skill. No skill is claimed without a runnable check.

## Tool 1: `create_markdown_summary` — NLP / Verified Markdown

**Module:** `src/markdown_summary_tool/tools/summarize_tool.py` · **Pipeline:** `src/markdown_summary_tool/engine/pipeline.py`

| Skill | Example question | Verify |
|-------|------------------|--------|
| Regional breakdown | "Summarize total revenue, average order value, and count by region. Highlight top region." | `python outputs/generate_30_samples.py` → MD-01 |
| Category profitability | "Analyze total amount and average discount by category." | MD-02 |
| Customer concentration (hard) | "Top 5 customers by spend, share of revenue, long-tail?" | MD-03 |
| Multi-dataset (orders+products) | "Summarize orders and products together: compare categories on price/stock/rating." | MD-04, MD-13 |
| Time trend | "Revenue and volume by month. Peak/lowest with figures." | MD-05 |
| Discount impact (hard) | "Average amount by discount bucket, correlation?" | MD-06 |
| Status & returns | "Break down by shipped/pending/cancelled/returned. Revenue at risk?" | MD-07 |
| Quantity vs amount | "Average quantity, total units, amount per unit by region." | MD-08 |
| Supplier & stock risk | "Stock and price by supplier/category. Flag low-stock high-price." | MD-09 |
| Outlier & tail (very hard) | "Top 1% threshold, max order, top 10 share, skew." | MD-10 |
| Cross-tab (hard) | "Revenue by region×category. Strongest/weakest cell?" | MD-11 |
| Rating vs price | "Rating and price by category. Correlation?" | MD-12 |
| 3-dataset stress | "Summarize orders+products+sales together." | MD-13 (66 facts) |
| Seasonality (hard) | "Busiest month, avg amount by month, seasonal pattern?" | MD-14 |
| Full audit (very hard) | "Row counts, nulls, distincts, totals, anomalies across datasets." | MD-15 (54 facts) |

**Guarantees:** DuckDB computes every number over full data (no sampling for final values) → LLM verbalizes facts JSON only → verifier checks numbers within tolerance → sanitizer strips HTML/JS. `meta.verified` is mechanical, not LLM-judged.

## Tool 2: `create_visualization` — Charts / Vega-Lite

**Module:** `src/visualization_tool/tool.py`

| Skill | `chart_type` | Heuristic | Verify |
|-------|--------------|-----------|--------|
| Bar (grouped SUM) | `bar` | `SUM(numeric) GROUP BY string`, top 20 | VZ-01, VZ-05, VZ-06, VZ-10, VZ-12 |
| Line (trend) | `line` | x=nominative (month/date), y=quantitative | VZ-02, VZ-07, VZ-13 |
| Pie (share) | `pie` | theta=quantitative, color=nominal | VZ-03, VZ-08, VZ-14 |
| Scatter (correlation) | `scatter` | Needs 2 numeric cols, 100 points | VZ-04, VZ-09, VZ-15 |
| Auto | `auto` | Infers from question: trend→line, share→pie, scatter→scatter, else bar | VZ-11 |

**Dashboard skill:** Call `create_visualization` N times in parallel, collect `chart_spec`s, stitch into one HTML grid with `vega-embed`. See `outputs/generate_dashboard.py` (6 charts + 1 summary → `outputs/dashboard.html`).

## How to Check Any Skill

```powershell
# Single skill check — markdown
python -c "
import json, sys; sys.path.insert(0,'src')
from markdown_summary_tool.tools.summarize_tool import create_markdown_summary
ds=json.dumps([{'kind':'inline_json','name':'orders','data':[{'region':'East','amount':100},{'region':'West','amount':200}]}])
print(json.loads(create_markdown_summary.invoke({'datasets_json':ds,'question':'Summarize total amount by region'}))['markdown'][:500])
"

# Single skill check — visualization
python -c "
import json, sys; sys.path.insert(0,'src')
from visualization_tool.tool import create_visualization
ds=json.dumps([{'kind':'inline_json','name':'orders','data':[{'region':'East','amount':100},{'region':'West','amount':200}]}])
print(json.loads(create_visualization.invoke({'datasets_json':ds,'question':'Bar chart of amount by region','chart_type':'bar'}))['chart_spec'])
"

# Full verification
python -m pytest -q                          # 16 tests
python outputs/generate_30_samples.py        # 30 live samples → outputs/samples_30.html
python outputs/generate_dashboard.py         # dashboard → outputs/dashboard.html
```

## Limits (honest)

- `create_visualization` is single-chart per call; dashboard is app-layer composition.
- `create_markdown_summary` uses one LLM call to verbalize facts — not for free-form chat.
- Large datasets: `options.max_rows` caps rows; DuckDB handles 10k+ rows in <1s (see stress test).
- URL datasets require `httpx` and network; `connector` kind is stubbed (warning + skip).
