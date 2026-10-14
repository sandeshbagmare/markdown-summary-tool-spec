"""Repo Adapter — adapt the Markdown Summary / Visualization tools to any repository.

Public API:
    from repo_adapter import RepoAnalyzer, ToolAdapter, AdapterSpec
    from repo_adapter.models import RepoProfile, SamplingConfig, ArgumentSpec
"""

from repo_adapter.adapter import ToolAdapter
from repo_adapter.analyzer import RepoAnalyzer
from repo_adapter.models import AdapterSpec, ArgumentSpec, RepoProfile, SamplingConfig

__version__ = "1.0.0"
__all__ = ["RepoAnalyzer", "ToolAdapter", "AdapterSpec", "RepoProfile", "SamplingConfig", "ArgumentSpec"]
