---
name: build-tool
description: Build a new compute-then-write tool (like Markdown Summary) for any domain
---

# Skill: build-tool

> Build a new tool following the same architecture: **Engine computes → LLM narrates → Verifier enforces**.

## Architecture to Replicate

```
Datasets (connectors) → Normalizer → Profiler → DuckDB (push-down)
  → FactPlanner + compute_facts → facts JSON
  → LLM (one call, verbalizes facts only) → markdown
  → Verifier (regex + tolerance) → repair if needed
  → Sanitizer → {markdown, facts, warnings, meta}
```

## Steps

1. **Define schemas** (`models/schemas.py`) — `DataRef`, `Request`, `Response`, `Fact`
2. **Connectors** (`connectors/`) — subclass `Connector`, implement `fetch()`, register in `ConnectorRegistry`
3. **Normalizer** (`normalizer/`) — coerce types, handle nulls
4. **Profiler** (`profiler/`) — row/column stats, cardinality
5. **Engine** (`engine/duckdb_engine.py`) — reuse `DuckDBEngine` or wrap another engine
6. **Facts** (`facts/planner.py` + `facts/compute.py`) — `FactSpec` + SQL execution
7. **LLM** (`llm/`) — `LLMClient` + `SYSTEM_PROMPT` + `build_prompt()`
8. **Verifier** (`verifier/`) — `verify()` + `repair()`
9. **Sanitizer** (`sanitizer/`) — strip HTML/JS, redact columns
10. **Pipeline** (`engine/pipeline.py`) — orchestrate 1–9
11. **Tool** (`tools/`) — `@tool` wrapper with `invoke()` + fallback decorator
12. **Gateway** (`gateway/app.py`) — FastAPI `POST /v1/summarize`

## Using repo_adapter to Bootstrap

```python
from repo_adapter import RepoAnalyzer, ToolAdapter

profile = RepoAnalyzer("/path/to/repo").analyze()
adapter = ToolAdapter.from_profile(profile, tool_name="create_my_tool", target_module="my_tool")
adapter.write("./my_tool_pkg")
```

Then customize `facts/planner.py` and `llm/prompts.py` for your domain.

## Checklist

- [ ] `pytest -q` passes (MockLLM, no keys needed)
- [ ] `python examples/demo.py` produces verified markdown
- [ ] `meta.verified is True` (mechanical verifier, not LLM-judged)
- [ ] Sanitizer strips HTML/JS
- [ ] DeepAgent wiring works (`deepagents.create_deep_agent` + `tool.invoke`)
