# Markdown Summary Tool -- Technical Specification v1.0

**Deterministic computation + LLM prose over large, untrusted, multi-dataset inputs**

| Field | Value |
|---|---|
| Version | 1.0 -- Draft for engineering review |
| Date | 2026-10-14 |
| Tool name | `create_markdown_summary` |
| Output type | `text/markdown` -- one verified markdown document + JSON metadata envelope |
| Computation | Deterministic engine (DuckDB / pandas) over full data; LLM never sees raw rows beyond profile + samples |
| Planner | One small/cheap LLM call per request (planner); optional second call for prose; model chosen by config |
| Spec length | ~80 pages |

---

## Executive Summary

**Primary recommendation.** Build the Markdown Summary Tool as a **compute-then-write** system: a deterministic data engine computes every number, comparison, and ranking over the full datasets, and a constrained LLM call turns those pre-computed facts into fluent markdown. The LLM never invents numbers; it only verbalises facts that have already been computed and that are re-checked after generation. This is the same division of labour that the Visualization Tool uses (LLM plans, code renders), adapted for text: **engine computes, LLM narrates, verifier enforces**.

**Why this shape.** The worst outcome is a fluent but wrong summary. Hallucinated numbers, misranked items, and invented trends are the dominant failure mode of end-to-end LLM summarization over structured data. Grounding every numeric claim in a prior computation and then mechanically verifying the prose against those computations is the only approach with a defensible faithfulness story at scale. It also solves the context-window problem (the LLM sees profiles and aggregates, not millions of rows), the cost problem (one small-model call over a few thousand tokens, not the full data), and the determinism problem (the same data + same request ? same facts, even if phrasing varies slightly).

**Who reads the markdown.** The primary consumer is the **user**, with the top model as a secondary consumer that may re-present or act on the summary. This decision drives the design: the markdown is self-contained, human-readable, and safe to render directly; the JSON envelope carries machine-readable facts, warnings, and artifact references for the top model. An alternative framing (markdown primarily for the top model to re-summarize) was rejected because it adds latency, cost, and a second lossy summarization step with no user-visible benefit.

**What the tool does.** The caller (an AI agent) supplies data references (not raw data), a natural-language request, and steering options (focus, audience, length, language, format). The tool normalizes and profiles the data, computes a fact set (descriptives, comparisons, trends, anomalies, join-aware facts for related datasets), plans the markdown structure, generates prose under strict grounding constraints, verifies every number, and returns markdown plus metadata. Follow-up edits reuse prior state without recomputing everything.

**What it does not do.** It is not a general document generator, not a BI dashboard, not a streaming engine, and not a data-cleaning pipeline. It reads data; it does not repair broken data beyond safe coercion. It summarizes what is in the data; it does not invent external knowledge.

**Key risks.** Faithfulness at scale depends on the verifier, not on prompt engineering. Evaluation must measure numeric accuracy, not just fluency. Prompt injection via data is a real threat and is handled by never treating data as instructions and by sanitizing markdown output.

---

## Table of Contents

1. Introduction and Scope -- p7
2. Research Findings -- p11
3. Decision Log and Rationale -- p18
4. System Architecture -- p22
5. Tool Input Specification -- p27
6. Processing Pipeline in Detail -- p35
7. Data Handling -- p42
8. Summary Design -- p48
9. Faithfulness and Verification -- p55
10. Model Call Design -- p61
11. Tool Output Specification -- p68
12. Consistency and Quality Controls -- p72
13. Security and Privacy -- p75
14. Errors, Warnings and Partial Results -- p79
15. Testing and Evaluation -- p83
16. Operations, Configuration and Observability -- p88
17. Implementation Blueprint -- p92
18. Worked Examples End to End -- p98
19. Comparison with Existing Approaches -- p108
20. Roadmap, Risks, Open Questions and Acceptance -- p111
21. Appendices -- p115

---

