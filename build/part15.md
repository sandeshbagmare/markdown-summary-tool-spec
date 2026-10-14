## 19. Comparison with Existing Approaches

### 19.1 How This Design Compares

| Approach | Faithfulness | Scale | Cost | Steering | Security | Maturity |
|---|---|---|---|---|---|---|
| **This tool (compute-then-write)** | High (verified) | Full-data push-down | Low (1 small LLM call) | Full (options + edits) | Strong (isolated data, sanitized output) | New; needs eval |
| End-to-end LLM over serialized data | Low (hallucinates) | Fails on large data | High (large context) | Prompt-dependent | Weak (data as instructions) | Widely tried |
| LLM writes code (PandasAI etc.) | Medium (code may be wrong) | Good (code runs on full data) | Medium | Prompt-dependent | Weak (code execution) | Popular but fragile |
| BI templates (Power BI etc.) | High (deterministic) | Excellent | Low (no LLM) | Template-limited | Strong | Mature |
| Agent framework (LangChain etc.) | Varies | Varies | Varies | Framework-dependent | Varies | Mature framework, immature summaries |

### 19.2 Honest Assessment

**Where this design is stronger:**

- Faithfulness is mechanically enforced, not hoped for.
- Scale is handled by the engine, not by truncating data to fit a context window.
- Cost is predictable and low.
- Security is built in, not bolted on.

**Where this design is weaker:**

- Less fluent than a large model writing freely -- grounding constraints reduce creativity. For most data summaries this is the right trade-off, but it may feel "templated" for narrative-heavy requests.
- Fact planning is heuristic -- it may miss a finding that a human analyst would surface. The eval set must measure coverage, not just accuracy.
- Multi-dataset reasoning is limited to declared relationships -- no automatic join discovery.
- Free-text log summarization (e.g., "summarize these error messages") still relies on LLM quality over chunks; the verifier cannot check qualitative claims.
- Initial eval set (115 cases) is modest -- real-world diversity will be larger.

**What would make us reconsider:**

- If a new model class achieves near-perfect numeric faithfulness without grounding, the verifier could be relaxed (but not removed).
- If users consistently want more narrative flair than grounded prose allows, a "creative mode" with explicit unverified-content markers could be added.

## 20. Roadmap, Risks, Open Questions and Acceptance

### 20.1 Phased Roadmap (Rough Estimates)

| Phase | Scope | Estimate |
|---|---|---|
| Phase 1 (v1) | Single + multi-dataset, push-down engine, verified prose, steering, edits, security | 8-10 weeks, 3-4 engineers |
| Phase 1.1 | Streaming output, artifact store polish, locale formatting | 2-3 weeks |
| Phase 2 | Incremental/streaming data, richer anomaly detection, correlation facts | 4-6 weeks |
| Phase 3 | Auto join discovery, learned preferences, richer eval set | Ongoing |

### 20.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Verifier false positives (correct prose flagged as wrong) | Medium | Annoying repairs | Tune tolerance; locale-aware number parsing; test per locale |
| Fact planner misses important findings | Medium | Incomplete summaries | Eval coverage metric; human review of eval set |
| LLM provider outage | Low | No summaries | Fallback provider; cached plans for repeated requests |
| Data scale exceeds engine (100M+ rows) | Low | Slow or OOM | Push-down to warehouse; chunked aggregation |
| Prompt injection via novel technique | Low | Security breach | Defense in depth; security review; adversarial eval |

### 20.3 Open Questions for the Owner

| # | Question | Recommendation |
|---|---|---|
| 1 | Should markdown include inline fact citations (e.g., `[f7]`) for audit, or strip them for clean reading? | Strip by default; include when `options.include_citations` is true |
| 2 | What is the max acceptable p95 latency? | 10s as initial SLO; measure and tighten |
| 3 | Which LLM provider(s) should be primary? | Small/cheap model; bake-off decides (Section 15.4) |
| 4 | Should artifacts be stored durably or ephemerally? | Ephemeral (24h) for v1; durable if users request it |
| 5 | How should highly sensitive datasets be handled? | Column redaction + access control at connector; no raw data in LLM context |
| 6 | Should the tool support chart generation alongside markdown? | No for v1 -- that is the sibling Visualization Tool; combine at the agent level |

