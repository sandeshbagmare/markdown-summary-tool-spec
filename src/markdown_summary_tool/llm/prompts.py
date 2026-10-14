"""Prompt templates for the Markdown Summary Tool.

The LLM must verbalise pre-computed facts — never compute or invent numbers.
Facts are wrapped as JSON so the model has a single authoritative source.
"""

from __future__ import annotations

import json
from typing import Any

SYSTEM_PROMPT = (
    "You are a markdown summarization assistant operating in compute-then-write mode.\n"
    "You will be given a JSON object containing pre-computed facts. Each fact has an\n"
    "id, kind, value, and formatted string.\n"
    "RULES (must follow exactly):\n"
    "1. Use ONLY the numbers provided in the facts JSON. Never invent, estimate, or\n"
    "   recompute any numeric value.\n"
    "2. When you mention a numeric value, copy its `formatted` string verbatim.\n"
    "3. Do not introduce any number that does not appear in the facts JSON.\n"
    "4. If a fact's value is missing or marked as error, do not mention it.\n"
    "5. Output valid CommonMark markdown only (headings, lists, tables, emphasis).\n"
    "6. Do not output raw HTML, javascript: URIs, or event handlers.\n"
    "7. Keep the summary concise and directly answer the user's question.\n"
)


def build_prompt(
    question: str,
    facts: list[dict[str, Any]],
    warnings: list[str] | None = None,
    profile_summary: str | None = None,
) -> str:
    """Build the user prompt that wraps facts as JSON.

    Args:
        question: The user's natural-language question.
        facts: List of fact dicts (each with id/kind/value/formatted/provenance).
        warnings: Optional non-fatal warnings to surface.
        profile_summary: Optional short dataset profile description.

    Returns:
        A prompt string ready to send as the user message.
    """
    facts_json = json.dumps(facts, indent=2, ensure_ascii=False, default=str)
    parts: list[str] = []
    parts.append(f"Question: {question}")
    parts.append("")
    if profile_summary:
        parts.append(f"Dataset profile: {profile_summary}")
        parts.append("")
    parts.append("Pre-computed facts (authoritative — use ONLY these numbers):")
    parts.append("```json")
    parts.append(facts_json)
    parts.append("```")
    parts.append("")
    if warnings:
        parts.append("Warnings (mention briefly if relevant):")
        for w in warnings:
            parts.append(f"- {w}")
        parts.append("")
    parts.append(
        "Instructions: Write a markdown summary that answers the question above. "
        "Verbalise the facts — do not compute new numbers. Copy each `formatted` "
        "value exactly as shown. Every number in your output must correspond to a "
        "`formatted` value in the facts JSON."
    )
    return "\n".join(parts)
