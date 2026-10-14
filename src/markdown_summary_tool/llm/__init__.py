"""LLM package — client + prompts for compute-then-write."""

from markdown_summary_tool.llm.client import LLMClient, MockLLMClient, OpenAICompatibleClient
from markdown_summary_tool.llm.prompts import SYSTEM_PROMPT, build_prompt

__all__ = ["LLMClient", "MockLLMClient", "OpenAICompatibleClient", "SYSTEM_PROMPT", "build_prompt"]
