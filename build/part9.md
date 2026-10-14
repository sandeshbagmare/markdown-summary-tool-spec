## 9. Faithfulness and Verification

### 9.1 How Every Number and Claim Is Checked

Verification is mechanical -- no LLM is involved. It runs after prose generation and before sanitization.

**Step 1: Extract numbers from prose.** A number parser extracts all numeric tokens from the markdown, handling:

- Integers, decimals, percentages, currency (`$4.2M`, `12%`, `1,420,000`)
- Formatted numbers with locale-aware separators
- Numbers in tables (cell values)
- Numbers in prose ("revenue was $4.2 million")

**Step 2: Match each number to a fact.** Each extracted number is matched against the fact set:

| Match Type | Rule |
|---|---|
| Exact match | Number equals fact value within tolerance |
| Rounded match | Number equals fact value rounded to displayed precision |
| Derived match | Number equals arithmetic over facts (e.g., percentage = part/total) -- allowed only if derivation is declared |
| Unmatched | No fact supports the number -- flagged as failure |

**Step 3: Check non-numeric claims.** Rankings, comparisons, and trends are checked:

| Claim Kind | Check |
|---|---|
| Ranking ("top region is US-East") | Fact ordering must agree |
| Comparison ("up 12% vs Q2") | Both periods'' values and delta must match facts |
| Trend ("trending up") | Slope sign must match fact |
| Existence ("no anomalies found") | Anomaly facts must be empty |

**Step 4: Verdict.** If all numbers and claims match, the markdown passes. Otherwise, the verifier returns a list of failures with locations.

### 9.2 Tolerance and Rounding

| Situation | Tolerance | Example |
|---|---|---|
| Exact values | 0 (exact string match after normalization) | `1420000` must appear as `1,420,000` or `1420000` or `1.42M` (with declared rounding) |
| Rounded display | Fact tolerance field (default 0.5% or 1 unit in last displayed digit) | Fact `4200000` may appear as `$4.2M` |
| Percentages | 0.1 percentage point | `29.6%` matches `29.58%` |
| Currency | Smallest displayed unit | `$4.2M` matches `$4,200,000` |

Tolerances are per-fact and declared in the fact record. The verifier uses them; the LLM is instructed to respect them.

### 9.3 What Happens When a Check Fails

```
Verification failure
    │
    ├── Attempt 1: Targeted repair prompt
    │       "Fact f7 says revenue is $4.2M but prose says $4.5M at line 12. Fix line 12 to match f7."
    │       → Re-verify
    │
    ├── Attempt 2: Section-level fallback
    │       Re-generate the failed section from facts using a template (no LLM creativity)
    │       → Re-verify
    │
    └── Still failing: Safe fallback
            Replace unverifiable claim with: "[value not verified -- see fact table]"
            Emit W_UNVERIFIED_CLAIM warning
            Include correct value in the fact table so the user still gets the number
```

The tool never delivers unverified numbers as if they were verified. At most 2 repair attempts are made; total repair time is bounded at 4 seconds.

### 9.4 Attribution

Every fact carries provenance:

```json
{
  "id": "f7",
  "provenance": {
    "query": "SELECT SUM(amount) FROM orders WHERE ordered_at BETWEEN ''2025-07-01'' AND ''2025-09-30''",
    "rows_scanned": 1420000,
    "computation_ms": 42
  }
}
```

The markdown may include footnote-style attribution for key claims (configurable). The envelope always includes full provenance for audit.

### 9.5 Verification Metrics

| Metric | How Measured | Gate (v1) |
|---|---|---|
| Numeric accuracy | % of numbers in prose matching facts within tolerance | 100% (hard gate -- no delivery if any number is unmatched and unrepaired) |
| Claim accuracy | % of rankings/comparisons/trends matching facts | 100% |
| Repair rate | % of summaries needing repair | Track; alert if > 10% |
| Fallback rate | % of summaries with safe-fallback replacements | Track; alert if > 2% |

### 9.6 Limitations

- The verifier checks numbers and structured claims, not qualitative prose ("the data looks healthy" is not verifiable and is discouraged by the prompt).
- Numbers that are correctly computed but misleadingly presented (e.g., cherry-picked time range) are not caught by the verifier -- they require evaluation-level review.
- Locale-specific number formatting (e.g., `1.000,00` vs `1,000.00`) is handled but must be tested per locale.

### 9.7 Verifier Implementation Details

Number extraction handles integers, decimals, percentages, currency with K/M/B suffixes, and locale-aware separators. Matching compares extracted values to fact values within per-fact tolerance. Derived percentages (part/total) are allowed only if both part and total are facts and derivation is declared in derived_from field.

### 9.8 Repair Prompt (Exact Template)

The repair prompt is narrow -- it constrains the LLM to fix only flagged numbers:

    The following markdown contains numbers that do not match the computed facts.
    Fix ONLY the flagged lines. Do not change any other text.
    Facts: {facts_json}
    Failures: {failures_json}
    Markdown (flagged lines marked with [FAIL]): {markdown_with_flags}
    Instructions: For each [FAIL] line, replace the incorrect number with the correct fact value.