## 1. Introduction and Scope

### 1.1 Purpose

This document is the complete technical specification for a Markdown Summary Tool: a backend capability that an AI agent (the "top model") calls whenever it needs to turn large, machine-generated data into a useful markdown summary. The tool accepts references to one or more datasets, a natural-language request, and steering options, and returns one verified markdown document plus a JSON metadata envelope.

The core idea is a strict division of labour. A deterministic data engine computes every fact over the full data. A small, cheap language model then turns those facts into fluent markdown under tight grounding constraints. A mechanical verifier checks that every number in the prose matches a computed fact. The model never computes, never sees the full data, and never invents numbers.

### 1.2 Problem Statement

Asking a large model to summarize raw data end-to-end has predictable problems:

- **Wrong numbers.** LLMs hallucinate numbers, misrank items, and invent trends when asked to reason over tables. Fluency masks error. For data summaries, this is the worst failure mode.
- **Context overflow.** Real inputs (API responses, query results, log streams, time series, paginated results, multiple related datasets) can be orders of magnitude larger than any context window. Sending raw data to the model does not scale.
- **Cost and latency.** Sending large data as tokens is slow and expensive. Output tokens are the bottleneck. A tool called often must be cheap and fast.
- **Inconsistency.** Every run reinvents structure, tone, and emphasis, so "the same kind of request" produces different summaries.
- **Untrusted data.** Data may contain prompt-injection attempts, malicious markup, or sensitive information. Treating data as instructions is unsafe.
- **Steering and follow-ups.** Users want to control focus, audience, length, language, and format, and to ask follow-up edits without starting over.

The tool exists to solve these problems with a defensible, testable design.

### 1.3 Goals

- Produce markdown summaries whose every numeric claim is grounded in a prior deterministic computation and mechanically verified.
- Handle inputs far larger than any context window without sampling away correctness.
- Return useful summaries for heterogeneous, nested, paginated, and multi-dataset inputs.
- Support steering (focus, audience, length, language, format) and follow-up edits.
- Be cheap and fast enough to call often (one small-model call per request in the common case).
- Be safe over untrusted data (no prompt injection, no markdown injection, no data exfiltration).
- Produce consistent structure for the same kind of request.
- Be callable by systems other than one specific top model (stable contract, no hidden coupling).

### 1.4 Non-Goals

- Not a general document or report generator beyond data summarization.
- Not a BI or dashboard product (no interactive charts; that is the sibling Visualization Tool).
- Not a data-cleaning or ETL tool. The tool reads data; it does not repair broken data beyond safe type coercion and null handling.
- Not a streaming or real-time engine. Output is a snapshot of the data at request time.
- Not a replacement for bespoke, hand-written analysis. The tool summarizes what is in the data; it does not invent external knowledge or domain expertise.
- No server-side image rendering in v1.

### 1.5 Terminology

| Term | Meaning |
|---|---|
| Top model | The AI agent that calls the tool and talks to the user. |
| Data reference (`data_ref`) | A pointer to a dataset (table, file, handle, URL, inline) resolved server-side. Raw data is never sent by the top model. |
| Profile | Column-level statistics and metadata computed over the full data (types, counts, nulls, min/max, cardinality, time grain, etc.). |
| Fact | A single computed finding with a value, provenance, and optional attribution (e.g., "revenue in 2025-Q3 was $4.2M, +12% QoQ, computed over 1.4M rows"). |
| Fact set | The complete set of facts computed for a request before any prose is generated. |
| Verifier | The mechanical checker that every number in the prose matches a fact in the fact set. |
| Steering | User-controlled options: focus, audience, length, language, format, and follow-up edits. |
| Artifact | A stored object (e.g., full fact table, CSV export) referenced by the markdown rather than inlined. |

### 1.6 Design Principles

