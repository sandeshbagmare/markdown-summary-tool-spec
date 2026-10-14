"""Repair loop — re-prompt LLM once when verification fails."""

from __future__ import annotations

import json
from typing import Any

from markdown_summary_tool.verifier.verify import verify


async def repair(
    markdown: str,
    facts: list[dict[str, Any]],
    violations: list[str],
    llm: Any,
    max_retries: int = 1,
) -> tuple[str, bool, list[str]]:
    """Attempt to repair *markdown* by re-calling the LLM with violation feedback.

    Args:
        markdown: The original (failing) markdown.
        facts: Ground-truth facts.
        violations: Violations from :func:`verify`.
        llm: An :class:`LLMClient` instance with ``generate(prompt, facts_json)``.
        max_retries: Maximum repair attempts (default 1).

    Returns:
        ``(markdown, passed, violations)`` after repair (or original if repair
        still fails).
    """
    facts_json = json.dumps(facts, indent=2, ensure_ascii=False, default=str)
    current = markdown
    current_violations = violations

    for _ in range(max_retries):
        repair_prompt = (
            "Your previous markdown summary had verification errors. "
            "Fix ONLY the issues listed below. Do not introduce any new numbers.\n"
            "\n"
            "Violations:\n"
            + "\n".join(f"- {v}" for v in current_violations)
            + "\n\nPre-computed facts (authoritative — use ONLY these numbers):\n"
            "```json\n"
            + facts_json
            + "\n```\n"
            "\nPrevious markdown:\n"
            + current
            + "\n\nInstructions: Return corrected markdown. Copy each `formatted` "
            "value exactly. Every number must correspond to a fact."
        )
        try:
            current = await llm.generate(repair_prompt, facts_json)
        except Exception:
            break

        passed, new_violations = verify(current, facts)
        if passed:
            return current, True, []
        current_violations = new_violations

    # Final verification of last attempt
    passed, final_violations = verify(current, facts)
    return current, passed, final_violations
