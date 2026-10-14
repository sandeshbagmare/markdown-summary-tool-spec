"""Generate an adapted tool file from a RepoProfile."""

from __future__ import annotations

from pathlib import Path

from repo_adapter.adapter import ToolAdapter
from repo_adapter.models import RepoProfile


def generate_adapted_tool(profile: RepoProfile, output_dir: str | Path, tool_name: str = "create_markdown_summary", target_module: str = "adapted_tool") -> Path:
    adapter = ToolAdapter.from_profile(profile, tool_name=tool_name, target_module=target_module)
    return adapter.write(output_dir)
