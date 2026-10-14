## 14. Errors, Warnings and Partial Results

### 14.1 Issue Object

Both errors and warnings share a common shape:

```json
{"code": "E_DATA_NOT_FOUND", "message": "Dataset ''orders'' not found", "details": {"dataset_id": "orders"}, "retryable": false}
```

### 14.2 Error Codes

| Code | Meaning | Retryable | HTTP |
|---|---|---|---|
| `E_INPUT_INVALID` | Request validation failed | No | 400 |
| `E_DATA_NOT_FOUND` | Dataset not found or not accessible | No | 404 |
| `E_DATA_EMPTY` | Dataset has no rows after normalization | No | 422 |
| `E_DATA_TOO_LARGE` | Dataset exceeds row/page limits | No | 413 |
| `E_FACT_COMPUTATION_FAILED` | All fact queries failed | No | 500 |
| `E_PROSE_FAILED` | LLM failed after retries | Yes | 502 |
| `E_LLM_UNAVAILABLE` | LLM provider unavailable | Yes | 503 |
| `E_LLM_OVERLOADED` | LLM rate limited / circuit breaker | Yes | 429 |
| `E_VERIFICATION_FAILED` | Verification failed and repair exhausted (partial still returned) | No | 200 (partial) |
| `E_NOT_FOUND` | `prior_summary_id` not found | No | 404 |
| `E_INTERNAL` | Unexpected internal error | Yes | 500 |

### 14.3 Warning Codes

| Code | Meaning | Impact |
|---|---|---|
| `W_SCHEMA_DRIFT` | Datasets/pages have differing schemas | Null-filled union; some columns sparse |
| `W_PROFILE_MISMATCH` | Provided profile does not match data | Recomputed |
| `W_NESTING_TRUNCATED` | JSON nesting beyond max depth | Deeper fields as JSON column |
| `W_PAGINATION_TRUNCATED` | Pagination hit page/row limit | Data is incomplete; summary notes this |
| `W_FACT_FAILED` | Single fact query failed | That fact omitted; others still delivered |
| `W_NULL_RATE` | Column has high null rate (>30%) | Caveat in prose |
| `W_TRUNCATED` | Markdown exceeded size limit | Large tables as artifacts |
| `W_UNVERIFIED_CLAIM` | A claim could not be verified after repair | Replaced with safe fallback |
| `W_SENSITIVE_REDACTED` | Columns redacted per policy | Noted in caveats |
| `W_CACHE_STALE` | Cached profile may be stale | Re-verify on next request |

### 14.4 Partial Results

When some facts fail but others succeed, the tool returns `status: "partial"` with:

- Markdown covering the successful facts.
- Warnings listing every failed fact and why.
- A caveat section noting what is missing.

The caller can decide to show the partial summary or retry. Partial results are always verified -- no unverified numbers are included.

## 15. Testing and Evaluation

### 15.1 Test Layers

| Layer | What It Tests | How |
|---|---|---|
| Unit | Normalizer, profiler, engine, verifier, sanitizer | pytest with fixtures; mocked data |
| Integration | Full pipeline with real DuckDB + mock LLM | End-to-end with canned LLM responses |
| Contract | Request/response schema validation | JSON Schema validation on every test case |
| Security | Injection, sanitization, redaction | Adversarial inputs with known payloads |
| Evaluation | Summary quality (faithfulness, usefulness) | Human + automated metrics on eval set |
| Load | Latency, throughput, large data | Benchmark with 10M-row datasets |

### 15.2 Evaluation Set Design

The eval set covers:

| Category | Examples | Count (target) |
|---|---|---|
| Single dataset, small | 1K rows, simple request | 20 |
| Single dataset, large | 1M+ rows, complex request | 20 |
| Multi-dataset | 2-3 related datasets with joins | 20 |
| Paginated / nested | API responses with nesting and pagination | 15 |
| Steered | Various audience/length/language combos | 15 |
| Follow-up edits | Edit a prior summary | 10 |
| Adversarial | Injection attempts, sensitive data, edge cases | 15 |
| **Total** | | **~115 cases** |

Each case has: input datasets (or generators), request, expected fact set (computed), and human-written reference summary for comparison.

### 15.3 Metrics and Initial Quality Gates

