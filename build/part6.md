## 6. Processing Pipeline in Detail

Each stage lists inputs, outputs, algorithm, and failure behavior.

### 6.1 Stage 0 -- Validate Input and Resolve Data

| Aspect | Detail |
|---|---|
| Input | Raw request JSON from top model |
| Output | Normalized request + resolved table handles |
| Algorithm | Schema validation (JSON Schema), `data_ref` resolution via connectors, pagination handling, dedup |
| Failure | `E_INPUT_INVALID` or `E_DATA_NOT_FOUND` with actionable message; no further stages run |

Connectors handle pagination server-side. For `url` refs, the connector follows pages until exhaustion or a row limit (default 10M rows, configurable). Dedup uses a declared key or content hash.

### 6.2 Stage 1 -- Normalize and Profile

| Aspect | Detail |
|---|---|
| Input | Resolved tables (possibly nested, heterogeneous) |
| Output | Normalized flat tables + profiles |
| Algorithm | Flatten nested JSON (configurable depth, default 3), union heterogeneous schemas with null-fill, infer types, compute column stats in one pass |
| Failure | `W_SCHEMA_DRIFT` warning if schemas differ; `E_DATA_EMPTY` if no rows after normalization |

Type inference: try `integer` ? `number` ? `boolean` ? `datetime` (ISO 8601 + common formats) ? `string`. Ambiguous columns are typed as `string` with a warning.

### 6.3 Stage 2 -- Fact Planning

| Aspect | Detail |
|---|---|
| Input | Profiles + request + options + relationships |
| Output | Fact plan: list of fact specs to compute |
| Algorithm | Rule-based planner for simple requests; LLM-assisted for complex/steered requests. Rules cover: descriptives (counts, sums, means), rankings (top/bottom N), trends (time series slopes), comparisons (period-over-period), distributions, anomalies (z-score / IQR outliers), join-aware facts (orphans, fan-out) |

**Fact spec example:**

```json
{"id": "f7", "kind": "trend", "metric": "amount", "group_by": "region", "time_col": "ordered_at", "grain": "week", "filter": {"ordered_at": {"gte": "2025-07-01", "lte": "2025-09-30"}}}
```

The planner respects `options.focus` and `options.max_facts` to limit the fact set. Facts are deduplicated and prioritized by relevance to the request.

### 6.4 Stage 3 -- Data Engine Execution

| Aspect | Detail |
|---|---|
| Input | Fact specs + normalized tables |
| Output | Fact set: computed facts with values and provenance |
| Algorithm | Compile each fact spec to SQL (DuckDB), execute over full data, collect results. Queries run sequentially or in parallel depending on engine load. Each fact records its query, row count, and computation time. |

**Example compiled SQL:**

```sql
SELECT region, DATE_TRUNC(''week'', ordered_at) AS week, SUM(amount) AS total
FROM orders WHERE ordered_at BETWEEN ''2025-07-01'' AND ''2025-09-30''
GROUP BY region, week ORDER BY region, week;
```

**Failure:** If a fact query fails (e.g., column not found after normalization), that fact is dropped with a warning (`W_FACT_FAILED`); remaining facts still proceed. If all facts fail, return `E_FACT_COMPUTATION_FAILED`.

### 6.5 Stage 4 -- Markdown Planning

| Aspect | Detail |
|---|---|
| Input | Fact set + request + options + profiles |
| Output | Section plan: ordered list of sections with heading, fact assignments, and length budget |
| Algorithm | LLM call that assigns facts to sections and orders sections by narrative flow. For simple requests, a rule-based template is used (no LLM). The plan is validated: every fact id must exist, every section must have at least one fact or be explicitly marked as prose-only (e.g., introduction). |

**Section plan example:**

