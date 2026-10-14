"""Pydantic v2 schemas for the Markdown Summary Tool API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DataRef(BaseModel):
    """Reference to a single dataset."""

    model_config = ConfigDict(strict=True, extra="forbid")

    kind: Literal["inline_json", "inline_csv", "url", "connector"] = Field(
        description="How the dataset is supplied."
    )
    name: str = Field(min_length=1, max_length=128, description="Dataset identifier (unique within request).")
    data: Any | None = Field(default=None, description="Inline payload for inline_json / inline_csv kinds.")
    url: str | None = Field(default=None, description="Source URL for url kind.")
    connector_config: dict[str, Any] | None = Field(
        default=None, description="Connector parameters for connector kind."
    )
    options: dict[str, Any] = Field(default_factory=dict, description="Per-dataset options (e.g. delimiter, encoding).")

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> DataRef:
        if self.kind in ("inline_json", "inline_csv") and self.data is None:
            raise ValueError(f"kind '{self.kind}' requires 'data'")
        if self.kind == "url" and not self.url:
            raise ValueError("kind 'url' requires 'url'")
        if self.kind == "connector" and not self.connector_config:
            raise ValueError("kind 'connector' requires 'connector_config'")
        return self


class SummaryOptions(BaseModel):
    """Optional knobs for summary generation."""

    model_config = ConfigDict(strict=True, extra="forbid")

    max_rows: int | None = Field(default=None, ge=1, description="Cap rows processed per dataset.")
    redact: list[str] = Field(default_factory=list, description="Column names to redact from output.")
    locale: str = Field(default="en-US", description="BCP-47 locale for number/date formatting.")
    timeout_ms: int = Field(default=30_000, ge=100, le=300_000, description="End-to-end timeout in milliseconds.")
    include_warnings: bool = Field(default=True, description="Whether to include warnings in the response.")
    # Presentation — self-contained HTML report
    preamble: str | None = Field(default=None, description="HTML fragment shown before markdown body (sanitized).")
    postamble: str | None = Field(default=None, description="HTML fragment shown after markdown body (sanitized).")
    title: str | None = Field(default=None, description="Report title for HTML <title> and header.")
    theme: str | None = Field(default=None, description="HTML theme: light | dark.")
    include_html: bool = Field(default=True, description="Whether to include rendered HTML in response.")


class SummaryRequest(BaseModel):
    """POST /v1/summarize request body."""

    model_config = ConfigDict(strict=True, extra="forbid")

    datasets: list[DataRef] = Field(min_length=1, description="One or more datasets to summarise.")
    question: str = Field(min_length=1, description="Natural-language question / instruction for the summary.")
    options: SummaryOptions | None = Field(default=None, description="Optional generation options.")

    @field_validator("datasets")
    @classmethod
    def _unique_names(cls, v: list[DataRef]) -> list[DataRef]:
        names = [d.name for d in v]
        if len(names) != len(set(names)):
            raise ValueError("dataset names must be unique")
        return v


class Fact(BaseModel):
    """A single computed fact that the LLM may verbalise."""

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(description="Stable fact identifier.")
    kind: str = Field(description="Fact kind (e.g. count, sum, mean, topk).")
    value: float | int | str = Field(description="Raw computed value.")
    formatted: str = Field(description="Locale-formatted representation.")
    provenance: dict[str, Any] = Field(default_factory=dict, description="Source / derivation metadata.")
    tolerance: float | None = Field(default=None, ge=0, description="Allowed numeric deviation during verification.")


class SummaryResponse(BaseModel):
    """POST /v1/summarize success response."""

    model_config = ConfigDict(strict=True, extra="forbid")

    markdown: str = Field(description="Verified markdown summary.")
    facts: list[Fact] = Field(default_factory=list, description="Facts backing the summary.")
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings.")
    artifacts: dict[str, Any] = Field(default_factory=dict, description="Supplementary artifacts (e.g. tables).")
    meta: dict[str, Any] = Field(default_factory=dict, description="Timing, model, and trace metadata.")


class ErrorResponse(BaseModel):
    """Uniform error envelope."""

    model_config = ConfigDict(strict=True, extra="forbid")

    error_code: str = Field(description="Machine-readable error code.")
    message: str = Field(description="Human-readable error message.")
    details: dict[str, Any] | None = Field(default=None, description="Optional structured details.")
