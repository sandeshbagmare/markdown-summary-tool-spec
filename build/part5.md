## 5. Tool Input Specification

### 5.1 Contract Overview

The top model calls one function: `create_markdown_summary`. The function accepts a request object with datasets, a natural-language instruction, and steering options. Data is supplied by reference, not by value -- the top model never pastes large data.

### 5.2 Function Definition Exposed to the Top Model

```json
{
  "name": "create_markdown_summary",
  "description": "Summarize one or more datasets as a verified markdown document. Data is supplied by reference (data_ref), not pasted. Numbers in the summary are computed over the full data and mechanically verified.",
  "parameters": {
    "type": "object",
    "required": ["datasets", "request"],
    "properties": {
      "datasets": {
        "type": "array",
        "minItems": 1,
        "maxItems": 8,
        "items": { "$ref": "#/$defs/Dataset" }
      },
      "request": { "type": "string", "minLength": 1, "maxLength": 2000 },
      "relationships": {
        "type": "array",
        "items": { "$ref": "#/$defs/Relationship" }
      },
      "options": { "$ref": "#/$defs/Options" },
      "prior_summary_id": { "type": "string", "description": "For edit mode: ID of prior summary to revise" },
      "edit_instruction": { "type": "string", "maxLength": 2000 }
    }
  }
}
```

### 5.3 Top-Level Request Object

| Field | Type | Required | Description |
|---|---|---|---|
| `datasets` | `Dataset[]` | Yes | One or more datasets to summarize (1-8) |
| `request` | `string` | Yes | Natural-language instruction (e.g., "Summarize revenue trends by region, focusing on anomalies") |
| `relationships` | `Relationship[]` | No | How datasets relate (FK, time alignment, shared keys) |
| `options` | `Options` | No | Steering: focus, audience, length, language, format |
| `prior_summary_id` | `string` | No | For `edit` mode: references a prior summary |
| `edit_instruction` | `string` | No | For `edit` mode: what to change |

### 5.4 Dataset Object

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | `string` | Yes | Unique within request (e.g., `"orders"`, `"events"`) |
| `data_ref` | `DataRef` | Yes | Pointer to the data (see below) |
| `profile` | `Profile` | No | Pre-computed profile (if omitted, tool computes it) |
| `sample_rows` | `object[]` | No | Up to 5 example rows for LLM planning (never used for final numbers) |
| `name` | `string` | No | Human-readable name for headings |
| `description` | `string` | No | What the dataset contains |

### 5.5 Data Reference (`data_ref`) Types

| Type | Fields | Description |
|---|---|---|
| `table` | `connection`, `query` or `table` | SQL table or query via server-side connection |
| `file` | `path`, `format` (csv/parquet/json) | File on allow-listed storage |
| `handle` | `handle_id` | Opaque handle from a prior step (e.g., paginated API result) |
| `url` | `url`, `pagination` | Allow-listed URL with pagination config |
| `inline` | `data` (array, max 100 rows) | Small inline payload for tiny datasets |

**Size and limit rules:**

- Inline data: max 100 rows, max 64 KB.
- Referenced data: no hard row limit; engine handles scale via push-down.
- Total datasets per request: max 8.
- Total request payload (excluding referenced data): max 256 KB.
- Pagination: connector handles it server-side; tool sees one logical table. Supports `cursor`, `offset`, and `page_token` strategies with dedup by key.

### 5.6 Profile Object

The profile is column-level metadata computed over the full data. If the caller omits it, the tool computes it.

| Field | Type | Description |
|---|---|---|
| `row_count` | `integer` | Total rows |
| `columns` | `ColumnProfile[]` | Per-column stats |
| `time_grain` | `string` | Inferred time grain if a time column exists |
| `computed_at` | `string` (ISO 8601) | When the profile was computed |

**ColumnProfile:**

| Field | Type | Description |
|---|---|---|
| `name` | `string` | Column name |
| `type` | `string` | Inferred type: `string`, `number`, `integer`, `boolean`, `datetime`, `json` |
| `count` | `integer` | Non-null count |
| `null_count` | `integer` | Null count |
| `distinct_count` | `integer` | Approximate distinct values |
| `min` / `max` | `any` | Min/max for orderable types |
| `mean` / `median` / `std` | `number` | For numeric columns |
| `top_values` | `{value, count}[]` | Top 5 frequent values |
| `sample_values` | `any[]` | Up to 3 sample values |

