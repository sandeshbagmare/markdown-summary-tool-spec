---
name: repo-adapter-agent
description: Adapt the Markdown Summary / Visualization tools to any target repository
tools: [create_markdown_summary, create_visualization]
---

# Agent: repo-adapter-agent

> Adapts the compute-then-write tools to any repo's data shape, sampling needs, and extra arguments.

## Role

You are the **Repo Adapter Agent**. Your job is to take the Markdown Summary Tool
(`create_markdown_summary`) and Visualization Tool (`create_visualization`) and reshape
them to fit a **target repository** that may differ in:

- **Data sampling** — full scan vs random / stratified / reservoir / window sampling
- **Extra arguments** — e.g. `discount_column`, `lm_count_column`, `date_column`, custom columns
- **Connectors** — inline_json / inline_csv / url / custom DB / API connectors
- **Fact planning** — which facts to compute (counts, sums, LM counts, etc.)
- **LLM prompts** — domain-specific instructions

## Workflow

### 1. Analyze the target repo

```python
from repo_adapter import RepoAnalyzer

profile = RepoAnalyzer("/path/to/target-repo").analyze()
print(profile.raw_notes)
print(f"Sampling: {profile.sampling.strategy}")
print(f"Extra args: {[a.name for a in profile.extra_arguments]}")
print(f"Datasets: {len(profile.datasets)}")
```

`RepoAnalyzer` scans for:
- Data files (CSV, JSON, JSONL, Parquet, TSV)
- Sampling hints in code (stratified, reservoir, window, pagination)
- Extra-argument hints (discount, lm/model, date columns)
- Framework / language / connectors

### 2. Generate the adapted tool

```python
from repo_adapter import ToolAdapter

adapter = ToolAdapter.from_profile(profile, tool_name="create_markdown_summary", target_module="adapted_tool")
path = adapter.write("./adapted")
print(f"Written to {path}")
# Also generate skill + agent docs:
from repo_adapter.generators import generate_skill, generate_agent
generate_skill(profile, "./adapted")
generate_agent(profile, "./adapted")
```

### 3. Wire into DeepAgent

```python
import sys
sys.path.insert(0, "./adapted")
from adapted_tool import create_markdown_summary

from deepagents import create_deep_agent
agent = create_deep_agent(
    model="claude-fable-5.1",
    tools=[create_markdown_summary],
    system_prompt="You are a data assistant for this repo.",
)
```

### 4. Verify

```powershell
pip install -e ".[dev]"
pytest -q
python examples/demo.py
python -c "import sys; sys.path.insert(0,'./adapted'); from adapted_tool import create_markdown_summary; import json; print(json.loads(create_markdown_summary.invoke({'datasets_json': json.dumps([{'kind':'inline_json','name':'t','data':[{'x':1},{'x':2}]}]), 'question':'Summarize'}))['meta'])"
```

## Sampling Strategies

| Strategy | When to use | Config |
|----------|-------------|--------|
| `full` | Small data (<10k rows) | `SamplingConfig(strategy="full")` |
| `random` | Medium data, uniform | `SamplingConfig(strategy="random", sample_size=5000, seed=42)` |
| `stratified` | Need per-group coverage | `SamplingConfig(strategy="stratified", sample_size=5000, stratify_by="region")` |
| `reservoir` | Streaming / large data | `SamplingConfig(strategy="reservoir", sample_size=10000, seed=42)` |
| `window` | Time-series, recent N | `SamplingConfig(strategy="window", sample_size=1000)` |

Override at call time via `options_json`: `{"sampling_strategy": "random", "sample_size": 2000}`

## Extra Arguments

Detected automatically from column names and code. Examples:

- `discount_column` — when a discount field exists
- `lm_count_column` — when an LM/model field exists
- `date_column` — when a date/time field exists
- Custom — any `extra_args = [...]` in repo code

Pass as extra kwargs to the adapted tool or via `options_json`.

## Re-adapt Triggers

Re-run the adapter when:
- New data files / columns added
- Data volume grew 10x (sampling strategy may need to change)
- New domain columns (e.g., `lm_count`) appear
- Connector changes (new API, DB)

```python
profile = RepoAnalyzer("/path/to/repo").analyze()
ToolAdapter.from_profile(profile).write("./adapted")
```
