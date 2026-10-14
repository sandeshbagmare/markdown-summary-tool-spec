"""Data models for the Repo Adapter."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ColumnInfo(BaseModel):
    name: str
    inferred_type: str
    sample_values: list[Any] = Field(default_factory=list)
    null_rate: float = 0.0
    distinct_count: int | None = None


class DatasetInfo(BaseModel):
    name: str
    row_count: int
    columns: list[ColumnInfo] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    source_kind: str = "inline_json"
    file_path: str | None = None


class SamplingConfig(BaseModel):
    """How data sampling should work for this repo."""

    strategy: Literal["full", "random", "stratified", "reservoir", "window"] = "full"
    sample_size: int | None = Field(default=None, ge=1, description="Rows to sample; None = all rows")
    stratify_by: str | None = None
    window_size: int | None = None
    seed: int = 42
    description: str = ""


class ArgumentSpec(BaseModel):
    """An extra argument the adapted tool needs for this repo."""

    name: str
    type: str = "str"
    required: bool = False
    default: Any = None
    description: str = ""
    example: Any = None


class RepoProfile(BaseModel):
    """Full profile of a target repository — produced by RepoAnalyzer."""

    repo_path: str
    repo_name: str = ""
    language: str = "python"
    framework: str | None = None
    datasets: list[DatasetInfo] = Field(default_factory=list)
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    extra_arguments: list[ArgumentSpec] = Field(default_factory=list)
    connectors_needed: list[str] = Field(default_factory=list)
    llm_hints: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    raw_notes: str = ""


class AdapterSpec(BaseModel):
    """Specification for generating an adapted tool."""

    profile: RepoProfile
    tool_name: str = "create_markdown_summary"
    target_module: str = "adapted_tool"
    sampling: SamplingConfig = Field(default_factory=SamplingConfig)
    extra_arguments: list[ArgumentSpec] = Field(default_factory=list)
    fact_overrides: list[dict[str, Any]] = Field(default_factory=list)
    connector_overrides: dict[str, Any] = Field(default_factory=dict)
    llm_overrides: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