### 20.4 Acceptance Criteria for v1

- [ ] All 115 eval cases pass numeric accuracy (100%) and claim accuracy (100%).
- [ ] Fact coverage >= 80%, fluency >= 4.0/5 on human eval.
- [ ] p50 latency < 5s, p95 < 10s on eval set.
- [ ] Security review passes: no prompt injection, no markdown injection, no data leakage on adversarial cases.
- [ ] All error codes return correctly with actionable messages.
- [ ] Follow-up edits work for length, language, focus, and data changes.
- [ ] Documentation complete: API reference, top-model guidance, operational runbook.

## 21. Appendices

### Appendix A. Request JSON Schema (Compact)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "CreateMarkdownSummaryRequest",
  "type": "object",
  "required": ["datasets", "request"],
  "properties": {
    "datasets": {"type": "array", "minItems": 1, "maxItems": 8, "items": {"$ref": "#/$defs/Dataset"}},
    "request": {"type": "string", "minLength": 1, "maxLength": 2000},
    "relationships": {"type": "array", "items": {"$ref": "#/$defs/Relationship"}},
    "options": {"$ref": "#/$defs/Options"},
    "prior_summary_id": {"type": "string"},
    "edit_instruction": {"type": "string", "maxLength": 2000},
    "schema_version": {"type": "string", "const": "1.0"}
  },
  "$defs": {
    "Dataset": {
      "type": "object",
      "required": ["id", "data_ref"],
      "properties": {
        "id": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "data_ref": {"$ref": "#/$defs/DataRef"},
        "profile": {"$ref": "#/$defs/Profile"},
        "sample_rows": {"type": "array", "maxItems": 5, "items": {"type": "object"}},
        "name": {"type": "string", "maxLength": 100},
        "description": {"type": "string", "maxLength": 500}
      }
    },
    "DataRef": {
      "oneOf": [
        {"type": "object", "required": ["type", "table"], "properties": {"type": {"const": "table"}, "connection": {"type": "string"}, "table": {"type": "string"}, "query": {"type": "string"}}},
        {"type": "object", "required": ["type", "path"], "properties": {"type": {"const": "file"}, "path": {"type": "string"}, "format": {"enum": ["csv", "parquet", "json"]}}},
        {"type": "object", "required": ["type", "handle_id"], "properties": {"type": {"const": "handle"}, "handle_id": {"type": "string"}}},
        {"type": "object", "required": ["type", "url"], "properties": {"type": {"const": "url"}, "url": {"type": "string", "format": "uri"}, "pagination": {"type": "object"}}},
        {"type": "object", "required": ["type", "data"], "properties": {"type": {"const": "inline"}, "data": {"type": "array", "maxItems": 100, "items": {"type": "object"}}}}
      ]
    },
    "Options": {
      "type": "object",
      "properties": {
        "focus": {"type": "string", "maxLength": 200},
        "audience": {"enum": ["general", "executive", "technical", "analyst"]},
        "length": {"enum": ["short", "medium", "long", "detailed"]},
        "language": {"type": "string", "pattern": "^[a-z]{2}(-[A-Z]{2})?$"},
        "format": {"enum": ["sections", "bullets", "narrative", "table_heavy"]},
        "max_facts": {"type": "integer", "minimum": 1, "maximum": 50},
        "redact": {"type": "array", "items": {"type": "string"}},
        "include_citations": {"type": "boolean"}
      }
    }
  }
}
```

### Appendix B. Response Envelope JSON Schema (Compact)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "MarkdownSummaryEnvelope",
  "type": "object",
  "required": ["status", "schema_version"],
  "properties": {
    "status": {"enum": ["ok", "partial", "error"]},
    "markdown": {"type": "string"},
    "facts": {"type": "array", "items": {"$ref": "#/$defs/Fact"}},
    "warnings": {"type": "array", "items": {"$ref": "#/$defs/Issue"}},
    "artifacts": {"type": "array", "items": {"$ref": "#/$defs/Artifact"}},
    "provenance": {"type": "object"},
    "usage": {"type": "object"},
    "summary_id": {"type": "string"},
    "error": {"$ref": "#/$defs/Issue"},
    "schema_version": {"type": "string", "const": "1.0"}
  }
}
```

