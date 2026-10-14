"""Extensible command tool — arbitrary markdown requirements, fast path.

Best practices:
- Single responsibility: command → markdown + HTML presentation.
- Pure helpers, no global state.
- Sanitizes preamble/postamble via presentation layer.
- Extensible via options: template, sections, style, preamble/postamble/title/theme.
- Fast: reuses pipeline with minimal overhead; supports include_html toggle.
"""

from __future__ import annotations

import json
from typing import Any

try:
    from langchain_core.tools import tool as _lc_tool  # type: ignore[import-untyped]

    tool = _lc_tool  # type: ignore[assignment]
except ImportError:
    from pydantic import BaseModel, Field, create_model

    def tool(func=None, **_kwargs):  # type: ignore[no-untyped-def]
        def _wrap(fn):  # type: ignore[no-untyped-def]
            import inspect

            sig = inspect.signature(fn)
            fields: dict[str, Any] = {}
            for name, param in sig.parameters.items():
                ann = param.annotation if param.annotation is not inspect.Parameter.empty else str
                if param.default is inspect.Parameter.empty:
                    fields[name] = (ann, Field(description=name))
                else:
                    fields[name] = (ann, Field(default=param.default, description=name))
            try:
                args_model = create_model(f"{fn.__name__}Args", **fields)  # type: ignore[call-overload]
            except Exception:
                class _Args(BaseModel):  # type: ignore[no-redef]
                    pass

                args_model = _Args  # type: ignore[assignment]

            fn.name = fn.__name__  # type: ignore[attr-defined]
            fn.description = (fn.__doc__ or "").strip()  # type: ignore[attr-defined]
            fn.args_schema = args_model  # type: ignore[attr-defined]

            def _invoke(args: dict[str, Any]) -> Any:  # type: ignore[no-untyped-def]
                return fn(**args)

            fn.invoke = _invoke  # type: ignore[attr-defined]
            return fn

        if func is None:
            return _wrap
        return _wrap(func)


@tool
def create_command_summary(
    datasets_json: str,
    command: str,
    options_json: str = "{}",
) -> str:
    """Create a markdown report for any command/requirement — extensible presentation.

    Use this when you need a markdown summary for an arbitrary requirement
    (not just a question). Supports custom preamble/postamble/title/theme,
    extra sections, and fast HTML rendering.

    Args:
        datasets_json: JSON string of list[DataRef] — each with kind, name, data/url.
        command: Natural-language command or requirement (e.g. "Build a KPI summary with preamble").
        options_json: JSON string of options — preamble, postamble, title, theme (light|dark),
            include_html (bool), extra_sections ([{title, html}]), max_rows, redact, locale.

    Returns:
        JSON string with markdown, html (self-contained), preamble, postamble, facts, warnings, meta.
    """
    try:
        datasets = json.loads(datasets_json) if datasets_json else []
        if isinstance(datasets, str):
            datasets = json.loads(datasets)
        if not isinstance(datasets, list):
            raise ValueError("datasets_json must be a JSON array of DataRef objects")

        options: dict[str, Any] = {}
        if options_json and options_json.strip():
            parsed = json.loads(options_json)
            if isinstance(parsed, dict):
                options = parsed
            elif parsed is None:
                options = {}
            else:
                raise ValueError("options_json must be a JSON object")

        if not command or not command.strip():
            raise ValueError("command must be a non-empty string")

        # Normalize extensible options
        extra_sections = options.get("extra_sections")
        if extra_sections is not None and not isinstance(extra_sections, list):
            raise ValueError("extra_sections must be a list of {title, html}")

        request: dict[str, Any] = {
            "datasets": datasets,
            "question": command,
            "options": options,
        }

        from markdown_summary_tool.engine.pipeline import run

        try:
            from markdown_summary_tool.llm.client import get_llm_client

            llm = get_llm_client()
        except ImportError:
            llm = None

        result = run(request, llm=llm)

        # If extra_sections provided, rebuild HTML to include them (pipeline already handles preamble/postamble)
        if extra_sections:
            try:
                from markdown_summary_tool.presentation.html import build_report_html

                html = build_report_html(
                    markdown=result.get("markdown", ""),
                    preamble=result.get("preamble", "") or options.get("preamble") or "",
                    postamble=result.get("postamble", "") or options.get("postamble") or "",
                    title=options.get("title") or "Report",
                    facts=result.get("facts"),
                    warnings=result.get("warnings") if options.get("include_warnings", True) else None,
                    meta=result.get("meta"),
                    extra_sections=extra_sections,
                    theme=options.get("theme") or "light",
                )
                result["html"] = html
            except Exception:
                pass

        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as exc:
        return json.dumps(
            {"error_code": "command_failed", "message": str(exc), "details": {"exception": type(exc).__name__}},
            ensure_ascii=False,
        )


# DeepAgents registration exports
command_tool = create_command_summary

COMMAND_TOOL_SPEC: dict[str, Any] = {
    "name": "create_command_summary",
    "description": (
        create_command_summary.description
        if hasattr(create_command_summary, "description")
        else create_command_summary.__doc__ or "Create a markdown report for any command."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "datasets_json": {"type": "string", "description": "JSON string of list[DataRef]"},
            "command": {"type": "string", "description": "Natural-language command or requirement"},
            "options_json": {"type": "string", "description": "JSON string of options (preamble, postamble, title, theme, extra_sections)", "default": "{}"},
        },
        "required": ["datasets_json", "command"],
    },
}
