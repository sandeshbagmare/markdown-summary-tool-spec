## 4. System Architecture

### 4.1 Components

| Component | Responsibility | Notes |
|---|---|---|
| Tool gateway | Receives function call from top model; authenticates; enforces rate/size limits; returns envelope | Thin HTTP/RPC layer |
| Input validator | Validates and normalizes request (schema, ids, limits) | Rejects early with `E_INPUT_INVALID` |
| Data resolver | Turns each `data_ref` into a table via server-side connectors | Connectors: file, table/query, handle, URL (allow-listed), inline |
| Normalizer | Flattens nested JSON, handles pagination, unions heterogeneous schemas | Preserves provenance |
| Profiler | Computes column stats over full data; verifies provided profiles | One pass; milliseconds for 10K rows |
| Fact planner | Decides which facts to compute based on request + profiles | Rule-based + LLM-assisted for complex requests |
| Data engine | Executes aggregations over full data (DuckDB primary, pandas fallback) | Safe expression language; no eval |
| Markdown planner | Plans section structure, headings, and fact-to-section assignment | LLM call (or rule-based for simple cases) |
| Prose generator | Turns facts into fluent markdown under grounding constraints | LLM call with fact set in context |
| Verifier | Extracts numbers from prose, checks against fact set; repairs or flags | Mechanical; no LLM |
| Sanitizer | Strips raw HTML, JS, data URIs; enforces allow-listed markdown | Always runs |
| Artifact store | Stores large fact tables / exports; returns references | For markdown that would otherwise be too large |
| Cache | Caches profiles, fact sets, and plans by dataset fingerprint + request hash | TTL + invalidation on data change |

### 4.2 Pipeline Overview

```
Top model call
    |
    ?
[Gateway] ? [Validator] ? [Data Resolver + Normalizer] ? [Profiler]
                                                              |
                                          +-------------------+
                                          ?
                                   [Fact Planner] --? [Data Engine] --? Fact Set
                                          |                                |
                                          ?                                ?
                                   [Markdown Planner]              [Prose Generator]
                                          |                                |
                                          +----------------------------------+
                                                     ?
                                              [Verifier] --? (repair loop if needed)
                                                     |
                                                     ?
                                              [Sanitizer] ? [Artifact Store if needed]
                                                     |
                                                     ?
                                              Response Envelope (markdown + metadata)
                                                     |
                                                     ?
                                              Top model / User
```

### 4.3 Request Modes

| Mode | Description | LLM Calls |
|---|---|---|
| `create` | New summary from datasets + request | 1-2 (planner + prose) |
| `edit` | Follow-up edit of a prior summary (focus change, length, language, etc.) | 1 (prose with prior context) |
| `retry` | Retry after verifier failure | 1 (repair) |

All modes share the same pipeline; `edit` reuses cached profiles and fact sets where possible.

### 4.4 Delivery to the Caller and UI

- **Markdown** is returned as a string in the envelope, ready to render in any CommonMark renderer. No raw HTML, no JS.
- **Metadata** (fact set summary, warnings, artifact references, usage) is returned as structured JSON alongside the markdown.
- **Artifacts** (large tables, CSV exports) are stored server-side; the markdown contains links/references, not inlined data.
- **Streaming.** For long summaries, the tool can stream markdown chunks as they are verified, with a final envelope. v1 supports non-streaming; streaming is a v1.1 addition.

### 4.5 Latency Budget (Targets)

| Stage | Target | Notes |
|---|---|---|
| Gateway + validation | < 50 ms | |
| Data resolve + normalize | 100 ms – 2 s | Depends on data size and connector |
| Profile | 50 ms – 500 ms | One pass over data |
| Fact planning | 50 ms (rule-based) or 500 ms – 1 s (LLM) | |
| Data engine (aggregations) | 100 ms – 3 s | DuckDB over millions of rows |
| Markdown planning (LLM) | 500 ms – 1.5 s | Small model, cache-friendly |
| Prose generation (LLM) | 1 – 3 s | Dominant cost |
| Verification + sanitization | < 100 ms | |
| **Total (p50)** | **2 – 5 s** | For typical requests |
| **Total (p95)** | **< 10 s** | Including large data |

