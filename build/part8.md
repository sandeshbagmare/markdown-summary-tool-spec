## 8. Summary Design

### 8.1 Structure and Sections of the Markdown

Every summary follows a predictable section structure. The exact sections depend on the request and the data, but the order is stable:

| Section | When Included | Content |
|---|---|---|
| Title | Always | One-line title derived from request |
| Overview | Always | 2-3 sentences: what the data is, how many rows, what the summary covers |
| Key Findings | Always | 3-5 bullet highlights (the most important facts) |
| Trends | If time data exists and request is trend-relevant | Time-series facts with period comparisons |
| Breakdowns | If categorical data exists | Top-N, distributions, group comparisons |
| Anomalies | If anomalies detected or focus includes anomalies | Outliers with context |
| Relationships | If multiple datasets with declared relationships | Join-aware facts |
| Details / Tables | As needed | Markdown tables for precise values |
| Caveats | If warnings exist | Null rates, truncated data, unverifiable claims |
| Sources | Always (compact) | Dataset names, row counts, time range |

Length budgets per section are enforced by the prose generator (see Section 10).

### 8.2 How Content Is Planned

Content planning is a two-step process:

1. **Fact selection.** The fact planner (Section 6.3) selects up to `max_facts` facts ranked by relevance to the request. Relevance is scored by: keyword match to request, statistical interestingness (large changes, outliers), and coverage (diverse columns and fact kinds).

2. **Section assignment.** The markdown planner assigns facts to sections and orders sections for narrative flow. For simple requests this is rule-based (e.g., time facts -> Trends section). For complex requests the LLM planner does it.

### 8.3 How Facts and Findings Are Determined

Facts are not invented -- they are computed. The finding types:

| Finding Kind | How Determined | Example |
|---|---|---|
| Descriptive | Direct aggregation | "Total revenue: $4.2M" |
| Ranking | `ORDER BY` + `LIMIT` | "Top region: US-East (29.6%)" |
| Comparison | Two aggregations + delta | "Revenue up 12% vs Q2" |
| Trend | Regression slope over time buckets | "Revenue trending up (+3.2% per week)" |
| Anomaly | Z-score or IQR outlier detection | "2025-08-12: 3x normal volume (anomaly)" |
| Distribution | Histogram / quantiles | "Amounts are right-skewed; median $89, mean $142" |
| Correlation | Pearson/Spearman for numeric pairs | "Orders and support tickets correlated (r=0.72)" |
| Join-aware | SQL JOIN + aggregation | "0.14% of orders lack a matching customer" |

Thresholds for "interesting" (e.g., what counts as an anomaly) are configurable and reported in the envelope.

### 8.4 How Prose Is Produced

Prose generation turns facts into fluent markdown under strict grounding:

- The LLM receives the fact set as structured JSON, the section plan, and the request/options.
- It must cite fact ids for every numeric claim (internal citations, stripped before delivery if not needed).
- It must not compute, estimate, or round beyond the tolerance in the fact.
- It must not introduce numbers not in the fact set.
- Tables are generated from fact values, not from LLM memory.

See Section 10 for the full prompt.

### 8.5 How Length and Audience Are Controlled

| Option | Effect on Prose |
|---|---|
| `length: short` | ~200 words; Key Findings + one table; no Details section |
| `length: medium` | ~500 words; all relevant sections, concise |
| `length: long` | ~1000 words; full sections with context and caveats |
| `length: detailed` | ~2000 words; exhaustive with all tables and distributions |
| `audience: executive` | High-level, jargon-free, focus on implications |
| `audience: technical` | Precise, includes methodology notes and caveats |
| `audience: analyst` | Detailed with distributions, correlations, and raw tables |
| `language` | All prose in requested language; numbers formatted per locale |

Length is enforced by token budget in the LLM call and by truncation with artifact references if exceeded.

### 8.6 Customization and Follow-Up Edits

**Steering at creation time.** The `options` object controls focus, audience, length, language, and format. The `request` string provides additional free-form steering.

**Follow-up edits.** The caller sends `prior_summary_id` + `edit_instruction`:

| Edit Kind | What Happens | Cost |
|---|---|---|
| Length change | Re-generate prose with new budget; reuse facts | 1 LLM call |
| Language change | Re-generate prose in new language; reuse facts | 1 LLM call |
| Focus change | Re-select facts + re-generate prose | 1 LLM call + possible re-computation |
| Data change | Re-profile + re-compute affected facts + re-generate | Full pipeline for changed datasets |

Edits reuse cached profiles and fact sets where possible. The response includes a `diff_summary` noting what changed.

### 8.7 Markdown Features Used

| Feature | Allowed | Notes |
|---|---|---|
| Headings (H1-H3) | Yes | H1 for title, H2 for sections, H3 for subsections |
| Paragraphs | Yes | |
| Bullet and numbered lists | Yes | |
| Tables | Yes | For precise values; always with header row |
| Bold / italic | Yes | For emphasis |
| Code spans | Yes | For column names, values |
| Blockquotes | Yes | For caveats |
| Footnotes | Yes | For methodology notes |
| Task lists | No | Not needed for summaries |
| Raw HTML | No | Never emitted; stripped if LLM generates it |
| Images / embeds | No | v1 text only |