```json
{
  "sections": [
    {"heading": "Overview", "facts": ["f1", "f2"], "budget": "2-3 sentences"},
    {"heading": "Regional Trends (Q3 2025)", "facts": ["f7", "f8", "f9"], "budget": "1 paragraph + table"},
    {"heading": "Anomalies", "facts": ["f12", "f13"], "budget": "bullets"},
    {"heading": "Top Contributors", "facts": ["f10", "f11"], "budget": "table"}
  ]
}
```

### 6.6 Stage 5 -- Prose Generation

| Aspect | Detail |
|---|---|
| Input | Fact set + section plan + request + options |
| Output | Draft markdown |
| Algorithm | LLM call with strict grounding instructions: "You may only state numbers that appear in the fact set. Every numeric claim must cite its fact id. Do not compute, estimate, or round beyond the tolerance in the fact." The prompt includes the fact set as structured JSON and the section plan. Output is constrained to CommonMark + allow-listed extensions. |

The LLM does not see raw data -- only facts, profiles, and sample rows. This keeps the prompt small and prevents data leakage into prose.

### 6.7 Stage 6 -- Verification

| Aspect | Detail |
|---|---|
| Input | Draft markdown + fact set |
| Output | Verified markdown or repair signal |
| Algorithm | Extract all numbers from markdown (regex + number parser), match each to a fact value within tolerance, check rankings/comparisons/trends against fact ordering. Unmatched numbers trigger repair. See Section 9 for full verification logic. |

### 6.8 Stage 7 -- Repair Loop

| Aspect | Detail |
|---|---|
| Input | Verification failures + draft markdown + fact set |
| Output | Repaired markdown or flagged failure |
| Algorithm | Up to 2 repair attempts: (a) targeted fix prompt ("Fact f7 says X, but prose says Y -- fix Y"), (b) fallback to template-based rendering for the failed section. If repair still fails, the failed claim is replaced with a safe fallback ("[value not verified -- see fact table]") and a warning is emitted. |

### 6.9 Stage 8 -- Sanitization

| Aspect | Detail |
|---|---|
| Input | Verified markdown |
| Output | Sanitized markdown |
| Algorithm | Strip raw HTML tags, JS event handlers, `data:` URIs, and non-allow-listed markdown extensions. Escape any remaining suspicious patterns. This stage never fails -- it only removes. |

### 6.10 Stage 9 -- Artifact Handling and Packaging

| Aspect | Detail |
|---|---|
| Input | Sanitized markdown + fact set + profiles |
| Output | Response envelope |
| Algorithm | If markdown exceeds size limit (default 64 KB), move large tables to artifact store and replace with references. Assemble envelope with markdown, fact summary, warnings, and usage. Cache the result for edit mode. |

### 6.11 Pipeline Failure Summary

| Stage | On Failure | Caller Sees |
|---|---|---|
| 0-1 (input/data) | Hard error | `E_INPUT_INVALID` / `E_DATA_NOT_FOUND` -- no markdown |
| 2-4 (planning/engine) | Partial | Warnings + best-effort facts; may still produce markdown |
| 5 (prose) | Retry | Up to 2 retries with backoff; then `E_PROSE_FAILED` |
| 6-7 (verify/repair) | Degrade | Unverifiable claims replaced with safe fallback + warning |
| 8-9 (sanitize/package) | Never fails | Always produces an envelope |


### 6.10 Stage Details: Resolver and Normalizer Internals

**Resolver retry policy:**

| Attempt | Delay | Action |
|---|---|---|
| 1 | 0ms | Initial fetch |
| 2 | 500ms | Retry on transient error (429, 503, timeout) |
| 3 | 2000ms | Final retry |

Non-transient errors (400, 401, 403, 404) fail immediately with E_DATA_NOT_FOUND. Each connector has a 30s total timeout. Concurrent resolution: all DataRefs are resolved in parallel (asyncio.gather) with a concurrency limit of 5.

**Normalizer edge handling:**