### Appendix C. Implementation Checklist

- [ ] Gateway: auth, rate limiting, request validation
- [ ] Connectors: table, file, handle, url (with pagination), inline
- [ ] Normalizer: JSON flattening, schema union, type inference
- [ ] Profiler: single-pass stats, time grain detection
- [ ] Fact planner: rule-based + LLM-assisted
- [ ] Data engine: DuckDB primary, pandas fallback, parameterized queries
- [ ] Markdown planner: section planning (rule-based + LLM)
- [ ] Prose generator: LLM call with grounding constraints
- [ ] Verifier: number extraction, fact matching, claim checking
- [ ] Repair loop: targeted fix + template fallback
- [ ] Sanitizer: HTML/JS/data-URI stripping
- [ ] Artifact store: large table offloading
- [ ] Cache: profile/fact/plan caching
- [ ] Evaluation harness: 115 cases, metrics, gates
- [ ] Security tests: injection, sanitization, redaction
- [ ] Operational: config, telemetry, SLOs, health checks
- [ ] Documentation: API reference, top-model guidance, runbook

### Appendix D. Source List

| # | Title | Authors / Publisher | Date | URL |
|---|---|---|---|---|
| 1 | ToTTo: Controlled Table-To-Text Generation | Parikh et al. (Google) | 2020 | https://arxiv.org/abs/2004.14373 |
| 2 | LogicNLG: An Evaluation for Logical Natural Language Generation | Chen et al. | 2020 | https://arxiv.org/abs/2004.14604 |
| 3 | FeTaQA: Free-form Table Question Answering | Nan et al. | 2021 | https://arxiv.org/abs/2104.00369 |
| 4 | TAPEX: Table Pre-training via Learning a Neural SQL Executor | Liu et al. (Microsoft) | 2021 | https://arxiv.org/abs/2107.07653 |
| 5 | Hallucination in Data-to-Text Generation | Ji et al. | 2022 | https://arxiv.org/abs/2206.11400 |
| 6 | Faithfulness in Natural Language Generation: A Survey | Huang et al. | 2023 | https://arxiv.org/abs/2303.03342 |
| 7 | DuckDB Documentation | DuckDB Labs | 2024 | https://duckdb.org/docs/ |
| 8 | CommonMark Specification | CommonMark | 2024 | https://spec.commonmark.org/ |
| 9 | OWASP Top 10 for LLM Applications | OWASP | 2024 | https://owasp.org/www-project-top-10-for-large-language-model-applications/ |
| 10 | Power BI Documentation | Microsoft | 2024 | https://learn.microsoft.com/en-us/power-bi/ |
| 11 | Grafana Documentation | Grafana Labs | 2024 | https://grafana.com/docs/ |
| 12 | LangChain Documentation | LangChain | 2024 | https://python.langchain.com/ |
| 13 | LlamaIndex Documentation | LlamaIndex | 2024 | https://docs.llamaindex.ai/ |
| 14 | Great Expectations Documentation | Great Expectations | 2024 | https://docs.greatexpectations.io/ |
| 15 | Evaluation of Text Generation: A Survey | Celikyilmaz et al. | 2021 | https://arxiv.org/abs/2006.14799 |

*Note: Sources are representative. A production spec would include full verification of each cited claim against its source.*

### Appendix E. Revision History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-10-14 | Engineering | Initial draft for review |

---

*End of specification. For questions, contact the engineering team or file an issue against this document.*

### Appendix F. Glossary