### 8.8 Markdown Templates by Use Case

While prose is LLM-generated, templates guide structure for common use cases. Executive summary template has Overview, Key Findings, Trends, Breakdown table, and Caveats. Technical deep-dive template adds Detailed Analysis per dimension, Methodology, and Caveats sections. Templates are not rigid -- the LLM adapts them to the request and data. They ensure consistent section ordering.

### 8.9 Handling Empty or Sparse Results

| Situation | Markdown Behavior |
|---|---|
| No facts match the request | No data matching request was found plus profile summary |
| Only 1-2 facts available | Short summary with available facts plus note on data sparsity |
| Request asks for dimension not in data | Breakdown by dimension not available; lists available dimensions |
| All values are zero/null | All values for metric are zero/null in the selected period |

The tool never fabricates a finding to fill space. If the data does not support the request, it says so clearly.

### 8.10 Internationalization Details

| Aspect | Handling |
|---|---|
| Number formatting | Locale-aware: 1,234.56 (en) vs 1 234,56 (fr) vs 1.234,56 (de) |
| Date formatting | Locale-aware: Oct 14, 2026 (en) vs 14 oct. 2026 (fr) |
| Currency | Symbol placement per locale |
| RTL languages | Markdown is logical order; rendering handles RTL |
| Verifier locale | Verifier parses numbers in the output locale |

Language is controlled by options.language (BCP 47 tag). If not specified, defaults to en.

### 8.11 Accessibility of Markdown Output

- Tables always have header rows (required for screen readers).
- Heading hierarchy is strict (H1 -> H2 -> H3, no skips).
- No information is conveyed by color or formatting alone.
- Large tables include a summary sentence before the table for context.
- Artifacts (large tables) are linked with descriptive text, not bare URLs.

### 8.12 Markdown Rendering Considerations

The generated markdown is designed to render well across common renderers:

| Renderer | Consideration |
|---|---|
| GitHub Flavored Markdown | Tables, task lists, and strikethrough are supported |
| CommonMark | Strict subset; all generated markdown is valid CommonMark |
| VS Code preview | Handles all generated constructs |
| Static site generators (Hugo, Jekyll) | Front matter not included; add separately if needed |
| PDF via pandoc | Tables and code blocks convert cleanly |

The tool does not generate HTML, LaTeX, or other non-markdown content. If the caller needs HTML, they can convert the markdown downstream.

### 8.13 Summary Length Calibration

Length options map to approximate word counts:

| Length | Target Words | Typical Sections | Typical Facts |
|---|---|---|---|
| short | 150-300 | 2-3 | 5-10 |
| medium | 400-700 | 3-5 | 10-20 |
| long | 800-1200 | 5-7 | 15-30 |
| detailed | 1200-2000 | 6-10 | 20-40 |

The LLM prompt includes the target word count. The verifier does not enforce length -- it is a soft target. If the LLM produces significantly more or fewer words than the target (over 30 percent deviation), a warning is added but the summary is still delivered.

### 8.14 Handling Sensitive Content in Summaries

If the data contains sensitive content (PII, credentials, offensive text), the summary must handle it appropriately:

- **PII:** Redacted columns never appear. If PII is detected in non-redacted columns (e.g., email pattern in a notes field), it is masked as [REDACTED] in the prose.
- **Credentials:** Patterns matching API keys, passwords, tokens are masked.
- **Offensive text:** Not filtered in v1 (assumes data is pre-moderated). A future enhancement could add a content filter.

The sanitizer handles masking after LLM generation, so even if the LLM reproduces sensitive content, it is caught before delivery.

### 8.15 Summary Structure Templates

The markdown planner uses templates based on the request type:

| Request Type | Template | Sections |
|---|---|---|
| General summary | Overview + Details + Quality | 3-4 sections |
| Trend analysis | Overview + Trends + Breakdown | 3-5 sections |
| Comparison | Overview + Group A vs B + Details | 3-4 sections |
| Anomaly report | Overview + Anomalies + Context | 3-4 sections |
| Executive brief | Key Findings + Details | 2-3 sections |

Each template defines section headings, expected fact kinds per section, and prose guidance. The LLM fills in the content; the template ensures consistent structure.

### 8.16 Handling Empty and Sparse Results

| Scenario | Handling |
|---|---|
| No rows match filter | Prose states no data found; suggests broadening filter |
| Single row | No aggregation; prose describes the single record |
| All nulls in a column | Column omitted from summary; warning added |
| Sparse data (many nulls) | Null fraction reported; facts computed on non-null subset |

Empty results still produce a valid markdown document (never an error), with a clear message about what was found (or not found).

### 8.17 Internationalization Considerations

- **Language:** The `options.language` field controls output language. The LLM prompt includes the target language; the verifier handles locale-specific number formats.
- **Number formatting:** Locale-aware (e.g., 1.234,56 in de-DE vs 1,234.56 in en-US). The verifier parses both.
- **Date formatting:** ISO 8601 in facts; localized in prose per the target language.
- **Currency:** Preserved from data; not converted.

v1 supports any language the LLM supports, but evaluation is primarily in English. Non-English output quality should be validated per language before production use.

