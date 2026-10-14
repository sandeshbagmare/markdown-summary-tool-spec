"""DeepAgent-compatible tool wrapper for the Markdown Summary pipeline."""

from __future__ import annotations

import json
from typing import Any

try:
    from langchain_core.tools import tool as _lc_tool  # type: ignore[import-untyped]

    tool = _lc_tool  # type: ignore[assignment]
except ImportError:
    from pydantic import BaseModel, Field, create_model

    def tool(func=None, **_kwargs):  # type: ignore[no-untyped-def]
        """Fallback decorator that mimics langchain_core.tools.tool."""

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
            return fn

        if func is None:
            return _wrap
        return _wrap(func)


@tool
def create_markdown_summary(datasets_json: str, question: str, options_json: str = "{}") -> str:
    """Create a verified markdown summary from datasets.

    Args:
        datasets_json: JSON string of list[DataRef] — each with kind, name, data/url.
        question: Natural-language question or instruction for the summary.
        options_json: JSON string of SummaryOptions (max_rows, redact, locale, etc.).

    Returns:
        JSON string with markdown, facts, warnings, meta (or error_code/message on failure).
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

        if not question or not question.strip():
            raise ValueError("question must be a non-empty string")

        request: dict[str, Any] = {
            "datasets": datasets,
            "question": question,
            "options": options,
        }

        from markdown_summary_tool.engine.pipeline import run

        try:
            from markdown_summary_tool.llm.client import get_llm_client

            llm = get_llm_client()
        except ImportError:
            llm = None

        result = run(request, llm=llm)
        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as exc:
        return json.dumps(
            {"error_code": "summarization_failed", "message": str(exc), "details": {"exception": type(exc).__name__}},
            ensure_ascii=False,
        )


# DeepAgents registration exports
summarize_tool = create_markdown_summary

SUMMARIZE_TOOL_SPEC: dict[str, Any] = {
    "name": "create_markdown_summary",
    "description": (create_markdown_summary.description if hasattr(create_markdown_summary, "description") else create_markdown_summary.__doc__ or "Create a verified markdown summary from datasets."),
    "parameters": {
        "type": "object",
        "properties": {
            "datasets_json": {"type": "string", "description": "JSON string of list[DataRef]"},
            "question": {"type": "string", "description": "Natural-language question for the summary"},
            "options_json": {"type": "string", "description": "JSON string of SummaryOptions", "default": "{}"},
        },
        "required": ["datasets_json", "question"],
    },
}