| Metric | How Measured | Gate (v1) |
|---|---|---|
| Numeric accuracy | % of numbers in prose matching facts | 100% (hard gate) |
| Claim accuracy | % of rankings/comparisons/trends correct | 100% (hard gate) |
| Fact coverage | % of relevant facts included (vs reference) | >= 80% |
| Fact precision | % of included facts that are relevant | >= 85% |
| Fluency | Human rating 1-5 | >= 4.0 mean |
| Usefulness | Human rating: "does this answer the request?" 1-5 | >= 4.0 mean |
| Latency p50 | End-to-end time | < 5s |
| Latency p95 | End-to-end time | < 10s |
| Cost per request | LLM + engine cost | < $0.02 |

Fluency and usefulness are secondary to faithfulness. A fluent but wrong summary fails the gate.

### 15.4 Model Bake-Off Procedure

To select or change the LLM:

1. Run the full eval set on each candidate model (same prompts, same facts).
2. Measure numeric accuracy, claim accuracy, fluency, latency, and cost.
3. Rank by: faithfulness first, then usefulness, then cost/latency.
4. Require 100% numeric accuracy -- any model that hallucinates numbers is disqualified regardless of fluency.
5. Re-run bake-off quarterly or when a new model is available.

## 16. Operations, Configuration and Observability

### 16.1 Configuration and Limits

| Config | Default | Description |
|---|---|---|
| `max_datasets` | 8 | Max datasets per request |
| `max_rows` | 10M | Max rows per dataset |
| `max_pages` | 1000 | Max pagination pages |
| `max_markdown_kb` | 64 | Max inline markdown size |
| `max_facts` | 20 | Max facts per summary |
| `llm_model` | `small-model-v3` | Primary LLM |
| `llm_fallback` | none | Secondary LLM for failover |
| `llm_timeout_ms` | 10000 | Per-call timeout |
| `cache_ttl_s` | 3600 | Profile/fact/plan cache TTL |
| `artifact_ttl_s` | 86400 | Artifact expiry |
| `rate_limit_rps` | 100 | Requests per second per tenant |

All limits are per-tenant and configurable.

### 16.2 Usage Object and Telemetry

Every response includes a `usage` object. The backend also emits structured logs:

| Field | Description |
|---|---|
| `request_id` | Unique per request |
| `datasets` | Dataset ids and row counts |
| `fact_count` | Number of facts computed |
| `verification` | `passed` / `repaired` / `fallback` |
| `llm_input_tokens` / `llm_output_tokens` | Token counts |
| `engine_ms` / `llm_ms` / `total_ms` | Latency breakdown |
| `cache_hit` | Whether profile/plan was cached |
| `warnings` | Warning codes emitted |

Metrics are aggregated for dashboards: request rate, error rate, latency percentiles, verification failure rate, cost per request.

### 16.3 Service Level Objectives (Initial)

| SLO | Target |
|---|---|
| Availability | 99.9% |
| p50 latency | < 5s |
| p95 latency | < 10s |
| Numeric accuracy | 100% (every delivered number verified) |
| Error rate | < 1% (excluding caller errors) |

### 16.4 Versioning and Compatibility

- **Spec version:** 1.0 (this document).
- **API version:** `v1` in the URL path (`/v1/summarize`).
- **Schema version:** `1.0` in request/response (`"schema_version": "1.0"`).
- Compatibility: additive changes only within a major version. New optional fields are OK; removing or renaming fields requires a new major version.
- Deprecation: 6-month notice for breaking changes.

### 16.5 Deployment

- Stateless service; horizontally scalable.
- DuckDB runs in-process; no external DB required for the engine.
- LLM calls go through a provider abstraction (supports multiple backends).
- Artifact store: local filesystem or S3-compatible; configurable.
- Cache: in-memory LRU + optional Redis for multi-instance.
- Health check: `/health` returns engine + LLM provider status.

### 12.6 Error Recovery Strategies

For each error category, the recommended caller recovery:

| Error Code | Caller Action |
|---|---|
| SCHEMA_ERROR | Fix the request JSON and retry |
| DATA_REF_ERROR | Check data source availability; retry with backoff |
| DATA_TOO_LARGE | Reduce data scope or add filters; retry |
| FACT_COMPUTATION_ERROR | Check column types; may need to adjust data_ref |
| LLM_ERROR | Retry with backoff; try fallback provider |
| VERIFICATION_FAILED | Inspect warnings; may need to adjust request |
| TIMEOUT | Retry with longer timeout or smaller data |
| RATE_LIMITED | Respect Retry-After header |