1. **Compute, then write.** No number appears in prose unless it was computed first.
2. **Verify, do not trust.** Every numeric claim is checked mechanically; failures are repaired or surfaced, never silently passed.
3. **Full-data correctness.** Aggregations run over the full data, not over a sample shown to the LLM. Sampling is for planning, not for answers.
4. **Least privilege for the LLM.** The LLM sees profiles, samples, and facts -- never raw large data, never credentials, never instructions from data.
5. **Deterministic facts, varied prose.** The same data + same request yields the same facts; phrasing may vary within a narrow band.
6. **Safe by construction.** Data is never treated as instructions; markdown output is sanitized; sensitive data is redacted or gated.
7. **Cheap and fast by default.** One small-model call, cache-friendly prompts, push-down computation.
8. **Stable contract.** Versioned schemas, additive changes, no coupling to one top model.

### 1.7 Assumptions

- Datasets are tabular or can be normalized to tabular form (including nested JSON via flattening). Truly unstructured blobs (images, PDFs) are out of scope for v1.
- Data is accessible server-side via connectors (file, table/query, handle, allow-listed URL, inline small payload). The top model does not paste large data.
- The tool runs in a trusted backend with access to a SQL-capable engine (DuckDB or equivalent) for push-down computation.
- A small/cheap LLM with structured-output support is available. Model choice is configuration, not hard-coded.
- Markdown is rendered in a context that supports CommonMark plus a small allow-listed extension set (tables, task lists, footnotes); raw HTML is not required.
- Users accept that "consistent" means same facts and same section structure, not byte-identical prose.

### 1.8 Stakeholders and Audience for This Specification

| Stakeholder | Interest | How This Spec Serves Them |
|---|---|---|
| Engineering team | Build the tool | Blueprint (Ch 17), pipeline detail (Ch 6), error handling (Ch 14) |
| Product / design | Define behaviour and UX | Input/output specs (Ch 5, 11), summary design (Ch 8), worked examples (Ch 18) |
| Security review | Assess risk | Security chapter (Ch 13), data handling (Ch 7), threat model |
| QA / evaluation | Test the tool | Testing chapter (Ch 15), eval metrics, acceptance criteria (Ch 20.4) |
| Top-model team | Integrate the tool | Tool contract (Ch 5, 11), consistency controls (Ch 12), model call design (Ch 10) |
| Leadership | Approve and fund | Executive summary, decision log (Ch 3), roadmap and risks (Ch 20) |

This spec is written for all of these audiences. Each chapter states its purpose up front so readers can navigate to what matters for their role.

### 1.9 How to Read This Document

- **For a quick overview:** Read the Executive Summary and Chapter 3 (Decision Log). Together they convey the what and why in under 10 pages.
- **For implementation:** Read Chapters 4-7 (Architecture, Input, Pipeline, Data Handling) and Chapter 17 (Blueprint) in order. They form a sequential build guide.
- **For integration:** Read Chapters 5 (Input), 11 (Output), and 12 (Consistency). These define the contract between the tool and its callers.
- **For review:** Read Chapters 9 (Faithfulness), 13 (Security), and 15 (Testing). These contain the claims that need the most scrutiny.
- **For context:** Read Chapter 2 (Research) and Chapter 19 (Comparison) to understand why this design was chosen over alternatives.

Cross-references are included throughout. Terms defined in the Glossary (Appendix F) are used consistently.

### 1.10 Conventions Used in This Document

| Convention | Meaning |
|---|---|
| `monospace` | Code, identifiers, file paths, API fields |
| **Bold** | Key terms on first use, emphasis |
| *Italic* | Secondary emphasis, glossary terms |
| [REQ-XXX] | Numbered requirement (future; not yet assigned) |
| MUST / SHOULD / MAY | RFC 2119 keywords for normative statements |
| -- | Em dash replacement (ASCII-safe) |

All JSON examples are valid JSON (trailing commas removed, quotes correct). All SQL examples use DuckDB dialect. All markdown examples are valid CommonMark.