### 5.7 Sample Rows

Up to 5 rows, for LLM planning only. These help the LLM understand the data shape and plan the summary structure. They are never used for final numbers.

### 5.8 Relationships

| Field | Type | Description |
|---|---|---|
| `from` | `string` | Source dataset id |
| `to` | `string` | Target dataset id |
| `kind` | `string` | `foreign_key`, `time_alignment`, `shared_key`, `union` |
| `on` | `object` | Join condition (e.g., `{"orders.customer_id": "customers.id"}`) |
| `cardinality` | `string` | `one_to_one`, `one_to_many`, `many_to_many` |

Relationships enable join-aware facts (e.g., "12% of orders have no matching customer").

### 5.9 Options Object

| Field | Type | Default | Description |
|---|---|---|---|
| `focus` | `string` | Auto | What to emphasize (e.g., "anomalies", "trends", "top contributors") |
| `audience` | `string` | `general` | `general`, `executive`, `technical`, `analyst` -- controls detail and jargon |
| `length` | `string` | `medium` | `short` (~200 words), `medium` (~500 words), `long` (~1000 words), `detailed` (~2000 words) |
| `language` | `string` | `en` | BCP 47 code (e.g., `en`, `fr`, `ja`) |
| `format` | `string` | `sections` | `sections`, `bullets`, `narrative`, `table_heavy` |
| `include` | `string[]` | Auto | Explicit sections to include (e.g., `["trends", "anomalies", "top_n"]`) |
| `exclude` | `string[]` | -- | Sections to omit |
| `max_facts` | `integer` | 20 | Max facts to surface (tool may return fewer) |
| `redact` | `string[]` | -- | Columns to redact from output |

### 5.10 Inputs for Modify and Restyle

For `edit` mode, the caller provides `prior_summary_id` and `edit_instruction`:

- `edit_instruction` examples: "Make it shorter", "Focus on errors instead of revenue", "Translate to French", "Add a section on regional breakdown".
- The tool reuses cached profiles and fact sets; only the prose and optionally the fact selection are recomputed.
- Length, language, and format changes do not require recomputing facts.

### 5.11 Input Validation and Normalization

| Check | Error Code | Behavior |
|---|---|---|
| Missing required fields | `E_INPUT_INVALID` | Reject with details |
| Too many datasets (>8) | `E_INPUT_INVALID` | Reject |
| Inline data too large | `E_INPUT_INVALID` | Reject; suggest using `file` or `table` ref |
| Unknown `data_ref` type | `E_INPUT_INVALID` | Reject |
| Unresolvable `data_ref` | `E_DATA_NOT_FOUND` | Error with resolution hint |
| Invalid `options` values | `E_INPUT_INVALID` | Reject with allowed values |
| `prior_summary_id` not found | `E_NOT_FOUND` | Error |

Normalization: trim strings, coerce `request` whitespace, default missing `options` fields, sort `datasets` by `id` for cache key stability.

### 5.12 Complete Example Input

```json
{
  "datasets": [
    {
      "id": "orders",
      "name": "Orders",
      "description": "E-commerce orders from 2025",
      "data_ref": { "type": "table", "connection": "warehouse", "table": "prod.orders" },
      "profile": {
        "row_count": 1420000,
        "columns": [
          {"name": "order_id", "type": "string", "count": 1420000, "distinct_count": 1420000},
          {"name": "customer_id", "type": "string", "count": 1418000, "null_count": 2000, "distinct_count": 89000},
          {"name": "amount", "type": "number", "count": 1420000, "min": 1.5, "max": 9999.0, "mean": 142.5, "median": 89.0},
          {"name": "region", "type": "string", "count": 1420000, "distinct_count": 6, "top_values": [{"value": "US-East", "count": 420000}]},
          {"name": "ordered_at", "type": "datetime", "count": 1420000, "min": "2025-01-01", "max": "2025-12-31"}
        ],
        "time_grain": "day"
      },
      "sample_rows": [
        {"order_id": "O-1001", "customer_id": "C-42", "amount": 129.99, "region": "US-East", "ordered_at": "2025-03-15T10:30:00Z"}
      ]
    },
    {
      "id": "customers",
      "name": "Customers",
      "data_ref": { "type": "table", "connection": "warehouse", "table": "prod.customers" }
    }
  ],
  "relationships": [
    {"from": "orders", "to": "customers", "kind": "foreign_key", "on": {"orders.customer_id": "customers.id"}, "cardinality": "many_to_one"}
  ],
  "request": "Summarize order trends by region for Q3 2025, highlighting anomalies and top contributors. Keep it executive-friendly.",
  "options": {
    "audience": "executive",
    "length": "medium",
    "focus": "trends and anomalies",
    "max_facts": 15
  }
}
```

