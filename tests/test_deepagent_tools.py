"""Tests for DeepAgent tool compatibility."""

from __future__ import annotations

import json
import os


def test_summarize_tool_has_name_description_args_schema():
    from markdown_summary_tool.tools.summarize_tool import create_markdown_summary

    assert hasattr(create_markdown_summary, "name")
    assert create_markdown_summary.name == "create_markdown_summary"
    assert hasattr(create_markdown_summary, "description")
    assert isinstance(create_markdown_summary.description, str)
    assert len(create_markdown_summary.description) > 10
    # args_schema or args
    assert hasattr(create_markdown_summary, "args_schema") or hasattr(create_markdown_summary, "args")


def test_visualization_tool_has_name_description():
    from visualization_tool.tool import create_visualization

    assert hasattr(create_visualization, "name")
    assert create_visualization.name == "create_visualization"
    assert hasattr(create_visualization, "description")
    assert isinstance(create_visualization.description, str)
    assert len(create_visualization.description) > 10


def test_get_llm_client_mock_when_env_not_set(monkeypatch):
    monkeypatch.delenv("API_BASE", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    from markdown_summary_tool.llm.client import MockLLMClient, get_llm_client

    client = get_llm_client()
    assert isinstance(client, MockLLMClient)


def test_get_llm_client_openai_when_env_set(monkeypatch):
    monkeypatch.setenv("API_BASE", "https://example.com/v1")
    monkeypatch.setenv("API_KEY", "test-key")
    from markdown_summary_tool.llm.client import OpenAICompatibleClient, get_llm_client

    client = get_llm_client()
    assert isinstance(client, OpenAICompatibleClient)
    assert client.base_url == "https://example.com/v1"
    assert client.model == "claude-fable-5.1"


def _call(tool, **kwargs):  # type: ignore[no-untyped-def]
    if hasattr(tool, "invoke"):
        return tool.invoke(kwargs)
    return tool(**kwargs)


def test_create_markdown_summary_returns_valid_json_with_markdown():
    from markdown_summary_tool.tools.summarize_tool import create_markdown_summary

    datasets_json = json.dumps(
        [{"kind": "inline_json", "name": "t", "data": [{"x": 1, "y": 2}, {"x": 3, "y": 4}]}]
    )
    raw = _call(create_markdown_summary, datasets_json=datasets_json, question="Summarize x and y")
    parsed = json.loads(raw)
    assert "markdown" in parsed, f"missing markdown key, got {list(parsed.keys())}"
    assert isinstance(parsed["markdown"], str)
    assert len(parsed["markdown"]) > 0


def test_create_visualization_returns_valid_json_with_chart_spec():
    from visualization_tool.tool import create_visualization

    datasets_json = json.dumps(
        [{"kind": "inline_json", "name": "t", "data": [{"cat": "A", "val": 10}, {"cat": "B", "val": 20}]}]
    )
    raw = _call(create_visualization, datasets_json=datasets_json, question="Bar chart of val by cat", chart_type="bar")
    parsed = json.loads(raw)
    assert "chart_spec" in parsed, f"missing chart_spec, got {list(parsed.keys())}"
    assert isinstance(parsed["chart_spec"], dict)
    assert "$schema" in parsed["chart_spec"]


def test_summarize_tool_error_on_empty_question():
    from markdown_summary_tool.tools.summarize_tool import create_markdown_summary

    datasets_json = json.dumps([{"kind": "inline_json", "name": "t", "data": [{"x": 1}]}])
    raw = _call(create_markdown_summary, datasets_json=datasets_json, question="")
    parsed = json.loads(raw)
    assert "error_code" in parsed


def test_visualization_tool_error_on_empty_question():
    from visualization_tool.tool import create_visualization

    datasets_json = json.dumps([{"kind": "inline_json", "name": "t", "data": [{"x": 1}]}])
    raw = _call(create_visualization, datasets_json=datasets_json, question="")
    parsed = json.loads(raw)
    assert "error_code" in parsed
