"""LLM client abstractions for the Markdown Summary Tool.

The LLM is used only to verbalise pre-computed facts — never to compute numbers.
The prompt always includes the facts JSON and instructs the model to use only
those numbers.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from markdown_summary_tool.llm.prompts import SYSTEM_PROMPT


class LLMClient(ABC):
    """Abstract LLM client — single async method."""

    @abstractmethod
    async def generate(self, prompt: str, facts_json: str, max_tokens: int = 1024) -> str:
        """Generate markdown from *prompt* grounded in *facts_json*.

        Args:
            prompt: Full user prompt (already includes facts JSON).
            facts_json: Raw JSON string of facts (for logging / debugging).
            max_tokens: Maximum tokens to generate.

        Returns:
            Markdown string.
        """


class MockLLMClient(LLMClient):
    """Deterministic mock — interpolates fact values into markdown.

    Useful for tests and offline development. Never calls a real API.
    """

    def __init__(self, template: str | None = None) -> None:
        self.template = template
        self.last_prompt: str | None = None
        self.last_facts_json: str | None = None

    async def generate(self, prompt: str, facts_json: str, max_tokens: int = 1024) -> str:
        self.last_prompt = prompt
        self.last_facts_json = facts_json
        try:
            facts: list[dict[str, Any]] = json.loads(facts_json) if facts_json else []
        except (json.JSONDecodeError, TypeError):
            facts = []

        if self.template is not None:
            return self.template

        if not facts:
            return "## Summary\n\nNo facts were available to summarize.\n"

        lines: list[str] = ["## Summary", ""]
        for f in facts:
            fid = f.get("id", "?")
            formatted = f.get("formatted", str(f.get("value", "")))
            kind = f.get("kind", "")
            desc = f.get("provenance", {}).get("description", fid) if isinstance(f.get("provenance"), dict) else fid
            if formatted in ("—", "error", ""):
                continue
            lines.append(f"- **{desc}** ({kind}): {formatted}")
        lines.append("")
        lines.append("_All values are pre-computed and verified._")
        return "\n".join(lines)


class OpenAICompatibleClient(LLMClient):
    """httpx-based client for any OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def generate(self, prompt: str, facts_json: str, max_tokens: int = 1024) -> str:
        try:
            import httpx  # type: ignore[import-untyped]
        except ImportError as exc:
            raise RuntimeError("httpx is required for OpenAICompatibleClient; pip install httpx") from exc

        # Build messages: system instructs to only use facts numbers
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.2,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Unexpected chat completions response shape: {data!r}") from exc
