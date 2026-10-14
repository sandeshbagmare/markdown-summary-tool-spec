from markdown_summary_tool.verifier.verify import verify, extract_numbers
from markdown_summary_tool.sanitizer.sanitize import sanitize


def test_extract_numbers():
    assert 1234.0 in extract_numbers("value is 1,234")
    assert 42.0 in extract_numbers("$42.00")


def test_verify_pass():
    facts = [{"id": "f1", "value": 42, "formatted": "42", "tolerance": None}]
    passed, v = verify("The answer is 42.", facts)
    assert passed, v


def test_verify_hallucination():
    facts = [{"id": "f1", "value": 42, "formatted": "42", "tolerance": None}]
    passed, v = verify("The answer is 99.", facts)
    assert not passed
    assert any("hallucinated" in x for x in v)


def test_sanitize_strips_html():
    out = sanitize('<script>alert(1)</script> hello [x](javascript:alert(1))')
    assert "<script>" not in out
    assert "javascript:" not in out
