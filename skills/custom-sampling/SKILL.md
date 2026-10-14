---
name: custom-sampling
description: Configure custom data sampling (random, stratified, reservoir, window) for any repo
---

# Skill: custom-sampling

> Handle "data sampling is done a little bit different" — every repo samples differently.

## Strategies

| Strategy | When | Example |
|----------|------|---------|
| `full` | <10k rows | `SamplingConfig(strategy="full")` |
| `random` | Uniform sample | `SamplingConfig(strategy="random", sample_size=5000, seed=42)` |
| `stratified` | Per-group coverage | `SamplingConfig(strategy="stratified", sample_size=5000, stratify_by="region")` |
| `reservoir` | Streaming / large | `SamplingConfig(strategy="reservoir", sample_size=10000, seed=42)` |
| `window` | Time-series recent N | `SamplingConfig(strategy="window", sample_size=1000)` |

## Code

```python
from repo_adapter.sampling import apply_sampling
from repo_adapter.models import SamplingConfig

cfg = SamplingConfig(strategy="stratified", sample_size=5000, stratify_by="category", seed=42)
sampled = apply_sampling(rows, cfg)
```

## Via Adapted Tool

```python
# At generation time:
from repo_adapter import RepoAnalyzer, ToolAdapter
from repo_adapter.models import SamplingConfig

profile = RepoAnalyzer("/path/to/repo").analyze()
profile.sampling = SamplingConfig(strategy="reservoir", sample_size=10000, seed=7)
ToolAdapter.from_profile(profile).write("./adapted")

# At call time (override via options_json):
import json
create_markdown_summary.invoke({
    "datasets_json": ds,
    "question": "Summarize",
    "options_json": json.dumps({"sampling_strategy": "random", "sample_size": 2000}),
})
```

## Auto-Detection

`RepoAnalyzer` picks a strategy from row counts and code keywords. Override by setting
`profile.sampling` before calling `ToolAdapter`.
