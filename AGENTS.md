# Agents & Skills — Verifiable Reference

> **Exactly 2 tools. Everything below is runnable and verifiable — no mocks hidden as real.**

## 1. The 2 Tools (and only 2)

| # | Tool | Module | What it does | Input | Output |
|---|------|--------|--------------|-------|--------|
| 1 | `create_markdown_summary` | `src/markdown_summary_tool/tools/summarize_tool.py` | **NLP** — DuckDB computes facts over full data → LLM verbalizes facts JSON → mechanical verifier checks numbers → sanitizer strips HTML/JS → verified markdown | `datasets_json` (JSON array of `DataRef`), `question` (string), `options_json` (optional) | JSON string: `{markdown, facts, warnings, meta:{verified, fact_count, elapsed_ms}}` |
| 2 | `create_visualization` | `src/visualization_tool/tool.py` | **Charts/HTML** — DuckDB aggregates → Vega-Lite spec → `vega-embed` renders | `datasets_json`, `question`, `chart_type` (`auto/bar/line/pie/scatter`), `options_json` (`width,height,max_rows`) | JSON string: `{chart_spec (Vega-Lite), facts, warnings, meta:{chart_type,x_field,y_field,row_count}}` |

**Single `create_visualization` = single chart by design.** Dashboard = N parallel calls stitched into one HTML grid (app layer, not tool layer).

## 2. How to Verify (copy-paste)

```powershell
# 0) Install
pip install -e ".[dev]"

# 1) Unit tests — 16 tests, no API keys needed (MockLLM)
python -m pytest -q
# Expected: 16 passed

# 2) Stress test — 10k orders + 1k products, 6 checks, MockLLM
python examples/stress_test.py
# Expected: 6/6 PASS, ~3s, facts verified

# 3) DeepAgent both-tools demo (mock mode if no keys)
python examples/deepagent_example.py
# Expected: Tools: ['create_markdown_summary','create_visualization'], verified True, Vega spec

# 4) 30 live samples — 15 MD + 15 VZ in parallel (ThreadPoolExecutor)
python outputs/generate_30_samples.py
# Expected: 15 MD verified True + 15 VZ valid Vega specs → outputs/samples_30.html + samples_raw.json

# 5) Dashboard — 6 viz + 1 md in parallel → one HTML
python outputs/generate_dashboard.py
# Expected: outputs/dashboard.html (6 charts + summary + KPIs)

# 6) With real LLM (OpenAI-compatible)
$env:API_BASE="https://api.example.com/v1"
$env:API_KEY="sk-..."
pip install -e ".[deepagent]"   # langchain-core + deepagents
python examples/deepagent_example.py  # uses model claude-fable-5.1 via get_llm_client()
```

## 3. DeepAgent Wiring (verifiable)

```python
from deepagents import create_deep_agent
from markdown_summary_tool.tools.summarize_tool import create_markdown_summary
from visualization_tool.tool import create_visualization

agent = create_deep_agent(
    model="claude-fable-5.1",
    tools=[create_markdown_summary, create_visualization],
    system_prompt="You are a data assistant with two tools: create_markdown_summary (text) and create_visualization (charts).",
)
# Both tools expose langchain_core @tool interface: .name, .description, .args_schema, .invoke
# Fallback decorator in each tool.py mimics @tool when langchain_core not installed.
```

`get_llm_client()` in `src/markdown_summary_tool/llm/client.py`:
- `API_BASE` + `API_KEY` set → `OpenAICompatibleClient(base_url=API_BASE, model=claude-fable-5.1)` (Authorization: ******)
- Otherwise → `MockLLMClient` (deterministic, interpolates facts into markdown — no API call)
- `DEFAULT_MODEL = "claude-fable-5.1"`

## 4. Architecture (compute-then-write)

```
Datasets (inline_json / inline_csv / url) 
  → Connectors → Normalizer → Profiler → DuckDB (push-down, full data, no sampling for final values)
  → FactPlanner + compute_facts (SQL) → facts JSON
  → LLM (one call, verbalizes facts only) → markdown
  → Verifier (regex number extraction, tolerance check) → repair if needed
  → Sanitizer (strips raw HTML, javascript: URIs, event handlers, redacted columns)
  → {markdown, facts, warnings, meta}
```

Visualization: same DuckDB path → `_compute_aggregates` (group_by SUM/COUNT) → `_build_vega_spec` → Vega-Lite JSON → `vega-embed` in HTML.

## 5. Live Outputs (generated, not hand-written)

| File | How generated | What to check |
|------|---------------|---------------|
| `outputs/samples_30.html` | `python outputs/generate_30_samples.py` — 30 parallel tool calls | 15 MD cards (verified ✓, facts JSON) + 15 VZ cards (live Vega charts) |
| `outputs/samples_raw.json` | Same run | Raw JSON for all 30 calls — inspect `markdown`, `facts`, `chart_spec` |
| `outputs/dashboard.html` | `python outputs/generate_dashboard.py` — 7 parallel calls | 6-chart grid + KPI row + verified summary, single HTML, iframe-ready |
| `outputs/generate_30_samples.py` | Generator script | ThreadPoolExecutor(15), seeded RNG, deterministic datasets |
| `outputs/generate_dashboard.py` | Generator script | ThreadPoolExecutor(7), same pattern |

Embed anywhere:
```html
<iframe src="outputs/samples_30.html" width="100%" height="900" style="border:1px solid #1e293b;border-radius:12px"></iframe>
<iframe src="outputs/dashboard.html" width="100%" height="900" style="border:1px solid #1e293b;border-radius:12px"></iframe>
```

## 6. Skills / What Each Tool Is Good For

**`create_markdown_summary` skills:**
- Regional/category/status/time breakdowns, top-K, concentration, outlier/tail, cross-tabs, multi-dataset joins, full audits
- Handles 2k–10k rows, 3 datasets, nulls, redaction, locale formatting
- Hard queries: customer concentration, discount impact, seasonality, skew — all via deterministic SQL facts

**`create_visualization` skills:**
- `bar` (grouped SUM/COUNT), `line` (trend over time), `pie` (share), `scatter` (correlation), `auto` (heuristic)
- Heuristic: first string col = x, first numeric = y; scatter needs 2 numerics; bar/pie do `SUM(y) GROUP BY x`
- Dashboard = N `create_visualization` calls + stitch Vega specs into one HTML grid

## 7. Test Report

See [TESTING_REPORT.md](./TESTING_REPORT.md) — 16 pytest + 6 stress checks + DeepAgent live checks, all green. Re-run with `python -m pytest -q`.

## 8. No Hidden Mocks

- `MockLLMClient` is explicit and only used when `API_BASE`/`API_KEY` unset. It interpolates `facts[].formatted` into markdown — never invents numbers.
- With real env vars, `OpenAICompatibleClient` calls `POST {API_BASE}/chat/completions` with `model=claude-fable-5.1`, `temperature=0.2`, `Authorization: ******`.
- Verifier is mechanical (regex + tolerance), not LLM-based.
- All numbers in markdown are checked against `facts` — hallucinations fail verification and trigger repair.
