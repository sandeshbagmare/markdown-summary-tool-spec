## 3. Decision Log and Rationale

Every major decision, the alternatives considered, and why the chosen option won. Revisit this log when requirements change -- it records what would change our minds.

### 3.1 Compute-Then-Write vs End-to-End LLM

| Option | Description | Verdict |
|---|---|---|
| A. End-to-end LLM over serialized data | Put (sample of) data in prompt, ask LLM to summarize | Rejected -- hallucinates numbers, fails on large data, expensive |
| B. LLM writes code that computes, then summarizes | LLM generates Python/SQL, executes, then narrates | Rejected as primary -- non-deterministic code gen, failure-prone, slower |
| **C. Compute-then-write (chosen)** | Deterministic engine computes facts; LLM verbalises under verification | **Chosen** -- faithful, scalable, testable |

**Why C wins.** Only C gives a mechanical faithfulness guarantee: numbers exist before prose and are checked after. A and B both let the LLM invent numbers. C also solves scale (engine handles full data) and cost (LLM sees facts, not rows).

**What would change our minds.** If LLMs become reliably faithful on arithmetic over large tables without grounding, A could be reconsidered. No current evidence supports this.

### 3.2 Who Is the Primary Consumer?

| Option | Verdict |
|---|---|
| Markdown primarily for the top model to re-summarize | Rejected -- adds latency, cost, and a second lossy step |
| **Markdown primarily for the user (chosen)** | **Chosen** -- self-contained, directly renderable; envelope serves the top model |

**Reasoning.** The user is the ultimate reader. Making markdown user-ready avoids a second summarization that can introduce errors. The top model gets structured facts in the envelope, which is more useful than re-parsing markdown.

### 3.3 One LLM Call vs Two

| Option | Verdict |
|---|---|
| One call: plan + prose together | Cheaper but couples planning and writing; harder to verify |
| **Two calls: (1) plan structure, (2) write prose from facts (chosen, with single-call fast path)** | **Chosen** -- cleaner separation; fast path collapses to one call for simple requests |

**Design.** Simple requests (single dataset, short summary) use one call. Complex requests (multi-dataset, long, steered) use two: first call plans the section structure and fact requirements; second call writes prose from the computed fact set. The planner call is small and cache-friendly.

### 3.4 Fact Representation: Free Text vs Structured

| Option | Verdict |
|---|---|
| Facts as free-text sentences | Rejected -- hard to verify |
| **Facts as structured records with value, provenance, and tolerance (chosen)** | **Chosen** -- mechanically verifiable |

Each fact is a JSON record: `{"id": "f12", "kind": "aggregate", "metric": "revenue", "value": 4200000, "unit": "USD", "slice": {"quarter": "2025-Q3"}, "provenance": {"query": "SELECT SUM(revenue) ...", "rows": 1400000}, "tolerance": 0.01}`. The verifier extracts numbers from prose and matches them to fact records.

### 3.5 Engine Choice: DuckDB vs Alternatives

| Option | Verdict |
|---|---|
| **DuckDB (chosen)** | **Chosen** -- in-process, fast on analytical queries, handles JSON/CSV/Parquet, no server needed |
| pandas | Fallback for small data; slower on large aggregations |
| Spark / BigQuery | Overkill for a tool; external dependency |

DuckDB is the primary engine; pandas is the fallback for tiny datasets or when DuckDB is unavailable. Both are hidden behind an engine interface.

### 3.6 Markdown Flavor

| Option | Verdict |
|---|---|
| **CommonMark + allow-listed extensions (tables, task lists, footnotes) (chosen)** | **Chosen** -- widely rendered, safe, sufficient |
| Full GitHub Flavored Markdown with raw HTML | Rejected -- raw HTML is an injection vector |

Raw HTML is never emitted. All markdown is sanitized.

### 3.7 Handling Scale: Push-Down vs Sampling

