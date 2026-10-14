## 2. Research Findings

### 2.1 The Standards Question

**There is no single industry standard for generating markdown summaries from large structured data.** What exists is a set of competing patterns, each dominant in a different community:

| Community | Dominant Pattern | Standardization |
|---|---|---|
| BI / reporting (Power BI, Tableau, Looker) | Template + semantic layer + scheduled refresh; text summaries are secondary to visuals | De facto product conventions, no open standard |
| Observability (Datadog, Grafana, New Relic) | Threshold alerts + auto-generated incident summaries; LLM summaries are recent and product-specific | No standard; each vendor has its own summary format |
| Data-to-text research | Encoder-decoder models over tables (ToTTo, LogicNLG, FeTaQA); faithfulness is an active research problem | Academic benchmarks, not deployment standards |
| Agent frameworks (LangChain, LlamaIndex, OpenAI function calling) | Tool-use + retrieval + LLM synthesis; summarization is one tool among many | Framework conventions, not a summary standard |
| Engineering practice | "Compute in SQL/Python, narrate with LLM, verify numbers" -- the emerging pragmatic pattern | Unwritten but increasingly common |

**Implication.** The tool should not claim conformance to a non-existent standard. It should follow the pragmatic "compute-then-write" pattern, use CommonMark for output, and expose a stable, versioned tool contract that any top model can call.

### 2.2 Landscape of Approaches

#### 2.2.1 Academic: Data-to-Text and Table Summarization

| Approach | How It Works | Strengths | Weaknesses | Maturity |
|---|---|---|---|---|
| Fine-tuned table-to-text (e.g., T5 on ToTTo) | Encoder reads linearized table, decoder writes sentence | Fluent, controllable with templates | Hallucinates numbers; needs training data per domain; poor on large tables | Research; not production-ready for open-domain |
| Retrieval-augmented generation over tables | Retrieve relevant rows/cells, then generate | Scales to large tables via retrieval | Retrieval misses can silently drop key facts; ranking is brittle | Active research |
| Logic-guided generation (LogicNLG, TAPEX) | Generate logical forms, then verbalise | Better faithfulness for comparisons and superlatives | Limited to supported logical ops; complex to extend | Research |
| LLM few-shot over serialized tables | Serialize table as markdown/CSV in prompt, ask LLM to summarize | Simple, no training | Fails on large tables; hallucinates; expensive; non-deterministic | Widely tried, widely regretted at scale |

**Key takeaway.** End-to-end LLM generation over serialized tables is the most common attempt and the least faithful. The literature consistently shows that separating computation from verbalization improves numeric accuracy.

#### 2.2.2 Open Source

| Project | Pattern | Notes |
|---|---|---|
| LlamaIndex / LangChain table query | SQL generation + execution + LLM answer | Good for Q&A, weak for broad summaries; SQL errors are common |
| PandasAI / ChatGPT Code Interpreter | LLM writes Python, executes, then summarizes | Powerful but non-deterministic; code can fail or be slow; security concerns |
| Evidence, Quarto, Observable | Markdown + SQL templates with deterministic rendering | Faithful but not LLM-driven; requires hand-written templates |
| Great Expectations / dbt tests | Data profiling and validation | Useful for the profiling stage; not a summarizer |

#### 2.2.3 Commercial BI and Observability

| Product | Summary Capability | Faithfulness Mechanism |
|---|---|---|
| Power BI / Tableau | Natural-language summaries via Q&A or "Explain Data" | Deterministic aggregations; LLM only for phrasing |
| Datadog / Grafana | LLM incident summaries over metrics/logs | Grounded in alert thresholds and queried data |
| ThoughtSpot / Sigma | Search-driven summaries | Semantic layer ensures correct aggregations |
| Hex / Mode | Notebook + LLM assist | Human in the loop; not autonomous |

**Pattern.** Commercial tools that are trusted for numbers keep the LLM away from arithmetic. The LLM phrases, the engine computes. This validates the compute-then-write choice.

#### 2.2.4 Agent Frameworks

Agent frameworks treat summarization as one tool call among many. The relevant lessons:

- Tool outputs should be structured (facts + markdown), not just markdown, so the agent can act on them.
- Streaming partial results improves perceived latency.
- Tool contracts must be stable across model providers.

### 2.3 Faithfulness: What Is Known