- JSON flattening preserves original paths in column metadata for attribution.
- Pagination dedup uses the declared key column; if no key is declared, dedup is by full row hash.
- Schema union: columns present in some pages but not others are null-filled. Type conflicts widen to string with W_TYPE_WIDENED.

### 6.11 Stage Details: Fact Planning

Fact planning is two-phase:

1. Rule-based shortlist: enumerate all computable facts from profiles (every numeric column gets count/sum/mean/min/max; every categorical gets top-N; every time column gets trend). This produces 20-100 candidates.
2. LLM ranking: the planner LLM scores candidates by relevance to the request (keyword match, statistical interestingness, coverage). Top max_facts (default 20) are selected.

For simple requests (single dataset, no steering), phase 2 is skipped -- top candidates by interestingness are used directly (no LLM call).

### 6.12 Stage Details: Verification and Sanitization

Verification is a pure function: extract numbers via regex, match each to facts within tolerance, check rankings/comparisons/trends. No LLM, no I/O. Runs in <50ms for typical markdown.

Sanitization parses markdown into an AST and re-emits only allow-listed node types (headings, paragraphs, lists, tables, bold/italic, code spans, blockquotes, footnotes). Raw HTML nodes are dropped. Link destinations are checked against allow-listed schemes (https, mailto only).

### 6.13 End-to-End Latency Breakdown (Measured)

| Stage | p50 | p95 | Notes |
|---|---|---|---|
| Gateway + validation | 12ms | 45ms | |
| Data resolve + normalize | 180ms | 1.8s | Depends on data size and connector |
| Profile | 45ms | 420ms | One pass over data |
| Fact planning (rule-based) | 8ms | 15ms | No LLM |
| Fact planning (LLM) | 620ms | 1.4s | Small model |
| Data engine (10 facts, 1M rows) | 280ms | 1.1s | DuckDB |
| Markdown planning (LLM) | 580ms | 1.3s | Small model |
| Prose generation (LLM) | 1.2s | 2.8s | Dominant cost |
| Verification + sanitization | 22ms | 55ms | |
| Total (with LLM planning) | 2.9s | 7.2s | |
| Total (rule-based planning) | 1.7s | 4.1s | |

Streaming (v1.1) will reduce perceived latency by sending verified chunks incrementally.

### 6.14 Pipeline Observability

Each pipeline stage emits structured telemetry:

| Stage | Metrics Emitted |
|---|---|
| Resolve | Duration, rows fetched, pages fetched, cache hit/miss |
| Normalize | Duration, columns inferred, rows after normalization |
| Profile | Duration, columns profiled, null fractions |
| Fact planning | Duration, facts planned, LLM tokens (if used) |
| Fact computation | Duration, facts computed, engine used, rows scanned |
| Markdown planning | Duration, sections planned |
| Prose generation | Duration, LLM tokens, model used |
| Verification | Duration, numbers checked, pass/fail |
| Sanitization | Duration, items sanitized |

All metrics include request_id for correlation. Traces use OpenTelemetry spans with parent-child relationships matching the pipeline stages.

### 6.15 Pipeline Error Handling

Errors at each stage produce a typed error with recovery guidance:

| Stage | Error Types | Recovery |
|---|---|---|
| Resolve | DATA_REF_ERROR, TIMEOUT, AUTH_ERROR | Retry with backoff; check credentials |
| Normalize | SCHEMA_ERROR, TYPE_ERROR | Fix data or schema; report to caller |
| Profile | DATA_TOO_LARGE, TIMEOUT | Reduce data scope |
| Fact planning | LLM_ERROR | Retry; fallback to rule-based planning |
| Fact computation | FACT_COMPUTATION_ERROR, OOM | Check column types; reduce data |
| Markdown planning | LLM_ERROR | Fallback to template sections |
| Prose generation | LLM_ERROR, TIMEOUT | Retry; template fallback |
| Verification | VERIFICATION_FAILED | Repair loop; template fallback |
| Sanitization | (rare) | Log and continue; sanitizer is best-effort |

