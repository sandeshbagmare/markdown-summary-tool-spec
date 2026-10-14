"""Markdown sanitizer — strips dangerous content, handles column redaction."""

from __future__ import annotations

import re
from typing import Any

# -- regex fallbacks (used when nh3 is unavailable) --

_HTML_TAG_RE = re.compile(r"<[^>]*>", re.DOTALL)
_JS_URI_RE = re.compile(r"(?:javascript|data|vbscript)\s*:", re.IGNORECASE)
_EVENT_HANDLER_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def _strip_html_regex(text: str) -> str:
    text = _HTML_COMMENT_RE.sub("", text)
    text = _HTML_TAG_RE.sub("", text)
    return text


def _strip_dangerous_uris(text: str) -> str:
    # Remove markdown links/images whose URL is javascript:/data:/vbscript:
    # Pattern: [text](url) or ![alt](url)
    def _replace_link(m: re.Match[str]) -> str:
        prefix = m.group(1)  # "!" or ""
        label = m.group(2)
        url = m.group(3)
        if _JS_URI_RE.search(url):
            return label  # keep label text, drop link
        return m.group(0)

    text = re.sub(r"(!?)\[([^\]]*)\]\(([^()]*(?:\([^)]*\)[^()]*)*)\)", _replace_link, text)
    text = re.sub(r"(?:javascript|data|vbscript)\s*:[^\s)]*", "", text, flags=re.IGNORECASE)
    return text


def _strip_event_handlers(text: str) -> str:
    return _EVENT_HANDLER_RE.sub("", text)


def sanitize(
    markdown: str,
    redacted_columns: list[str] | None = None,
) -> str:
    """Sanitize markdown output.

    - Strips raw HTML tags (via nh3 if available, else regex).
    - Removes ``javascript:`` / ``data:`` / ``vbscript:`` URIs.
    - Removes event handlers (``on*`` attributes).
    - Allows only CommonMark + GFM tables (no raw HTML passthrough).
    - Removes mentions of redacted columns.

    Args:
        markdown: Raw markdown string.
        redacted_columns: Column names that must not appear in output.

    Returns:
        Sanitized markdown string.
    """
    text = markdown

    # 1. Strip HTML — prefer nh3, fallback to regex
    try:
        import nh3  # type: ignore[import-untyped]

        # nh3 cleans HTML; for markdown we strip all tags
        text = nh3.clean(text, tags=set())
        # nh3 may leave tag content; ensure no residual tags
        text = _HTML_TAG_RE.sub("", text)
    except ImportError:
        text = _strip_html_regex(text)

    # 2. Strip dangerous URIs
    text = _strip_dangerous_uris(text)

    # 3. Strip event handlers
    text = _strip_event_handlers(text)

    # 4. Column redaction — remove lines/mentions of redacted columns
    if redacted_columns:
        for col in redacted_columns:
            if not col:
                continue
            # Remove markdown table rows/columns mentioning the redacted column
            # Strategy: drop lines where the column name appears as a standalone
            # header or cell value, and replace inline mentions with [redacted]
            pattern = re.compile(re.escape(col), re.IGNORECASE)
            lines = text.split("\n")
            kept: list[str] = []
            for line in lines:
                if pattern.search(line):
                    # If line is a table row containing the column, drop it
                    if "|" in line:
                        # Check if column name is a cell value
                        cells = [c.strip() for c in line.split("|")]
                        if any(c.lower() == col.lower() for c in cells):
                            continue
                        # Otherwise redact the cell content
                        line = pattern.sub("[redacted]", line)
                        kept.append(line)
                    else:
                        line = pattern.sub("[redacted]", line)
                        kept.append(line)
                else:
                    kept.append(line)
            text = "\n".join(kept)

    # 5. Collapse excessive blank lines (max 2 consecutive)
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    return text.strip() + "\n" if text.strip() else ""