| Term | Definition |
|---|---|
| Artifact | A large table or data object offloaded from the inline response to external storage |
| Compute-then-write | Architecture where a deterministic engine computes facts and the LLM only verbalizes them |
| DataRef | A reference to a dataset (table, file, handle, URL, or inline data) |
| Fact | A single computed finding (stat, trend, comparison, distribution, etc.) with a verified numeric value |
| Fact spec | A declaration of what fact to compute (kind, column, filter, etc.) before computation |
| Normalizer | Pipeline stage that flattens JSON, unions schemas, and infers column types |
| Profile | Statistical summary of a dataset (row count, column types, null fractions, distinct counts) |
| Provenance | Metadata about how a fact was computed (source, query, timestamp) |
| Sanitizer | Pipeline stage that strips dangerous markdown (HTML, JS URIs, event handlers) |
| Verifier | Pipeline stage that checks every number in prose against the fact set |
| Envelope | The JSON response wrapper containing markdown, facts, warnings, and artifacts |

### Appendix G. Error Code Reference

| Code | HTTP Status | Retryable | Description |
|---|---|---|---|
| SCHEMA_ERROR | 400 | No | Request JSON fails schema validation |
| DATA_REF_ERROR | 400/502 | Sometimes | Data source unreachable or invalid |
| DATA_TOO_LARGE | 413 | No | Dataset exceeds size limits |
| FACT_COMPUTATION_ERROR | 422 | No | Fact query failed (e.g., column not found) |
| LLM_ERROR | 502 | Yes | LLM provider error or timeout |
| VERIFICATION_FAILED | 500 | Yes | Prose failed verification after repair |
| TIMEOUT | 504 | Yes | Request exceeded time limit |
| RATE_LIMITED | 429 | Yes | Rate limit exceeded |
| AUTH_ERROR | 401 | No | Invalid or missing API key |
| INTERNAL_ERROR | 500 | Yes | Unexpected server error |

### Appendix H. Fact Kind Reference

| Kind | Description | Example Value |
|---|---|---|
| stat | Single aggregate (count, sum, mean, min, max) | `{"kind": "stat", "column": "revenue", "agg": "sum", "value": 1234567.89}` |
| trend | Time-series direction and magnitude | `{"kind": "trend", "column": "revenue", "direction": "up", "change_pct": 12.3}` |
| comparison | Cross-group comparison | `{"kind": "comparison", "column": "revenue", "group": "region", "top": "West", "value": 450000}` |
| distribution | Value distribution (histogram, top-N) | `{"kind": "distribution", "column": "status", "top_values": [{"value": "active", "count": 800}]}` |
| correlation | Correlation between two columns | `{"kind": "correlation", "columns": ["price", "demand"], "value": -0.72}` |
| anomaly | Outlier or anomaly detection | `{"kind": "anomaly", "column": "revenue", "anomaly_count": 3, "max_z": 4.2}` |
| completeness | Data quality (nulls, duplicates) | `{"kind": "completeness", "column": "email", "null_fraction": 0.05}` |

### Appendix I. Markdown Feature Support

| Feature | Supported | Notes |
|---|---|---|
| Headings (H1-H4) | Yes | H1 for title, H2 for sections, H3-H4 for subsections |
| Paragraphs | Yes | Justified body text |
| Bullet lists | Yes | Unordered lists with dash or asterisk |
| Numbered lists | Yes | Ordered lists |
| Tables | Yes | GFM tables with header row and alignment |
| Code blocks | Yes | Fenced code blocks with language hint |
| Inline code | Yes | Backtick spans |
| Bold/italic | Yes | Strong and emphasis |
| Links | Yes | Only to artifact URLs or allow-listed domains |
| Images | No | Not generated (no image data in facts) |
| Raw HTML | No | Stripped by sanitizer |
| Footnotes | No | Not needed for data summaries |
| Task lists | No | Not needed |

### Appendix J. Performance Benchmarks (Estimated)

| Scenario | Rows | Datasets | Facts | Latency (p50) | Latency (p95) |
|---|---|---|---|---|---|
| Small single dataset | 1K | 1 | 8 | 1.5s | 3s |
| Medium single dataset | 100K | 1 | 15 | 2.5s | 5s |
| Large single dataset | 10M | 1 | 20 | 4s | 8s |
| Multi-dataset (3) | 50K each | 3 | 25 | 4s | 8s |
| With LLM planning | 100K | 1 | 15 | 3.5s | 7s |
| Follow-up edit (cached) | 100K | 1 | 15 | 1.5s | 3s |