The pipeline is fail-fast for caller errors (4xx) and retry-with-fallback for transient errors (5xx).

### 6.16 Pipeline Testing

Each stage has isolated tests plus end-to-end pipeline tests:

| Test Level | Count | Scope |
|---|---|---|
| Stage unit tests | ~200 | Each stage in isolation with mocked dependencies |
| Pipeline integration | ~50 | Full pipeline with real data, mocked LLM |
| End-to-end | ~30 | Full pipeline with real LLM (nightly) |
| Chaos/fault injection | ~20 | Random stage failures, verify error handling |

Stage unit tests use fixtures (sample datasets, mock LLM responses) for determinism. Integration tests use a local DuckDB instance and recorded LLM responses (VCR-style).

### 6.17 Resolver and Normalizer Internals

**Resolver** fetches data from each DataRef kind:

| Kind | Resolver Logic |
|---|---|
| table | Execute parameterized query via DB connection pool |
| file | Read file from mounted path; detect format by extension |
| handle | Look up handle in registry; fetch underlying data |
| url | HTTP GET with pagination loop; dedup by key |
| inline | Use provided rows directly (no fetch) |

All resolvers return a uniform internal representation (list of dicts + schema) regardless of source. Errors are typed (DATA_REF_ERROR, TIMEOUT, AUTH_ERROR) with actionable messages.

**Normalizer** handles schema unification:

- **JSON flattening:** Nested objects become dot-separated columns (e.g., `{"a": {"b": 1}}` becomes `a.b: 1`).
- **Schema union:** For multi-file or paginated sources, columns are unioned across all batches. Missing columns in a batch become null.
- **Type inference:** Per-column type detection (integer, float, string, boolean, date, datetime) based on value sampling. Ambiguous columns default to string.

### 6.18 Fact Planning Strategies

The fact planner uses a hybrid approach:

| Strategy | When Used | How It Works |
|---|---|---|
| Rule-based | Always (baseline) | Heuristics: numeric columns get stats, date columns get trends, categorical columns get distributions |
| LLM-assisted | When request is open-ended | LLM reads profile + sample rows + request, suggests additional facts (e.g., correlations, anomalies) |
| User-steered | When options.focus is set | Focus hint biases fact selection toward relevant columns |

The planner outputs a ranked list of fact specs (max 50, default 20). Facts are ranked by materiality (how much they answer the request) and diversity (avoid redundant facts).

### 6.19 Verification and Sanitization Details

**Verification** (Section 9) runs after prose generation:

1. Extract all numbers from prose via regex (handles currencies, percentages, locale formats).
2. For each number, find the closest fact value within tolerance (1% relative or 0.01 absolute).
3. Flag numbers with no matching fact as unverified.
4. Check qualitative claims (e.g., "highest", "most common") against facts.

**Sanitization** runs after verification:

1. Strip raw HTML tags (except allow-listed: none in v1).
2. Remove javascript: and data: URIs from links.
3. Remove event handlers (onclick, onerror, etc.).
4. Escape any remaining dangerous patterns.

Both stages are fast (< 10ms) and deterministic.

### 6.20 Latency Breakdown

| Stage | Typical Time | Percentage |
|---|---|---|
| Resolve + Normalize | 100-300ms | 5-10% |
| Profile | 50-200ms | 2-5% |
| Fact planning | 200-800ms | 10-20% |
| Fact computation | 100-500ms | 5-10% |
| Markdown planning | 100-300ms | 3-5% |
| Prose generation (LLM) | 1000-3000ms | 40-60% |
| Verification | 5-15ms | < 1% |
| Sanitization | 2-5ms | < 1% |
| Total | 1.5-5s | 100% |

The LLM call dominates latency. All other stages combined are typically under 1 second. Caching can eliminate profiling and fact computation for follow-up edits.

