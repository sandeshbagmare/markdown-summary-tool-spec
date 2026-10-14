"""Verifier package — mechanical number checking + repair loop."""

from markdown_summary_tool.verifier.repair import repair
from markdown_summary_tool.verifier.verify import extract_numbers, verify

__all__ = ["extract_numbers", "verify", "repair"]