| Option | Verdict |
|---|---|
| Sample data, summarize sample | Rejected for numeric facts -- sampling error is unacceptable for exact claims |
| **Push-down aggregation over full data (chosen)** | **Chosen** -- exact, cheap, deterministic |
| Hierarchical chunk-and-merge | Only for unstructured text (e.g., log messages) where aggregation is not applicable |

Sampling is used only to show the LLM a few example rows for planning, never for final numbers.

### 3.8 Security Posture

| Decision | Rationale |
|---|---|
| Data is never treated as instructions | Prevents prompt injection via data |
| Markdown output is sanitized (no raw HTML, no JS, no data URIs) | Prevents markdown injection |
| Sensitive data is redacted or gated by policy | Prevents exfiltration |
| Connectors use server-side credentials, never client-supplied secrets | Prevents credential leakage |

### 3.9 Consistency Mechanism

Deterministic facts + deterministic section structure + constrained prose. The same data + same request yields the same facts and same headings; phrasing may vary within a narrow band. A plan cache (keyed by dataset fingerprint + request hash) further stabilizes output.

### 3.10 Cost Reasoning in One Paragraph

One small-model call over ~2-4K input tokens (profiles + facts + request) and ~1-2K output tokens (markdown) costs cents and completes in 1-3 seconds. The data engine runs in milliseconds to low seconds for millions of rows (DuckDB). The verifier is pure Python and adds negligible cost. Total per-request cost is dominated by the LLM call, which is minimized by cache-friendly prompts and by never sending raw data as tokens.


### 3.11 Caching Strategy

| Option | Verdict |
|---|---|
| No cache -- recompute every time | Rejected -- wasteful for repeated requests over same data |
| Cache profiles + fact sets by dataset fingerprint + request hash | **Chosen** -- fast path for identical or near-identical requests |
| Cache full markdown | Rejected -- markdown varies with steering even over same data |

Cache keys combine a fingerprint of the normalized data (row count + column hashes + sample checksum) with a hash of the request and options. TTL is 1 hour for profiles, 30 minutes for fact sets. Invalidation is explicit on data change notification; otherwise TTL expiry. Cache hit rate is expected to be 30-40% for interactive use (user iterates on steering).

### 3.12 Streaming vs Batch Delivery

| Option | Verdict |
|---|---|
| Always batch -- return full markdown at once | **Chosen for v1** -- simpler, verifiable as a whole |
| Stream markdown chunks as verified | Deferred to v1.1 -- requires incremental verification |

Streaming is desirable for long summaries (perceived latency) but complicates verification (each chunk must be verified before streaming). v1 returns the full markdown after verification. v1.1 will add streaming with per-chunk verification and a final envelope.

### 3.13 Markdown Sanitization: Allow-List vs Block-List

| Option | Verdict |
|---|---|
| Block-list known bad patterns | Rejected -- incomplete, bypass-prone |
| **Allow-list safe markdown constructs (chosen)** | **Chosen** -- only CommonMark + tables/footnotes pass; everything else stripped |

The sanitizer parses markdown into an AST and re-emits only allow-listed node types. Raw HTML nodes are dropped. Link destinations are checked against an allow-list of schemes (`https`, `mailto` only). This is more robust than regex-based stripping.

### 3.14 Error Handling: Fail-Closed vs Fail-Open

| Option | Verdict |
|---|---|
| Fail-open -- return unverified markdown with a warning | Rejected -- user may miss the warning and trust wrong numbers |
| **Fail-closed with safe fallback (chosen)** | **Chosen** -- unverifiable claims replaced with safe placeholder + fact table |

When verification fails after repair attempts, the tool does not return the unverified prose. Instead, it replaces each unverifiable claim with `[value not verified -- see fact table]` and includes the correct value in a fact table. The envelope carries `W_UNVERIFIED_CLAIM`. This ensures no wrong number is ever presented as verified.

### 3.15 Evaluation Philosophy

