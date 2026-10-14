import pytest
from markdown_summary_tool.engine.pipeline import run


def test_inline_json_basic():
    req = {
        "datasets": [
            {"kind": "inline_json", "name": "sales", "data": [
                {"region": "East", "amount": 100},
                {"region": "West", "amount": 200},
                {"region": "East", "amount": 150},
            ]}
        ],
        "question": "Summarize sales by region",
        "options": {"locale": "en-US"},
    }
    result = run(req)
    assert "markdown" in result
    assert len(result["facts"]) > 0
    assert result["meta"]["verified"] is True
    # markdown must contain at least one fact value
    assert any(f["formatted"] in result["markdown"] for f in result["facts"] if f["formatted"] not in ("—", "error"))


def test_empty_dataset():
    req = {
        "datasets": [{"kind": "inline_json", "name": "empty", "data": []}],
        "question": "Summarize",
    }
    result = run(req)
    assert "markdown" in result
    assert isinstance(result["warnings"], list)


def test_inline_csv():
    csv_data = "name,score\nAlice,90\nBob,80\nAlice,95"
    req = {
        "datasets": [{"kind": "inline_csv", "name": "scores", "data": csv_data}],
        "question": "Average score?",
    }
    result = run(req)
    assert result["meta"]["verified"] is True


def test_redaction():
    req = {
        "datasets": [{"kind": "inline_json", "name": "t", "data": [{"secret": "abc", "val": 1}]}],
        "question": "Summarize",
        "options": {"redact": ["secret"]},
    }
    result = run(req)
    assert "secret" not in result["markdown"].lower() or "[redacted]" in result["markdown"]
