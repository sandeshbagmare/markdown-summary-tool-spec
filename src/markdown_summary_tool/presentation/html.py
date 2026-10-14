"""HTML report builder — preamble + markdown + postamble → sanitized HTML.

Best practices:
- Single responsibility: only presentation, no data fetching.
- Pure functions, no global state.
- Sanitizes preamble/postamble via nh3 allowlist; markdown via markdown lib.
- Graceful fallback if markdown/nh3 missing.
"""

from __future__ import annotations

import html as _html
import re
from typing import Any

_ALLOWED_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "strong", "em", "code", "pre", "blockquote", "a", "hr", "br", "span", "div", "section", "header", "footer", "article"}
_ALLOWED_ATTRS = {"a": {"href", "title"}, "th": {"align"}, "td": {"align"}, "code": {"class"}, "pre": {"class"}, "span": {"class", "style"}, "div": {"class", "style"}, "section": {"class"}, "header": {"class"}, "footer": {"class"}}


def _sanitize_html_fragment(fragment: str) -> str:
    """Sanitize an HTML fragment via nh3 allowlist; fallback strips script/style."""
    if not fragment or not fragment.strip():
        return ""
    try:
        import nh3  # type: ignore[import-untyped]
        return nh3.clean(fragment, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, link_rel=None)  # type: ignore[call-arg]
    except ImportError:
        # Fallback: strip script/style/iframe and event handlers
        frag = re.sub(r"<(script|style|iframe)[^>]*>.*?</\1>", "", fragment, flags=re.DOTALL | re.IGNORECASE)
        frag = re.sub(r"\bon\w+\s*=\s*\"[^\"]*\"", "", frag, flags=re.IGNORECASE)
        frag = re.sub(r"\bon\w+\s*=\s*'[^']*'", "", frag, flags=re.IGNORECASE)
        frag = re.sub(r"javascript\s*:", "", frag, flags=re.IGNORECASE)
        return frag


def markdown_to_html(md: str) -> str:
    """Convert markdown to HTML. Falls back to escaped <pre> if lib missing."""
    if not md or not md.strip():
        return ""
    try:
        import markdown as _md  # type: ignore[import-untyped]
        return _md.markdown(md, extensions=["tables", "fenced_code", "smarty"])
    except ImportError:
        return f"<pre>{_html.escape(md)}</pre>"


def build_report_html(
    *,
    markdown: str = "",
    preamble: str = "",
    postamble: str = "",
    title: str = "Report",
    facts: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    extra_sections: list[dict[str, str]] | None = None,
    theme: str = "light",
) -> str:
    """Build a complete self-contained HTML report.

    Args:
        markdown: Verified markdown body (converted to HTML).
        preamble: HTML fragment shown before body (sanitized).
        postamble: HTML fragment shown after body (sanitized).
        title: Page <title> and header.
        facts: Optional facts to render as appendix table.
        warnings: Optional warnings list.
        meta: Optional meta dict (elapsed_ms, verified, etc.).
        extra_sections: Optional [{title, html}] injected between body and postamble.
        theme: light | dark.

    Returns:
        Complete HTML document string (<!DOCTYPE html>...).
    """
    safe_title = _html.escape(title)
    pre_html = _sanitize_html_fragment(preamble)
    post_html = _sanitize_html_fragment(postamble)
    body_html = markdown_to_html(markdown)

    bg = "#ffffff" if theme != "dark" else "#1a1a1a"
    fg = "#1a1a1a" if theme != "dark" else "#e8e8e8"
    card_bg = "#f8f9fa" if theme != "dark" else "#2a2a2a"
    border = "#e0e0e0" if theme != "dark" else "#444"

    css = f"""
    *{{box-sizing:border-box}} body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:860px;margin:0 auto;padding:24px;background:{bg};color:{fg};line-height:1.6}}
    h1,h2,h3{{margin-top:1.2em}} table{{border-collapse:collapse;width:100%;margin:12px 0}} th,td{{border:1px solid {border};padding:8px 10px;text-align:left}} th{{background:{card_bg}}}
    pre{{background:{card_bg};padding:12px;border-radius:6px;overflow:auto}} code{{background:{card_bg};padding:2px 5px;border-radius:4px}}
    .preamble{{background:{card_bg};border-left:4px solid #4a90d9;padding:12px 16px;border-radius:6px;margin-bottom:20px}}
    .postamble{{background:{card_bg};border-left:4px solid #7bc67e;padding:12px 16px;border-radius:6px;margin-top:20px}}
    .meta{{font-size:12px;color:#888;margin-top:16px}} .facts-table{{font-size:13px}} .warnings{{color:#b45309;background:#fef3c7;padding:10px 14px;border-radius:6px;margin:12px 0}}
    a{{color:#4a90d9}}
    """

    parts: list[str] = []
    parts.append("<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"utf-8\">")
    parts.append(f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{safe_title}</title>")
    parts.append(f"<style>{css}</style></head><body>")
    parts.append(f"<header><h1>{safe_title}</h1></header>")

    if pre_html:
        parts.append(f'<section class="preamble">{pre_html}</section>')
    if body_html:
        parts.append(f'<article class="body">{body_html}</article>')
    if extra_sections:
        for sec in extra_sections:
            st = _html.escape(sec.get("title", ""))
            sh = _sanitize_html_fragment(sec.get("html", ""))
            if sh:
                parts.append(f'<section class="extra"><h2>{st}</h2>{sh}</section>')
    if warnings:
        items = "".join(f"<li>{_html.escape(w)}</li>" for w in warnings)
        parts.append(f'<div class="warnings"><strong>Warnings</strong><ul>{items}</ul></div>')
    if facts:
        rows = "".join(
            f"<tr><td>{_html.escape(str(f.get('id','')))}</td><td>{_html.escape(str(f.get('kind','')))}</td><td>{_html.escape(str(f.get('formatted', f.get('value',''))))}</td></tr>"
            for f in facts
        )
        parts.append(f'<section class="facts"><h3>Facts</h3><table class="facts-table"><thead><tr><th>ID</th><th>Kind</th><th>Value</th></tr></thead><tbody>{rows}</tbody></table></section>')
    if post_html:
        parts.append(f'<section class="postamble">{post_html}</section>')
    if meta:
        verified = meta.get("verified")
        badge = "✓ verified" if verified else ("✗ unverified" if verified is False else "")
        elapsed = meta.get("elapsed_ms", "")
        parts.append(f'<div class="meta">{badge} {elapsed}ms</div>' if badge or elapsed else "")

    parts.append("</body></html>")
    return "".join(p for p in parts if p)