Benchmarks assume DuckDB engine, small LLM (Haiku/Flash), and warm cache where noted. Cold starts add approximately 500ms for engine initialization.

### Appendix K. API Endpoint Reference

| Endpoint | Method | Purpose |
|---|---|---|
| /v1/summarize | POST | Create a new markdown summary |
| /v1/summarize/{id} | GET | Retrieve a prior summary by id |
| /v1/artifacts/{id} | GET | Retrieve an offloaded artifact |
| /health | GET | Health check (engine + LLM status) |
| /metrics | GET | Prometheus metrics endpoint |

All endpoints except /health and /metrics require authentication via `Authorization: Bearer <token>`.

**POST /v1/summarize -- Request:**

```json
{
  "datasets": [{"id": "sales", "data_ref": {"type": "table", "table": "sales"}}],
  "request": "Summarize sales performance",
  "options": {"length": "medium", "audience": "general"},
  "schema_version": "1.0"
}
```

**POST /v1/summarize -- Response (success):**

```json
{
  "status": "ok",
  "markdown": "# Sales Summary\n\nTotal revenue was $1,234,567...",
  "facts": [{"id": "f1", "kind": "stat", "value": 1234567.89, ...}],
  "warnings": [],
  "artifacts": [],
  "provenance": {"request_id": "req_abc123", "computed_at": "2026-10-14T10:30:00Z"},
  "usage": {"input_tokens": 1800, "output_tokens": 900, "cost_usd": 0.002},
  "summary_id": "sum_xyz789",
  "schema_version": "1.0"
}
```

**POST /v1/summarize -- Response (error):**

```json
{
  "status": "error",
  "error": {"code": "DATA_REF_ERROR", "message": "Table not found: sales_typo", "retryable": false},
  "schema_version": "1.0"
}
```

### Appendix L. Configuration File Example

```yaml
# config.yaml -- Markdown Summary Tool configuration
llm:
  provider: anthropic
  model: claude-3-5-haiku-20241022
  timeout: 30s
  max_retries: 2
  fallback:
    provider: openai
    model: gpt-4o-mini

engine:
  type: duckdb
  memory_limit: 2GB
  threads: 4

cache:
  ttl: 1h
  max_size: 1000
  redis_url: redis://localhost:6379  # optional

artifacts:
  ttl: 24h
  backend: s3
  s3_bucket: my-artifacts-bucket
  s3_prefix: markdown-summaries/

limits:
  max_rows: 10000000
  max_datasets: 8
  max_pages: 1000
  max_markdown_kb: 500

server:
  host: 0.0.0.0
  port: 8080
  workers: 4
  log_level: info
```

### Appendix M. Changelog

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0 | 2026-10-14 | Engineering | Initial draft for review |
| 1.0.1 | (future) | -- | Incorporate review feedback |
| 1.1 | (future) | -- | Streaming output, locale formatting polish |

### Appendix N. References and Further Reading

| # | Topic | Recommended Reading |
|---|---|---|
| 1 | Data-to-text generation | Reiter and Dale, Building Natural Language Generation Systems (2000) |
| 2 | Table understanding | Yin et al., TaBERT: Pretraining for Joint Understanding of Textual and Tabular Data (2020) |
| 3 | Faithfulness evaluation | Maynez et al., On Faithfulness and Factuality in Abstractive Summarization (2020) |
| 4 | Prompt injection | Perez and Ribeiro, Ignore Previous Prompt: Attack Techniques For Language Models (2022) |
| 5 | DuckDB internals | Raasveldt and Muehleisen, DuckDB: An Embeddable Analytical Database (2019) |
| 6 | Markdown security | OWASP, Cross-Site Scripting Prevention Cheat Sheet (2024) |
| 7 | Evaluation methodology | Chang et al., A Survey on Evaluation of Large Language Models (2023) |

