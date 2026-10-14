---
name: sampling-agent
description: Configure and tune data sampling for large or streaming datasets
tools: [create_markdown_summary]
---

# Agent: sampling-agent

> Handles the "data sampling is done a little bit different" case — every repo samples differently.

## Role

You configure **how data is sampled before it hits DuckDB**. The base tool does full scans;
this agent adapts sampling to the target repo's scale and access pattern.

## Strategies

| Strategy | Code | When |
|----------|------|------|
| `full` | `SamplingConfig(strategy="full")` | <10k rows, no sampling |
| `random` | `SamplingConfig(strategy="random", sample_size=5000, seed=42)` | Uniform sample, reproducible |
| `stratified` | `SamplingConfig(strategy="stratified", sample_size=5000, stratify_by="region")` | Per-group coverage |
| `reservoir` | `SamplingConfig(strategy="reservoir", sample_size=10000, seed=42)` | Streaming / unknown total |
| `window` | `SamplingConfig(strategy="window", sample_size=1000)` | Time-series, recent N |

## Usage

```python
from repo_adapter.sampling import apply_sampling
from repo_adapter.models import SamplingConfig

cfg = SamplingConfig(strategy="stratified", sample_size=5000, stratify_by="category", seed=42)
sampled = apply_sampling(rows, cfg)
```

Via adapted tool `options_json`:

```json
{"sampling_strategy": "reservoir", "sample_size": 10000, "seed": 7}
```

Via `AdapterSpec`:

```python
from repo_adapter import RepoAnalyzer, ToolAdapter
from repo_adapter.models import SamplingConfig

profile = RepoAnalyzer("/path/to/repo").analyze()
profile.sampling = SamplingConfig(strategy="stratified", sample_size=8000, stratify_by="region")
ToolAdapter.from_profile(profile).write("./adapted")
```

## Detection

`RepoAnalyzer` auto-detects sampling needs:
- Row count >100k → `reservoir`
- Row count >10k → `random`
- Code mentions `stratified` / `reservoir` / `window` → that strategy
- Otherwise → `full`

Override the auto-detection by setting `profile.sampling` before calling `ToolAdapter`.