All errors include a `retryable` boolean in the response envelope to indicate whether retrying is likely to help.

### 12.7 Testing the Error Paths

Each error code has dedicated tests:

- **Unit tests:** Trigger each error condition with minimal setup (e.g., invalid JSON for SCHEMA_ERROR).
- **Integration tests:** Trigger errors with real data sources (e.g., unreachable URL for DATA_REF_ERROR).
- **Chaos tests:** Randomly inject failures (LLM timeout, engine OOM) and verify the error envelope is well-formed.

Error path tests are part of the CI gate -- every error code must have at least one test that triggers it.

### 12.8 Evaluation Metrics Detail

Each metric in the evaluation harness is defined precisely:

| Metric | Definition | Target |
|---|---|---|
| Numeric accuracy | Fraction of numbers in prose that match a fact within tolerance | 100% |
| Claim accuracy | Fraction of qualitative claims supported by facts | 100% |
| Fact coverage | Fraction of material facts that appear in prose | >= 80% |
| Fluency | Human rating 1-5 on readability and coherence | >= 4.0 |
| Latency p50/p95 | Wall-clock time from request to response | < 5s / < 10s |
| Cost per request | LLM tokens consumed | < $0.01 |

Metrics are computed per eval case and aggregated (mean, median, p95) across the full set.

### 12.9 Operational Dashboards

Recommended dashboards for production monitoring:

| Dashboard | Key Panels |
|---|---|
| Request overview | Request rate, error rate, latency percentiles |
| Verification | Verification pass/fail rate, repair trigger rate |
| Cost | Tokens per request, cost per request, cost by model |
| Data | Rows scanned, datasets per request, connector breakdown |
| Errors | Error rate by code, top error messages |

Dashboards are built in the team's standard observability platform (Grafana, Datadog, etc.).

### 12.10 Incident Response

| Severity | Definition | Response |
|---|---|---|
| SEV-1 | All summaries failing or data leakage | Page on-call; rollback or disable |
| SEV-2 | Elevated error rate or latency | Investigate within 1 hour |
| SEV-3 | Single feature degraded (e.g., URL connector) | Fix in next deploy |

Runbook entries cover: LLM provider outage, engine OOM, artifact store unavailability, and cache poisoning.

### 12.11 Evaluation Harness Detail

The evaluation harness runs 115 test cases covering:

| Category | Count | Description |
|---|---|---|
| Single dataset | 30 | Various data types, sizes, and requests |
| Multi-dataset | 20 | Join-aware facts, cross-dataset comparisons |
| Edge cases | 20 | Empty data, single row, all nulls, adversarial |
| Steering | 15 | Focus, audience, length, language variations |
| Security | 15 | Prompt injection, markdown injection, redaction |
| Follow-up edits | 15 | Length change, focus change, data change |

Each case has: input (datasets + request + options), expected behaviour (what the summary should contain), and assertions (mechanical checks on the output).

### 12.12 Continuous Evaluation

Evaluation runs at three levels:

| Level | When | Scope | Gate |
|---|---|---|---|
| Per-PR | Every pull request | 30-case smoke set | Must pass |
| Nightly | Daily | Full 115-case set | Alert on failure |
| Pre-release | Before version tag | Full set + human eval (30 cases) | Must pass |

Results are tracked over time to detect regressions. A dashboard shows pass rates, latency trends, and cost trends per model.

### 12.13 Human Evaluation Protocol

For fluency and coverage (which require human judgment):

1. **Sample:** 30 cases randomly selected from the 115-case set.
2. **Annotators:** 2 independent raters per case.
3. **Rubric:** 1-5 scale for fluency (readability, coherence, formatting) and coverage (did the summary include the important findings?).
4. **Adjudication:** Cases where raters differ by more than 1 point are discussed and re-rated.
5. **Threshold:** Mean fluency >= 4.0, mean coverage >= 80%.

Human eval takes approximately 2 hours per release (30 cases x 2 raters x 2 min/case).

