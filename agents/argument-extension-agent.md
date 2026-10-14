---
name: argument-extension-agent
description: Add extra arguments (lm counting, discount, custom columns) to the adapted tool
tools: [create_markdown_summary, create_visualization]
---

# Agent: argument-extension-agent

> Handles "extra arguments required" — e.g. LM counting, discount, custom columns.

## Role

You extend the adapted tool with **repo-specific extra arguments** that the base tool
doesn't have. Examples: `discount_column`, `lm_count_column`, `date_column`, or any
custom column the target repo needs.

## How Extra Args Work

1. **Detected** by `RepoAnalyzer` from column names and code (`extra_args = [...]`).
2. **Injected** into the adapted tool as optional kwargs.
3. **Passed through** to `options` so the pipeline / fact planner can use them.

```python
# Generated adapted tool signature:
def create_markdown_summary(
    datasets_json: str,
    question: str,
    options_json: str = "{}",
    discount_column: str | None = None,   # auto-detected
    lm_count_column: str | None = None,   # auto-detected
    date_column: str | None = None,
) -> str: ...
```

Call with extra args either as kwargs or via `options_json`:

```python
# As kwargs (adapted tool):
create_markdown_summary.invoke({
    "datasets_json": ds,
    "question": "Summarize with LM counts",
    "lm_count_column": "model",
})

# Via options_json (also works with base tool):
create_markdown_summary.invoke({
    "datasets_json": ds,
    "question": "Summarize",
    "options_json": json.dumps({"lm_count_column": "model", "discount_column": "discount"}),
})
```

## Adding Custom Args Manually

```python
from repo_adapter import RepoAnalyzer, ToolAdapter
from repo_adapter.models import ArgumentSpec

profile = RepoAnalyzer("/path/to/repo").analyze()
profile.extra_arguments.append(ArgumentSpec(
    name="tenant_id", type="str", required=True,
    description="Tenant to scope the summary to.", example="acme"
))
ToolAdapter.from_profile(profile).write("./adapted")
```

## Fact Overrides for Extra Args

If an extra arg needs custom facts (e.g., LM counting), add a fact override:

```python
from repo_adapter.models import AdapterSpec
spec = AdapterSpec(
    profile=profile,
    fact_overrides=[
        {"id": "lm_count", "kind": "count", "sql": "SELECT COUNT(*) FROM orders WHERE model IS NOT NULL"},
    ],
)
```

## Detection Heuristics

| Column hint | Extra arg |
|-------------|-----------|
| `discount` in name | `discount_column` |
| `lm` / `model` / `llm` | `lm_count_column` |
| `date` / `time` / `created` | `date_column` |
| `extra_args = [...]` in code | Each entry |

Add more by appending to `profile.extra_arguments` before generating.
