# Markdown Summary Tool — Technical Specification v1.0

> **Deterministic computation + LLM prose over large, untrusted, multi-dataset inputs**

80-page technical specification for `create_markdown_summary` — a compute-then-write system that turns large, multi-dataset service data into verified markdown.

## Architecture

**Engine computes → LLM narrates → Verifier enforces.**

- **DuckDB push-down** computes every number over the full datasets (no sampling for final values)
- **Small/cheap LLM** (one call) verbalizes pre-computed facts into fluent markdown
- **Mechanical verifier** checks every number in the prose against the fact set within tolerance
- **Sanitizer** strips dangerous markdown (raw HTML, `javascript:` URIs, event handlers)

## Documents

| File | Description |
|------|-------------|
| [`Markdown_Summary_Tool_Technical_Specification_v1.0.pdf`](./Markdown_Summary_Tool_Technical_Specification_v1.0.pdf) | Full 80-page spec (this tool) |
| [`Visualization_Tool_Technical_Specification.pdf`](./Visualization_Tool_Technical_Specification.pdf) | Sibling spec — Visualization Tool (reference) |
| [`build/`](./build/) | Source markdown parts (15) + `stitch.py` PDF builder |

## Spec Contents (21 sections)

1. Introduction & Scope · 2. Research Findings · 3. Decision Log (20 decisions) · 4. System Architecture · 5. Tool Input Spec · 6. Processing Pipeline (10 stages) · 7. Data Handling · 8. Summary Design · 9. Faithfulness & Verification · 10. Model Call Design · 11. Tool Output Spec · 12. Consistency & Quality · 13. Security & Privacy · 14. Errors & Warnings · 15. Testing & Evaluation (115-case harness) · 16. Operations & Observability · 17. Implementation Blueprint · 18. Worked Examples (8) · 19. Comparison · 20. Roadmap/Risks/Open Questions · 21. Appendices A–N

## Rebuild the PDF

```powershell
pip install reportlab pymupdf
python build/stitch.py
# → Markdown_Summary_Tool_Technical_Specification_v1.0.pdf (80 pages)
```

## License

Draft for engineering review — confidential.