### 5.13 Guidance for the Top Model (The Thin Skill)

The top model receives a short instruction block (not a full skill file) that explains:

1. When to call the tool (user wants a data summary, not a chart).
2. How to construct `data_ref` (use handles/tables, never paste large data).
3. How to write `request` (be specific about focus, time range, and audience).
4. How to handle the response (render markdown directly; use envelope metadata for follow-ups).
5. That `sample_rows` and `profile` are optional -- the tool computes them if missing.

This block is ~300 tokens and is included in the top model''s system prompt or tool description. It is not a separate agent skill.


### 5.6 Input Validation Rules

| Rule | Check | Error |
|---|---|---|
| Dataset count | 1 <= len(datasets) <= 10 | E_INPUT_INVALID |
| Dataset id format | ^[a-z][a-z0-9_]{0,63}$ | E_INPUT_INVALID |
| DataRef kind | One of: file, table, handle, url, inline | E_INPUT_INVALID |
| Request length | 1 <= len(request) <= 2000 chars | E_INPUT_INVALID |
| Request not empty | request.strip() != '' | E_INPUT_INVALID |
| Relationship validity | Both datasets exist, key columns exist | E_INPUT_INVALID |
| Options values | Enums for focus, audience, length, language | E_INPUT_INVALID |
| Total data size | Sum of dataset sizes <= max_total_rows | W_TRUNCATED or E_INPUT_INVALID |

Validation is fail-fast: the first error is returned immediately with a descriptive message. No partial processing occurs on invalid input.

### 5.7 DataRef Kinds in Detail

**file:** References a file already uploaded to the file store. Identified by file_id from a prior upload. Supported formats: CSV, JSON (array or NDJSON), Parquet, Excel (.xlsx).

**table:** References a table or query in a connected warehouse. The connector executes the query and returns rows. Queries are parameterized; no string interpolation from data values.

**handle:** References a dataset by handle (opaque id) from a prior tool call or session. Handles are short-lived (TTL 1 hour) and scoped to the session.

**url:** References data at an allow-listed URL. The tool fetches the URL server-side with a 30s timeout. Only https URLs on the allow-list are permitted.

**inline:** Data is provided directly in the request as JSON or CSV. Limited to 100KB inline; larger data should use file or table refs.

### 5.8 Relationship Declarations

Relationships declare how datasets relate. Only declared relationships are used for join-aware facts. The tool never guesses joins. Cardinality is used to validate join results (e.g., many-to-one should not produce fan-out beyond expected).

```json
{
  "from": {"dataset": "orders", "column": "customer_id"},
  "to": {"dataset": "customers", "column": "id"},
  "cardinality": "many-to-one"
}
```

### 5.9 Options Reference

| Option | Type | Default | Description |
|---|---|---|---|
| focus | string | auto | What to focus on (e.g., trends, anomalies, breakdowns) |
| audience | enum | executive | Target audience: executive, technical, analyst |
| length | enum | medium | Length: short, medium, long, detailed |
| language | string (BCP 47) | en | Output language |
| format | enum | markdown | Output format (currently only markdown) |
| redact | string[] | [] | Column names to redact from output |
| max_facts | integer | 20 | Maximum facts to compute |
| include_provenance | boolean | false | Include provenance footnotes in markdown |

All options are optional. Sensible defaults ensure a useful summary even with minimal steering.
