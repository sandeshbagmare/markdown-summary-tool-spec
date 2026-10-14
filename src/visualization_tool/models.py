"""Pydantic v2 models for the Visualization Tool."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from markdown_summary_tool.models.schemas import DataRef


class VisualizationOptions(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    max_rows: int | None = Field(default=None, ge=1, description="Cap rows per dataset.")
    width: int = Field(default=400, ge=100, le=2000, description="Chart width in pixels.")
    height: int = Field(default=300, ge=100, le=2000, description="Chart height in pixels.")
    locale: str = Field(default="en-US", description="BCP-47 locale.")
    include_warnings: bool = Field(default=True)


class VisualizationRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    datasets: list[DataRef] = Field(min_length=1)
    question: str = Field(min_length=1)
    chart_type: str = Field(default="auto", description="Chart type: auto, bar, line, pie, scatter, table.")
    options: VisualizationOptions | None = None

    @field_validator("datasets")
    @classmethod
    def _unique_names(cls, v: list[DataRef]) -> list[DataRef]:
        names = [d.name for d in v]
        if len(names) != len(set(names)):
            raise ValueError("dataset names must be unique")
        return v


class VisualizationResponse(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    chart_spec: dict[str, Any] = Field(description="Vega-Lite spec or chart descriptor.")
    facts: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