Streaming reduces perceived latency for long outputs.


### 4.6 Data Flow in Detail

```
Caller (AI agent)
  |
  |  { datasets: [DataRef], request: string, options: {...} }
  v
Gateway  -- validates shape, checks auth, enforces limits
  |
  v
Validator  -- schema check, id format, relationship validity
  |
  v
Resolver  -- for each DataRef:
  |           file    -> read + parse (CSV/JSON/Parquet)
  |           table   -> SQL query via connector
  |           handle  -> fetch from handle store
  |           url     -> fetch from allow-listed URL
  |           inline  -> parse inline JSON/CSV
  v
Normalizer -- flatten nested JSON (depth 3), paginate, union schemas
  |
  v
Profiler  -- one pass: row counts, null rates, distinct counts, min/max, top values
  |
  v
Fact Planner -- rule-based shortlist + LLM ranking -> FactSpecs
  |
  v
Data Engine -- DuckDB executes FactSpecs over full tables -> FactSet
  |
  v
Markdown Planner -- LLM assigns facts to sections, orders sections
  |
  v
Prose Generator -- LLM turns facts + plan into markdown
  |
  v
Verifier  -- extracts numbers, matches to facts, checks claims
  |  \
  |   \-- on failure: repair prompt -> re-verify (max 2 attempts)
  |       on still failing: safe fallback (replace unverifiable claims)
  v
Sanitizer -- strip raw HTML, JS URIs, event handlers; allow-list check
  |
  v
Artifact Store -- if markdown too large, store tables as artifacts
  |
  v
Envelope  -- { markdown, facts, warnings, artifacts, usage }
  |
  v
Caller + User (markdown rendered in UI)
```

Each stage is independently testable and has a clear input/output contract. Stages 0-3 are deterministic; stages 4-5 involve LLM calls; stages 6-9 are deterministic again.

### 4.7 Failure Modes and Degradation

| Failure | Detection | Degradation |
|---|---|---|
| Data source unreachable | Resolver timeout / error | `E_DATA_NOT_FOUND`, no markdown |
| Data too large (>10M rows, no push-down) | Row count check | `W_TRUNCATED` + summary over available data |
| LLM planner fails | Timeout / error | Fallback to rule-based section plan |
| LLM prose fails | Timeout / error | Template-based fallback (fact table + minimal prose) |
| Verifier finds mismatches | Number extraction + matching | Repair loop; safe fallback if unrepairable |
| Sanitizer finds injection | Pattern match | Strip offending content, emit `W_SANITIZED` |

No failure mode delivers unverified numbers as if they were verified. Every degradation is signaled in the envelope warnings.

### 4.8 Caching Architecture

```
Request hash (datasets fingerprint + request + options)
  |
  +-- Profile cache (TTL 1h) -- hit? reuse profile
  |
  +-- Fact set cache (TTL 30m) -- hit? reuse facts
  |
  +-- Plan cache (TTL 30m) -- hit? reuse section plan
  |
  +-- Prose cache (TTL 15m) -- hit? reuse markdown (only for identical requests)
```

Cache keys are content-addressed (hash of normalized data fingerprint + request). Cache is in-memory with optional Redis backing for multi-instance deployments. Invalidation is TTL-based; explicit invalidation on data change notification.

### 4.9 Deployment Topology

```
                    +------------------+
                    |   Load Balancer  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
         +----+----+    +----+----+    +----+----+
         | Tool    |    | Tool    |    | Tool    |
         | Instance|    | Instance|    | Instance|
         | (stateless)  |         |    |         |
         +----+----+    +----+----+    +----+----+
              |              |              |
              +--------------+--------------+
                             |
              +--------------+--------------+
              |  Shared State              |
              |  - Cache (Redis)           |
              |  - Artifact Store (S3/GCS) |
              |  - Handle Store (DB)       |
              +----------------------------+
                             |
              +--------------+--------------+
              |  Data Sources              |
              |  - Files, Warehouses, APIs |
              +----------------------------+
```

