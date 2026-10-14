## 7. Data Handling

### 7.1 Normalization of Nested and Paginated Data

**Nested JSON flattening.** Service responses often contain nested objects and arrays. The normalizer flattens with these rules:

| Input Shape | Output | Example |
|---|---|---|
| Nested object `{"user": {"name": "Alice"}}` | Dotted column `user.name` | `user.name = "Alice"` |
| Array of primitives `{"tags": ["a","b"]}` | JSON column | `tags = ''["a","b"]''` |
| Array of objects `{"items": [{"id":1}]}` | Child table with FK | `items` table with `parent_id` |
| Mixed nesting | Recursive flatten to depth 3 | Deeper nesting becomes JSON column |

Original JSON paths are preserved in column metadata for attribution. Depth beyond 3 is truncated with `W_NESTING_TRUNCATED`.

**Paginated responses.** The connector handles pagination server-side:

| Strategy | How It Works | Dedup |
|---|---|---|
| Cursor-based | Follow `next_cursor` until null | By declared key |
| Offset/limit | Increment offset until short page | By key |
| Page token | Follow `next_page_token` | By key |
| Link header | Follow `Link: rel="next"` | By key |

The tool sees one logical table. Max pages (1000) and max rows (10M) are configurable; exceeding either emits `W_PAGINATION_TRUNCATED`.

**Heterogeneous schemas.** Pages with differing columns are unioned with null-fill. Type conflicts widen (e.g., `integer` + `string` -> `string`) with a warning.

### 7.2 Profiling

Single pass over full normalized data:

| Stat | How Computed |
|---|---|
| Row count | `COUNT(*)` |
| Null counts | `COUNT(*) - COUNT(col)` per column |
| Distinct counts | `APPROX_COUNT_DISTINCT` (HyperLogLog) |
| Min/max | `MIN`/`MAX` per column |
| Mean/median/std | `AVG`, `MEDIAN`, `STDDEV` for numeric |
| Top values | `GROUP BY col ORDER BY COUNT(*) DESC LIMIT 5` |
| Time grain | Detect datetime columns, infer from span and row count |

If caller provides a profile, tool verifies row count and column names; mismatches emit `W_PROFILE_MISMATCH` and trigger recompute.

### 7.3 Computation Over the Full Data

All numeric facts are computed over full data via push-down SQL. No sampling for final numbers.

| Fact Kind | SQL Pattern |
|---|---|
| Count / sum / mean | `SELECT COUNT(*), SUM(x), AVG(x) FROM t WHERE ...` |
| Top N | `SELECT col, COUNT(*) FROM t GROUP BY col ORDER BY 2 DESC LIMIT N` |
| Trend (slope) | `SELECT REGR_SLOPE(y, x) FROM (SELECT bucket, SUM(metric) ...)` |
| Period comparison | Two aggregations + arithmetic |
| Anomaly | `WHERE metric > mean + 3*stddev` (z-score or IQR) |
| Distribution | `SELECT WIDTH_BUCKET(x, min, max, 10), COUNT(*)` |

Queries are parameterized; never string-interpolated from data values.

### 7.4 Handling Scale

| Data Size | Strategy |
|---|---|
| < 100K rows | Direct DuckDB in-process |
| 100K - 10M rows | DuckDB columnar, may spill to disk |
| > 10M rows | Push-down to source (warehouse) if possible; else chunked aggregation |
| Streaming | Incremental aggregation (v1.1); v1 snapshots |

Sampling is never used for final numbers. A 5-row sample is shown to LLM only for planning.

### 7.5 Nulls, Types, Time, and Joins

- **Nulls.** Excluded from aggregations; reported in profile. Facts with >30% nulls include a caveat.
- **Types.** Safe coercion only: `string "123"` -> `integer` only if entire column is numeric strings. Otherwise stays `string`.
- **Time.** Detected by name (`*_at`, `*_date`) and parsing. Grain inferred from span/row count. Gaps detected. All times normalized to UTC.
- **Joins.** Only declared relationships are used; tool never guesses joins.

| Join Fact | Example |
|---|---|
| Orphan detection | "2,000 orders (0.14%) have no matching customer" |
| Fan-out | "Customers average 15.9 orders each" |
| Cross-dataset aggregate | "Revenue per segment (joining orders + customers)" |
| Time alignment | "Orders and events correlated by day" |

### 7.6 Edge Cases in Normalization

| Edge Case | Handling |
|---|---|
| Empty dataset (0 rows) | Profile reports 0 rows; fact engine returns no facts; prose notes no data available |
| Single row | All aggregations trivially return that rows values; no trends/anomalies |
| All nulls in a column | Column excluded from numeric facts; warning W_ALL_NULLS |
| Duplicate rows | Preserved as-is; dedup only for pagination (by declared key) |
| Extremely wide table (>500 columns) | Profile samples columns; fact planner considers top columns by relevance |
| Binary / blob columns | Excluded from profiling and facts; noted in warnings |
| Circular references in JSON | Detected and truncated at depth 3 with W_CIRCULAR_REF |

### 7.7 Performance Characteristics

