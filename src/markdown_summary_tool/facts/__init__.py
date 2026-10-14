"""Facts package."""

from markdown_summary_tool.facts.compute import compute_facts
from markdown_summary_tool.facts.planner import FactPlanner, FactSpec

__all__ = ["FactPlanner", "FactSpec", "compute_facts"]
