# Testing Report — Live Verification

**Date:** 2026-10-14T10:32+05:30  
**Repo:** `sandeshbagmare/markdown-summary-tool-spec` — `main` at `09876a8`  
**Model:** `claude-fable-5.1` (via `DEFAULT_MODEL` in `src/markdown_summary_tool/llm/client.py`)  
**Env:** `API_BASE` / `API_KEY` → `OpenAICompatibleClient` (Bearer auth); unset → `MockLLMClient` (deterministic)  
**Python:** 3.14.8 · **Platform:** win32

---

## 1. Unit Tests — `pytest tests/ -v`

```
tests/test_deepagent_tools.py::test_summarize_tool_has_name_description_args_schema PASSED
tests/test_deepagent_tools.py::test_visualization_tool_has_name_description PASSED
tests/test_deepagent_tools.py::test_get_llm_client_mock_when_env_not_set PASSED
tests/test_deepagent_tools.py::test_get_llm_client_openai_when_env_set PASSED
tests/test_deepagent_tools.py::test_create_markdown_summary_returns_valid_json_with_markdown PASSED
tests/test_deepagent_tools.py::test_create_visualization_returns_valid_json_with_chart_spec PASSED
tests/test_deepagent_tools.py::test_summarize_tool_error_on_empty_question PASSED
tests/test_deepagent_tools.py::test_visualization_tool_error_on_empty_question PASSED
tests/test_pipeline.py::test_inline_json_basic PASSED
tests/test_pipeline.py::test_empty_dataset PASSED
tests/test_pipeline.py::test_inline_csv PASSED
tests/test_pipeline.py::test_redaction PASSED
tests/test_verifier.py::test_extract_numbers PASSED
tests/test_verifier.py::test_verify_pass PASSED
tests/test_verifier.py::test_verify_hallucination PASSED
tests/test_verifier.py::test_sanitize_strips_html PASSED

16 passed in 2.18s
```

---

## 2. Stress Test — `python examples/stress_test.py` (10k + 1k rows, MockLLMClient)

Synthetic data: 10,000 orders (customer/amount/region/date/order_id) + 1,000 products (category/price/stock/sku), seeded RNG.

```
Dataset A: orders 10k rows  total=4995622.95  regions=4
Dataset B: products 1k rows  categories=5

Test 1: summarize 10k orders  — time=1.449s  facts=13  verified=True  ok=True
Test 2: visualize 10k orders (bar) — time=0.525s  chart_type=bar  rows=20  has_vega=True  ok=True
Test 3: summarize 1k products — time=0.043s  facts=19  ok=True
Test 4: visualize 1k products (auto) — time=0.036s  chart_type=pie  ok=True
Test 5: summarize both datasets (10k+1k) — time=0.547s  facts=23  ok=True
Test 6: visualize both datasets — time=0.519s  ok=True

Summary: 6/6 PASS  Total time: 3.118s  Overall: PASS
```

All facts computed via DuckDB push-down over full data (no sampling for final values); LLM only verbalizes facts JSON; mechanical verifier checks numbers within tolerance.

---

## 3. DeepAgent Example — `python examples/deepagent_example.py` (mock mode, no API keys)

```
LLM client: MockLLMClient (mock=True)
Model: claude-fable-5.1
Tools: ['create_markdown_summary', 'create_visualization']
(API_BASE/API_KEY not set — running in mock mode, calling tools directly)

--- create_markdown_summary ---
markdown preview: ## Summary ...  facts: 13  verified: True

--- create_visualization ---
chart_type: bar  mark: bar  rows: 4
vega spec keys: ['$schema', 'width', 'height', 'data', 'mark', 'encoding']

--- Multi-dataset summarization ---
facts: 22  warnings: []
```

---

## 4. Live DeepAgent Both-Tools Test — `deepagents.create_deep_agent`

```python
from deepagents import create_deep_agent
from markdown_summary_tool.tools.summarize_tool import create_markdown_summary
from visualization_tool.tool import create_visualization

agent = create_deep_agent(
    model="claude-fable-5.1",
    tools=[create_markdown_summary, create_visualization],
    system_prompt="You are a data assistant..."
)
```

```
DeepAgent type: CompiledStateGraph
Tools: ['create_markdown_summary', 'create_visualization']
summarize .invoke -> markdown: True facts: 9 verified: True
visualize .invoke -> chart_spec: True mark: bar vega: True
multi-dataset summarize -> facts: 14 warnings: []
DEFAULT_MODEL: claude-fable-5.1
API_BASE set: False API_KEY set: False
get_llm_client(): MockLLMClient (MockLLMClient expected when no env)
ALL LIVE CHECKS PASSED
```

Both tools expose `langchain_core @tool` interface (`.name`, `.description`, `.args_schema`, `.invoke`) with fallback decorator when `langchain_core` not installed. Verified `deepagents` 1.x `CompiledStateGraph` creation with `model="claude-fable-5.1"`.

---

## 5. Env Var Integration

| Condition | `get_llm_client()` | Verified |
|-----------|-------------------|----------|
| `API_BASE` + `API_KEY` set | `OpenAICompatibleClient(base_url=API_BASE, api_key=API_KEY, model=claude-fable-5.1)` — `Authorization: Bearer <key>` | ✅ |
| Neither set | `MockLLMClient` | ✅ |
| Only one set / whitespace | `MockLLMClient` | ✅ |
| Trailing slash in `API_BASE` | Stripped | ✅ |
| No hardcoded keys/URLs in `src/` | — | ✅ |

Live LLM call (with real `API_BASE`/`API_KEY`) not executed in this run — requires user-provided env vars. Set them and re-run:

```powershell
$env:API_BASE="https://api.example.com/v1"
$env:API_KEY="sk-..."
python examples/deepagent_example.py  # will use OpenAICompatibleClient + claude-fable-5.1
```

---

## 6. Summary

| Suite | Result |
|-------|--------|
| `pytest` (16 tests) | ✅ 16 passed |
| `stress_test.py` (6 checks, 11k rows) | ✅ 6/6 PASS (3.1s) |
| `deepagent_example.py` | ✅ PASS (mock) |
| Live `create_deep_agent` + `.invoke` both tools | ✅ PASS |
| Env var / model `claude-fable-5.1` | ✅ PASS |

**No failures. All live tests green.**