| Operation | Time (1M rows, 10 cols) | Time (10M rows, 10 cols) |
|---|---|---|
| Normalization (flatten) | ~200ms | ~1.5s |
| Profiling (one pass) | ~150ms | ~800ms |
| Fact execution (10 facts) | ~300ms | ~2s |
| Total deterministic stages | ~650ms | ~4.3s |

DuckDB performance is columnar and benefits from predicate pushdown. For datasets exceeding memory, DuckDB spills to disk automatically.

### 7.8 Data Lineage and Provenance

Every fact records its lineage with datasets, query, rows scanned, computation time, engine, and source path. Lineage is included in the envelope for audit. The markdown may include compact provenance footnotes (configurable). This enables debugging and compliance.

### 7.9 Incremental Updates (v1.1 Preview)

v1 operates on snapshots. v1.1 will support incremental updates: caller sends base_summary_id plus new/changed datasets, tool diffs against cached fingerprint, only affected facts are recomputed, prose is patched for changed facts. This reduces latency for dashboard refresh from seconds to hundreds of milliseconds.

### 7.10 Null and Missing Value Semantics

Null handling is explicit at every stage:

| Stage | Null Behaviour |
|---|---|
| Profiling | Counts nulls per column; reports null fraction |
| Fact computation | Aggregations skip nulls (SQL semantics) |
| Prose | Facts include null context when material |
| Verification | Null-related numbers verified like any other fact |

The LLM prompt includes null counts so it can mention data completeness when relevant.

### 7.11 Duplicate Detection and Handling

Duplicates are detected during profiling:

- **Exact duplicates:** Rows where all columns match. Reported as count and fraction.
- **Key duplicates:** Rows where the declared or inferred key has duplicate values.
- **Near duplicates:** Not detected in v1 (requires fuzzy matching; deferred).

Facts about duplicates are generated when the duplicate fraction exceeds 1 percent. Deduplication is not automatic -- the caller decides whether to deduplicate upstream.

### 7.12 Data Freshness and Staleness

For handle and URL data refs, freshness is tracked:

- **Handle:** Metadata includes creation timestamp. Handles older than 1 hour produce a staleness warning.
- **URL:** HTTP response headers (Last-Modified, ETag) are checked. Unchanged data reuses the cached profile.
- **Table/file:** Freshness not tracked in v1 (caller manages it).

Staleness warnings appear in the response envelope and may be mentioned in prose.

### 7.13 Large Text Fields and Truncation

Text columns with large values (log messages, descriptions) are handled specially:

- **Profiling:** Only the first 200 characters per value are used for distinct counts and length stats.
- **Fact computation:** Text aggregations use truncated values for grouping but report the full value when it fits within 500 chars.
- **LLM context:** Sample rows truncate text fields to 100 characters. The LLM is told values are truncated.

### 7.14 Schema Evolution and Compatibility

Datasets may change schema between requests. Handling:

- **New columns:** Detected during profiling; new facts may be generated. No error.
- **Removed columns:** Facts referencing removed columns fail gracefully (warning added; prose omits that finding).
- **Renamed columns:** Treated as remove plus add. No automatic alias resolution in v1.
- **Type changes:** Normalizer re-infers the type. Facts assuming the old type may fail.

For follow-up edits with prior_summary_id, schema changes are detected by comparing the new profile to the cached prior profile.

### 7.15 Data Lineage and Provenance

Every fact carries provenance metadata for auditability:

| Field | Example | Purpose |
|---|---|---|
| source_dataset | sales | Which dataset the fact came from |
| source_query | SELECT SUM(revenue) FROM sales | How the value was computed |
| computed_at | 2026-10-14T10:30:00Z | When it was computed |
| row_count | 10000 | How many rows were scanned |
| engine | duckdb | Which engine computed it |

Provenance is included in the response envelope facts array. The markdown itself does not include provenance (to keep it readable), but the top model can inspect it for debugging or audit.

For join-aware facts, provenance includes both datasets and the join condition:

```json
{"source_datasets": ["orders", "customers"], "join_on": "customer_id", "join_type": "many_to_one"}
```

### 7.16 Incremental Updates and Change Detection

For datasets that change between requests (e.g., a table with new rows), the tool detects changes:

- **Row count change:** Compare current COUNT(*) to cached count. If different, invalidate cached profile and facts.
- **Schema change:** Compare current column list to cached schema. If different, invalidate and re-profile.
- **Content change:** For file/URL sources, compare ETag or Last-Modified header.

Change detection is lightweight (single COUNT query or header check) and runs before the full pipeline. If no change is detected, cached results are reused.

### 7.17 Performance Characteristics by Data Size

| Rows | Profiling | Fact Computation | Total (excl. LLM) |
|---|---|---|---|
| 1K | 10ms | 20ms | 30ms |
| 100K | 80ms | 150ms | 230ms |
| 1M | 400ms | 600ms | 1s |
| 10M | 2s | 3s | 5s |
| 100M | 15s | 20s | 35s (needs push-down) |

For 100M+ rows, the engine pushes aggregation to the source database (if table-backed) rather than scanning locally. File/URL sources at this scale require chunked processing or pre-aggregation.

