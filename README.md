# Markdown Summary Tool — Technical Specification v1.0

> **Deterministic computation + LLM prose over large, untrusted, multi-dataset inputs**

80-page technical specification for `create_markdown_summary` — a compute-then-write system that turns large, multi-dataset service data into verified markdown.

## Architecture

**Engine computes → LLM narrates → Verifier enforces.**

- **DuckDB push-down** computes every number over the full datasets (no sampling for final values)
- **Small/cheap LLM** (one call) verbalizes pre-computed facts into fluent markdown
- **Mechanical verifier** checks every number in the prose against the fact set within tolerance
- **Sanitizer** strips dangerous markdown (raw HTML, `javascript:` URIs, event handlers)

## Documents

| File | Description |
|------|-------------|
| [`Markdown_Summary_Tool_Technical_Specification_v1.0.pdf`](./Markdown_Summary_Tool_Technical_Specification_v1.0.pdf) | Full 80-page spec (this tool) |
| [`Visualization_Tool_Technical_Specification.pdf`](./Visualization_Tool_Technical_Specification.pdf) | Sibling spec — Visualization Tool (reference) |
| [`build/`](./build/) | Source markdown parts (15) + `stitch.py` PDF builder |

## Spec Contents (21 sections)

1. Introduction & Scope · 2. Research Findings · 3. Decision Log (20 decisions) · 4. System Architecture · 5. Tool Input Spec · 6. Processing Pipeline (10 stages) · 7. Data Handling · 8. Summary Design · 9. Faithfulness & Verification · 10. Model Call Design · 11. Tool Output Spec · 12. Consistency & Quality · 13. Security & Privacy · 14. Errors & Warnings · 15. Testing & Evaluation (115-case harness) · 16. Operations & Observability · 17. Implementation Blueprint · 18. Worked Examples (8) · 19. Comparison · 20. Roadmap/Risks/Open Questions · 21. Appendices A–N

## Implementation

```powershell
pip install -e ".[dev]"
pytest -q                          # 16 tests
python examples/demo.py            # end-to-end demo
uvicorn markdown_summary_tool.gateway.app:app --reload  # API at /docs

# DeepAgent tools (both summary + visualization) — mock mode if no keys
python examples/deepagent_example.py
python examples/stress_test.py     # 10k orders + 1k products, 6 checks

# With a real LLM (OpenAI-compatible endpoint)
$env:API_BASE="https://api.example.com/v1"
$env:API_KEY="sk-..."
pip install -e ".[deepagent]"      # langchain-core + deepagents
python examples/deepagent_example.py  # uses model claude-fable-5.1
```

```
src/markdown_summary_tool/
  gateway/     FastAPI app (POST /v1/summarize, GET /health)
  models/      Pydantic v2 schemas (DataRef, SummaryRequest/Response, Fact)
  connectors/  inline_json / inline_csv / url (httpx + pagination)
  normalizer/  type coercion, null handling, date parsing
  profiler/    row/column stats, cardinality, 5-row sample
  engine/      DuckDB push-down + pipeline orchestration
  facts/       deterministic planner + SQL fact computation
  llm/         MockLLM + OpenAI-compatible client (API_BASE/API_KEY, claude-fable-5.1)
  verifier/    regex number extraction + mechanical verification + repair
  sanitizer/   HTML/URI/event-handler stripping + column redaction
  tools/       DeepAgent wrapper: create_markdown_summary (@tool fallback)
src/visualization_tool/
  tool.py      DeepAgent wrapper: create_visualization (DuckDB + Vega-Lite)
  models.py    VisualizationRequest/Response schemas
```

## Rebuild the PDF

```powershell
pip install reportlab pymupdf
python build/stitch.py
# → Markdown_Summary_Tool_Technical_Specification_v1.0.pdf (80 pages)
```

## Live Outputs (30 samples + dashboard)

All generated live via the 2 DeepAgent tools — not hand-written. Open directly or embed via iframe.

| Output | How to generate | What it is |
|--------|-----------------|------------|
| [`outputs/samples_30.html`](./outputs/samples_30.html) | `python outputs/generate_30_samples.py` | 15× `create_markdown_summary` + 15× `create_visualization` fired in parallel (ThreadPoolExecutor) — 15 verified markdown cards + 15 live Vega charts |
| [`outputs/samples_raw.json`](./outputs/samples_raw.json) | Same run | Raw JSON for all 30 calls — inspect `markdown`, `facts`, `chart_spec` |
| [`outputs/dashboard.html`](./outputs/dashboard.html) | `python outputs/generate_dashboard.py` | 6× `create_visualization` + 1× `create_markdown_summary` in parallel → one responsive grid + KPI row + verified summary |

```html
<iframe src="outputs/samples_30.html" width="100%" height="900" style="border:1px solid #1e293b;border-radius:12px"></iframe>
<iframe src="outputs/dashboard.html" width="100%" height="900" style="border:1px solid #1e293b;border-radius:12px"></iframe>
```

Single `create_visualization` = single chart by design; dashboard = N parallel calls stitched into one HTML (app layer). See [`AGENTS.md`](./AGENTS.md) and [`SKILL.md`](./SKILL.md) for verifiable agents/skills reference.

## Agents & Skills

* [`AGENTS.md`](./AGENTS.md) — The 2 tools, DeepAgent wiring, architecture, live outputs, and how to verify every claim (copy-paste commands).
* [`SKILL.md`](./SKILL.md) — What each tool can do, with example questions and which sample proves it.

## Repo Adapter — Adapt to Any Repo

Make the tools fit a new repo (different sampling, extra args, connectors, facts):

```powershell
# One-command adapt
python -m repo_adapter.cli --repo /path/to/target-repo --out ./adapted

# Or in Python
python -c "
from repo_adapter import RepoAnalyzer, ToolAdapter
profile = RepoAnalyzer('/path/to/repo').analyze()
print(profile.raw_notes)
ToolAdapter.from_profile(profile).write('./adapted')
"
# Use the adapted tool
python -c "
import sys, json; sys.path.insert(0,'./adapted')
from adapted_tool import create_markdown_summary
ds=json.dumps([{'kind':'inline_json','name':'t','data':[{'x':1},{'x':2}]}])
print(json.loads(create_markdown_summary.invoke({'datasets_json':ds,'question':'Summarize'}))['markdown'][:400])
"
```

| Component | Path | Purpose |
|-----------|------|---------|
| Analyzer | `src/repo_adapter/analyzer.py` | Scans data files, sampling hints, extra args, connectors |
| Adapter | `src/repo_adapter/adapter.py` | Generates adapted tool code (sampling + extra kwargs + fact overrides) |
| Sampling | `src/repo_adapter/sampling.py` | `full/random/stratified/reservoir/window` — deterministic via seed |
| Connectors | `src/repo_adapter/connectors.py` | Registry for custom DB/API connectors |
| CLI | `src/repo_adapter/cli.py` | `python -m repo_adapter.cli --repo <path> --out <dir>` |
| Agents | `agents/repo-adapter-agent.md`, `agents/sampling-agent.md`, `agents/argument-extension-agent.md` | Adaptation workflows |
| Skills | `skills/adapt-tool/`, `skills/analyze-repo/`, `skills/custom-sampling/`, `skills/extend-arguments/`, `skills/build-tool/` | One-command adapt, analyze, sampling, args, build |

Sampling override at call time: `options_json='{"sampling_strategy":"random","sample_size":2000}'`.

## License

Draft for engineering review — confidential.