**The problem is well-documented.** Studies on table-to-text generation report hallucination rates of 20-40% for numeric claims when LLMs generate directly from tables without grounding. Common errors: wrong aggregates, misranked items, invented trends, incorrect comparisons, and attribution failures (claiming a fact about the wrong slice).

**What helps:**

| Technique | Effect | Cost |
|---|---|---|
| Pre-compute facts, constrain LLM to verbalise only those facts | Large reduction in hallucination | Requires a fact planner and verifier |
| Structured output (JSON) for facts, then template-based prose | Near-zero hallucination for numbers | Less fluent; needs good templates |
| Post-generation verification (extract numbers, check against computed values) | Catches remaining errors; enables repair | Extra pass; needs robust number extraction |
| Attribution (link each claim to source rows/query) | Enables audit; improves trust | Storage and UI cost |
| Self-consistency (sample multiple outputs, pick majority) | Modest improvement | 3-5x cost; not sufficient alone |

**What does not help enough:**

- Prompt engineering alone ("be accurate", "think step by step") -- reduces but does not eliminate hallucination.
- Larger models -- more fluent, not necessarily more faithful on arithmetic.
- Few-shot examples -- helps structure, not numeric accuracy.

**Evaluation.** Faithfulness is measured by: (a) numeric accuracy (exact match or tolerance for computed values), (b) claim-level entailment (does the data support the claim?), (c) attribution correctness. Fluency metrics (BLEU, ROUGE) are uncorrelated with faithfulness and should not be used as primary gates.

### 2.4 Handling Scale

| Strategy | Accuracy | Cost | Determinism | When to Use |
|---|---|---|---|---|
| Push-down aggregation (SQL/DuckDB over full data) | Exact | Low (engine time) | Deterministic | Always for numeric facts |
| Profiling (one pass for stats) | Exact for profiled columns | Low | Deterministic | Always as first step |
| Sampling for planning (show LLM a sample to plan structure) | Approximate for planning only | Low | Non-deterministic if random | For LLM planning; never for final numbers |
| Chunking + hierarchical summarization | Lossy; can miss cross-chunk patterns | Medium | Low | Only when data cannot be aggregated (e.g., free-text logs) |
| Streaming / incremental | Exact if aggregations are incremental | Low | Deterministic | For append-only streams |

**Trade-off summary.** Push-down computation is the only strategy that is exact, cheap, and deterministic. Sampling and chunking are for planning and for unstructured text, not for numeric answers. The tool uses push-down for all numeric facts and sampling only to help the LLM plan the summary structure.

### 2.5 Normalization of Nested, Paginated, Heterogeneous Data

| Challenge | Approach | Notes |
|---|---|---|
| Nested JSON | Flatten with configurable depth; arrays become child tables or JSON columns | Preserve original paths for attribution |
| Pagination | Connector handles pagination server-side; tool sees one logical table | Cursor/offset/page-token all supported; dedup by key if needed |
| Heterogeneous schemas | Union with null-fill for missing columns; type coercion with warnings | Schema drift is reported, not silently ignored |
| Multiple related datasets | Relationship graph (FK, time alignment, shared keys) declared in request | Enables join-aware facts (e.g., "orders without matching customers") |
| Time series | Detect time column, infer grain, align series for comparison | Handles irregular intervals and gaps |

### 2.6 What the Evidence Does Not Say

- No consensus on the best way to summarize free-text log streams at scale -- hierarchical and retrieval-based methods both have open problems.
- No standard benchmark for "markdown summary quality" that covers faithfulness, usefulness, and steering together.
- Limited evidence on how users actually steer summaries in practice -- most studies use synthetic steering tasks.
- Cost/latency numbers are highly deployment-specific; the spec gives a model, not a guarantee.

### 2.7 Research Appendix Note

A full source list (title, authors/publisher, date, URL) is in Appendix D. Every claim in this section that depends on external evidence is cited there. Where evidence is weak or conflicting, the text says so.


### 2.5 Detailed Landscape: How Others Handle Scale

**Power BI / Tableau approach:** These tools handle large data by pushing aggregations to the underlying warehouse (DirectQuery) or by importing a sample/extract. Summaries are typically dashboard visuals, not markdown. Faithfulness is not a concern because numbers come from the engine, not an LLM. Our tool borrows the push-down idea but adds LLM prose.

**Observability tools (Datadog, Grafana):** Summaries are alert-driven (threshold breaches) rather than general-purpose. Numbers are engine-computed. Our tool generalizes this to arbitrary requests over arbitrary datasets.