This reduces the risk of introducing new errors during repair.

### 9.9 Verifier Testing

| Test Case | Expected Verdict |
|---|---|
| All numbers match facts exactly | Pass |
| Number matches after rounding within tolerance | Pass |
| Number is 1pct off (outside tolerance) | Fail |
| Percentage derived from two facts (declared) | Pass |
| Percentage derived but not declared | Fail |
| Ranking claim matches fact ordering | Pass |
| Ranking claim contradicts fact ordering | Fail |
| Number in code span (column name) | Ignored (not a claim) |
| Number in table cell | Checked |

The verifier has 87 unit tests covering these cases plus locale-specific formatting.

### 9.10 Locale-Aware Number Parsing

The verifier must handle locale-specific number formats:

| Locale | Example | Parsed Value |
|---|---|---|
| en-US | 1,234.56 | 1234.56 |
| de-DE | 1.234,56 | 1234.56 |
| fr-FR | 1 234,56 | 1234.56 |
| en-IN | 1,23,456.78 | 123456.78 |

The verifier detects the locale from the request options.language field and applies the appropriate parsing rules. If no locale is specified, it tries en-US first, then falls back to lenient parsing (strip all grouping separators, treat last separator as decimal).

Currency symbols (dollar, euro, pound, yen) are stripped before parsing. Percent signs are handled by dividing by 100 when the fact is a percentage.

### 9.11 Handling Rounded and Approximate Numbers

LLM prose often rounds numbers for readability (e.g., fact says 1234.56, prose says about 1,200). The verifier handles this:

- **Exact match:** Prose number equals fact value within tolerance -- pass.
- **Rounded match:** Prose number is a rounded version of the fact value -- pass if within rounding tolerance (e.g., 1234.56 rounded to 1200 is within 3 percent).
- **Approximate language:** Phrases like about, approximately, roughly, around signal intentional rounding. The verifier allows wider tolerance (5 percent) when such qualifiers are present.
- **No match:** Prose number does not correspond to any fact value -- flag as unverified.

The tolerance for approximate language is configurable via options.verification_tolerance.

### 9.12 Verifier Performance and Caching

The verifier is designed to be fast:

- **Number extraction:** Single regex pass over the prose (O(n) in prose length).
- **Fact matching:** Hash map lookup per extracted number (O(1) per number).
- **Total time:** Under 10ms for typical prose (500-2000 words, 20-50 numbers).

No caching is needed for the verifier itself (it is stateless and fast). However, the fact set is cached (Section 4.8) so repeated verifications of the same facts do not recompute.

### 9.13 Verifier Testing Strategy

The verifier has its own test suite:

| Test Category | Count | What It Checks |
|---|---|---|
| Number extraction | 50 | Various formats, locales, currencies, percentages |
| Fact matching | 40 | Exact, rounded, approximate, no-match cases |
| Claim checking | 30 | Supported vs unsupported qualitative claims |
| Locale handling | 20 | Different locale formats |
| Edge cases | 20 | Empty prose, no numbers, all numbers verified, etc. |
| Total | 160 | |

Each test case is a triple: (facts, prose, expected_result). The verifier must produce the expected pass/fail for each case. Tests run in under 1 second total.

### 9.14 Faithfulness Metrics and Targets

| Metric | How Measured | Target | Gate |
|---|---|---|---|
| Numeric accuracy | Mechanical: every number in prose matches a fact | 100% | Hard gate (must pass) |
| Claim accuracy | Mechanical + human: qualitative claims supported by facts | 100% | Hard gate |
| Fact coverage | Human: fraction of material facts that appear in prose | >= 80% | Soft gate |
| Fluency | Human: 1-5 rating on readability | >= 4.0 | Soft gate |
| Hallucination rate | Mechanical: numbers/claims not in facts | 0% | Hard gate |

Hard gates must pass for every eval case. Soft gates are aggregated (mean across cases) and must meet the threshold.

### 9.15 Verifier Edge Cases

| Edge Case | Handling |
|---|---|
| Prose contains no numbers | Verifier passes (nothing to check) |
| Fact value is 0 | Zero is a valid number; must appear exactly as 0 if referenced |
| Very large numbers (1e12+) | Scientific notation handled; tolerance is relative (1%) |
| Negative numbers | Sign must match; -5 does not match 5 |
| Percentages | 50% matches fact value 0.5 or 50 depending on fact representation |

The verifier is tested against all edge cases in its dedicated test suite (160 cases, Section 9.13).

### 9.16 Repair Prompt Design

When verification fails, the repair prompt is targeted:

```
SYSTEM: Your previous summary had verification errors. Fix ONLY the errors listed below.
Do not change correct content. Every number must still come from the facts.

ERRORS:
- Line 5: "revenue was $1,500" -- fact f3 says revenue is $1,234.56
- Line 8: "top product was Widget B" -- fact f7 says top product is Widget A

FACTS: [same facts as original call]
PREVIOUS PROSE: [previous output]

Fix the errors and return the corrected markdown.
```

The repair call is cheaper than the original (shorter prompt, fewer tokens) and typically succeeds on the first retry. If it fails again, the template fallback is used.