| Option | Verdict |
|---|---|
| Evaluate fluency only (BLEU, ROUGE) | Rejected -- fluency without faithfulness is harmful |
| **Evaluate faithfulness first, fluency second (chosen)** | **Chosen** -- numeric accuracy is the hard gate; fluency is secondary |

The evaluation harness (Section 15) measures numeric accuracy (100% required), claim accuracy, and fluency (human rating). A summary that is fluent but has a wrong number fails. A summary that is accurate but slightly awkward passes. This ordering reflects the risk profile: a wrong number in a business summary can cause a bad decision; awkward phrasing merely causes mild annoyance.

### 3.16 Decision: Output Format -- Markdown Only vs Multi-Format

**Options considered:**

| Option | Pros | Cons |
|---|---|---|
| Markdown only | Simple, universal, renders everywhere | No native chart support |
| Markdown + HTML | Richer output | HTML sanitization burden |
| Markdown + JSON | Machine-readable + human-readable | Two outputs to maintain |
| Multi-format (markdown, HTML, PDF) | Maximum flexibility | Complexity, testing burden |

**Decision:** Markdown only for v1, with JSON envelope for machine consumers. The markdown is the primary output; the envelope carries structured data for the top model. HTML/PDF conversion is downstream (caller converts markdown if needed). This keeps the tool focused and avoids format-specific bugs.

### 3.17 Decision: Fact Granularity -- Coarse vs Fine

**Options considered:**

| Option | Pros | Cons |
|---|---|---|
| Coarse facts (one per section) | Fewer facts, simpler | Misses detail; prose may need numbers not in facts |
| Fine facts (one per number) | Every number verified | Many facts; higher cost |
| Hybrid (facts for key numbers, prose for context) | Balanced | Need to decide what is key |

**Decision:** Fine-grained facts -- every number that appears in prose must have a corresponding fact. The fact planner generates facts for all material findings; the verifier checks every number. This is stricter but provides the strongest faithfulness guarantee. The cost is manageable because facts are computed by the engine (cheap), not the LLM.

### 3.18 Decision: LLM Provider Abstraction -- Single vs Multi

**Options considered:**

| Option | Pros | Cons |
|---|---|---|
| Single provider (e.g., only OpenAI) | Simple, one API to handle | Vendor lock-in; outage = total failure |
| Multi-provider with abstraction | Resilience, cost optimization | More code, testing across providers |
| Provider-agnostic (bring your own key) | Maximum flexibility | Caller manages keys and quotas |

**Decision:** Multi-provider with abstraction. The tool defines a common LLM interface (generate, stream, count_tokens) and adapters for each provider (OpenAI, Anthropic, Google). The caller configures the primary provider and optional fallback. This provides resilience without burdening the caller.

### 3.19 Decision: Caching Strategy -- None vs Aggressive

**Options considered:**

| Option | Pros | Cons |
|---|---|---|
| No caching | Simple, always fresh | Repeated work for follow-up edits |
| Profile caching only | Saves profiling time | Facts still recomputed |
| Full caching (profile + facts + plans) | Maximum savings for edits | Cache invalidation complexity |
| External cache (Redis) | Shared across instances | Infrastructure dependency |

**Decision:** Full caching with in-memory LRU (1-hour TTL) for v1, plus optional Redis for multi-instance deployments. Cache keys include data hash + request hash so stale data is never served. For follow-up edits, the prior summary state is loaded directly (no cache lookup needed).

### 3.20 Decision: Evaluation -- Automated Only vs Human-in-the-Loop

**Options considered:**

| Option | Pros | Cons |
|---|---|---|
| Automated only (mechanical checks) | Fast, cheap, deterministic | Misses fluency and coverage |
| Human only | Catches everything | Slow, expensive, not scalable |
| Hybrid (automated + human sample) | Best of both | More process |

**Decision:** Hybrid. Automated checks (numeric accuracy, claim accuracy) run on every eval case in CI. Human evaluation (fluency, coverage) runs on a sample of 30 cases per release, rated by 2 annotators. Disagreements are adjudicated. This balances rigor with practicality.