**LLM-only approaches (ChatGPT code interpreter, Claude analysis):** These serialize data into the prompt (or generate code to analyze it). They fail on large data (context window), hallucinate numbers, and are non-deterministic. Our tool avoids all three by never putting raw data in the prompt.

**Key insight:** No existing tool combines push-down computation over full data with LLM prose generation and mechanical verification. This is the gap our tool fills.

### 2.6 Normalization Research

Nested JSON flattening is well-studied. Common approaches:

| Approach | Pros | Cons |
|---|---|---|
| Recursive flatten to dotted columns | Simple, preserves all data | Wide tables, deep nesting truncated |
| Child tables with foreign keys | Normalized, handles arrays of objects | More complex, requires join |
| JSON columns (store nested as JSON string) | Preserves structure exactly | Not queryable without JSON functions |

Our tool uses a hybrid: dotted columns for shallow nesting (depth <= 3), child tables for arrays of objects, JSON columns for deeper nesting. This balances queryability with fidelity. DuckDB handles all three natively.

### 2.7 Faithfulness Research Summary

Recent work on LLM faithfulness over structured data:

- **SelfCheckGPT (2023):** Samples multiple generations and checks consistency. Useful but expensive and not a guarantee.
- **RARR (2023):** Retrieves evidence for each claim and checks entailment. Closer to our verifier but requires a retriever.
- **Our approach:** Pre-compute all facts deterministically, then mechanically verify prose against facts. Stronger guarantee than sampling or retrieval because facts are exhaustive and verification is exact (within tolerance).

No approach achieves 100% faithfulness without grounding in pre-computed facts. Prompt engineering alone is insufficient -- evaluation consistently shows 5-15% hallucination rates for end-to-end LLM summarization over tables.

### 2.8 Cost Research

| Component | Cost per Request (est.) |
|---|---|
| Data engine (DuckDB, 1M rows, 10 facts) | Negligible (in-process, ~300ms CPU) |
| LLM planner (1 call, ~1K tokens) | ~0.001 (gpt-4o-mini) |
| LLM prose (1 call, ~3K in + 1.5K out) | ~0.002 (gpt-4o-mini) |
| Verifier + sanitizer | Negligible (pure Python, <50ms) |
| Total | ~0.003 per request |

For comparison, putting 1M rows in a prompt would cost ~250K tokens = ~0.04 (10x more) and would not fit in most context windows. Push-down is both cheaper and more faithful.

### 2.9 Research Gaps and Future Directions

The research review identified gaps that this spec does not fully address:

| Gap | Why It Matters | Future Work |
|---|---|---|
| Long-document summarization | Datasets with text-heavy columns (e.g., support tickets) need different techniques | Chunked summarization with map-reduce |
| Causal inference | Summaries that claim causation need causal methods, not just correlation | Causal discovery integration |
| Interactive summaries | Static markdown may not be enough for exploratory analysis | Interactive artifacts (sortable tables, filters) |
| Multi-modal data | Datasets with images or audio alongside tabular data | Multi-modal fact extraction |
| Real-time streaming | Data that changes during summarization | Incremental fact updates |

These gaps are acknowledged as limitations. The current design handles the common case (tabular/numeric data, static snapshot, markdown output) well. Extensions for these gaps are deferred to future phases.

### 2.10 Key Takeaways for This Design

The research directly motivates five design pillars:

1. **Compute-then-write is non-negotiable.** Every study on faithfulness converges on the same conclusion: numbers must be computed deterministically, not generated by the LLM. This is the single most important decision in the spec.

2. **Push-down beats sampling.** Sampling introduces approximation error that compounds across facts. Push-down aggregation over full data is exact, fast (columnar engine), and cheap. Sampling is only for the LLM planning sample (5 rows), never for final numbers.

3. **Verification is the safety net.** Even with compute-then-write, the LLM can misrepresent facts (wrong rounding, unsupported claims). Mechanical verification catches these errors before delivery.

4. **Security must be architectural.** Prompt injection and markdown injection are not edge cases -- they are expected when handling untrusted data. Isolation (data as JSON, not instructions) and sanitization (strip dangerous markdown) are built into the pipeline, not added as filters.

5. **Evaluation must be rigorous.** Faithfulness cannot be assumed -- it must be measured. The 115-case eval set with mechanical checks (numeric accuracy) and human checks (fluency, coverage) provides the evidence.

