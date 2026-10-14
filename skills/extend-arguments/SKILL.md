---
name: extend-arguments
description: Add extra arguments (LM counting, discount, custom columns) to the adapted tool
---

# Skill: extend-arguments

> Handle "extra arguments required" — e.g. LM counting, discount, custom columns.

## Auto-Detected Args

| Column hint | Arg | Example |
|-------------|-----|---------|
| `discount` | `discount_column` | `discount` |
| `lm` / `model` / `llm` | `lm_count_column` | `model` |
| `date` / `time` | `date_column` | `created_at` |
| `extra_args = [...]` in code | Each entry | custom |

## Usage

```python
# Adapted tool gets extra kwargs automatically:
from adapted_tool import create_markdown_summary

create_markdown_summary.invoke({
    "datasets_json": ds,
    "question": "Summarize with LM counts",
    "lm_count_column": "model",
    "discount_column": "discount",
})

# Or via options_json (works with base tool too):
import json
create_markdown_summary.invoke({
    "datasets_json": ds,
    "question": "Summarize",
    "options_json": json.dumps({"lm_count_column": "model"}),
})
```

## Adding Custom Args

```python
from repo_adapter import RepoAnalyzer, ToolAdapter
from repo_adapter.models import ArgumentSpec

profile = RepoAnalyzer("/path/to/repo").analyze()
profile.extra_arguments.append(ArgumentSpec(
    name="tenant_id", type="str", required=True,
    description="Tenant to scope to.", example="acme"
))
ToolAdapter.from_profile(profile).write("./adapted")
```

## Fact Overrides

For args needing custom SQL (e.g., LM counting):

```python
from repo_adapter.models import AdapterSpec
spec = AdapterSpec(profile=profile, fact_overrides=[
    {"id": "lm_count", "kind": "count", "sql": "SELECT COUNT(*) FROM orders WHERE model IS NOT NULL"},
])
```
