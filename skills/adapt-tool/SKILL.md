---
name: adapt-tool
description: Adapt the Markdown Summary / Visualization tools to any repository
---

# Skill: adapt-tool

> One-command adaptation of `create_markdown_summary` + `create_visualization` to any repo.

## When to Use

- You have a new target repo and want the tools to work there
- Data sampling differs (random / stratified / reservoir / window)
- Extra arguments are needed (discount, LM counting, custom columns)
- Connectors differ (DB, API, file layout)

## Quick Start

```python
from repo_adapter import RepoAnalyzer, ToolAdapter

# 1. Analyze
profile = RepoAnalyzer("/path/to/target-repo").analyze()
print(profile.raw_notes)

# 2. Generate adapted tool
adapter = ToolAdapter.from_profile(profile)
path = adapter.write("./adapted")
print(f"Adapted tool at {path}")

# 3. Use it
import sys
sys.path.insert(0, "./adapted")
from adapted_tool import create_markdown_summary
import json
result = json.loads(create_markdown_summary.invoke({
    "datasets_json": json.dumps([{"kind": "inline_json", "name": "orders", "data": [{"amount": 100}]}]),
    "question": "Summarize total amount",
}))
print(result["markdown"])
```

## CLI

```powershell
python -m repo_adapter.cli --repo /path/to/target-repo --out ./adapted
python -m repo_adapter.cli --repo /path/to/target-repo --out ./adapted --tool-name create_markdown_summary
```

## What Gets Adapted

| Concern | How |
|---------|-----|
| Sampling | `SamplingConfig` (full/random/stratified/reservoir/window) injected into tool |
| Extra args | Auto-detected columns → optional kwargs on the tool |
| Connectors | Registry — register custom `Connector` subclasses |
| Facts | `fact_overrides` — custom SQL facts |
| LLM prompt | `llm_overrides` — domain-specific system prompt |

## Verify

```powershell
pip install -e ".[dev]"
pytest -q
python examples/demo.py
```
