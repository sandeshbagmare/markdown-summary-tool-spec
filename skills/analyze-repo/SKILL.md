---
name: analyze-repo
description: Analyze any repository to profile its data, sampling, and adaptation needs
---

# Skill: analyze-repo

> Inspect any repo and produce a `RepoProfile` describing how to adapt the tools.

## Usage

```python
from repo_adapter import RepoAnalyzer

profile = RepoAnalyzer("/path/to/repo").analyze()

print(f"Repo: {profile.repo_name} ({profile.language}, {profile.framework})")
print(f"Datasets: {len(profile.datasets)}")
for d in profile.datasets:
    print(f"  {d.name}: {d.row_count} rows, cols={[c.name for c in d.columns]}")
print(f"Sampling: {profile.sampling.strategy} — {profile.sampling.description}")
print(f"Extra args: {[a.name for a in profile.extra_arguments]}")
print(f"Connectors: {profile.connectors_needed}")
if profile.warnings:
    print("Warnings:", profile.warnings)
```

## What It Detects

- **Data files**: CSV, JSON, JSONL, Parquet, TSV (up to 4 levels deep, skips venv/build)
- **Sampling needs**: row counts + code keywords (stratified/reservoir/window/pagination)
- **Extra arguments**: column-name heuristics (discount, lm/model, date) + `extra_args = [...]` in code
- **Language / framework**: Python / TypeScript / Go / Java; FastAPI / Django / Flask / Node
- **Connectors**: inline_json / inline_csv / url / connector

## Output: RepoProfile

```python
profile.model_dump(mode="json")  # full JSON
profile.raw_notes                 # human-readable summary
```

Use the profile to drive `ToolAdapter`:

```python
from repo_adapter import ToolAdapter
ToolAdapter.from_profile(profile).write("./adapted")
```