Tool instances are stateless; all state is in shared stores. Horizontal scaling is linear. Each instance embeds DuckDB for data engine work (no external DB needed for computation).

### 4.10 Configuration Surface

| Config Key | Default | Description |
|---|---|---|
| `engine` | `duckdb` | Data engine (`duckdb` or `pandas`) |
| `planner_model` | `gpt-4o-mini` | Model for planning call |
| `prose_model` | `gpt-4o-mini` | Model for prose call |
| `max_rows` | `10000000` | Max rows before truncation warning |
| `max_pages` | `1000` | Max pagination pages |
| `max_facts` | `20` | Max facts per summary |
| `verify_tolerance` | `0.01` | Default numeric tolerance |
| `cache_ttl_profile` | `3600` | Profile cache TTL (seconds) |
| `cache_ttl_facts` | `1800` | Fact set cache TTL |
| `llm_timeout` | `10` | LLM call timeout (seconds) |
| `max_repair_attempts` | `2` | Verifier repair attempts |

All config is via `config/default.yaml` with environment variable overrides. No secrets in config files.

### 4.11 Scaling Characteristics

| Dimension | v1 Limit | Scaling Strategy |
|---|---|---|
| Rows per dataset | 10M | Push-down aggregation; no row serialization |
| Datasets per request | 8 | Parallel connector fetching |
| Columns per dataset | 100 | Profile sampling for wide tables |
| Concurrent requests | 100/instance | Stateless design; horizontal scaling |
| Request rate | 60/min/key | Rate limiting with token bucket |
| Data size per request | 1GB scanned | Engine streaming; no full materialization |

The bottleneck is typically the LLM call (1-3s), not data processing. For very large datasets (100M+ rows), the engine pushes aggregation to the source database (if table-backed) or uses chunked processing (if file/URL-backed).

### 4.12 Failure Modes and Recovery

| Failure | Detection | Recovery |
|---|---|---|
| LLM timeout | 30s timer | Retry once; fallback provider; template fallback |
| Engine OOM | Memory monitor | Reduce data scope; return partial with warning |
| Connector failure | HTTP/DB error | Retry with backoff; return error envelope |
| Verifier failure | Number mismatch | Repair loop (1 retry); template fallback |
| Cache corruption | Checksum mismatch | Invalidate and recompute |
| Artifact store down | Write error | Truncate inline with warning |

All failures produce a well-formed response envelope (never a raw exception). The caller always gets a JSON response with status, error code, and actionable message.

### 4.13 Data Flow Diagram

```
Caller                    Gateway                 Pipeline
  |                         |                       |
  |-- POST /v1/summarize -->|                       |
  |   {datasets, request}   |-- validate ---------> |
  |                         |<- profile ----------->|
  |                         |-- plan facts -------> |
  |                         |-- compute facts ----> |
  |                         |-- plan markdown ----> |
  |                         |-- generate prose ---> |
  |                         |   (LLM call)          |
  |                         |-- verify -----------> |
  |                         |-- sanitize --------> |
  |                         |<- envelope ----------|
  |<-- {markdown, facts} ---|                       |
  |                         |                       |
  |-- POST /v1/summarize -->|  (follow-up edit)     |
  |   {prior_id, edit}      |-- load prior ------> |
  |                         |-- re-verify --------> |
  |<-- {markdown, facts} ---|                       |
```

Follow-up edits skip profiling and fact computation when the data has not changed (cache hit on data hash).

### 4.14 Technology Choices

| Component | Choice | Rationale |
|---|---|---|
| Data engine | DuckDB (primary), pandas (fallback) | DuckDB is fast, in-process, SQL-compatible; pandas for edge cases |
| LLM abstraction | Custom interface + adapters | Avoid framework lock-in (LangChain etc.) |
| API framework | FastAPI | Async, typed, auto-docs |
| Cache | In-memory LRU + optional Redis | Simple default, scalable option |
| Artifact store | Filesystem / S3 | Configurable; no hard dependency |
| Observability | OpenTelemetry | Standard, vendor-neutral |

No heavy framework (LangChain, LlamaIndex) is used -- the pipeline is custom-built for this specific task. Framework overhead is not justified for a single-tool service.

