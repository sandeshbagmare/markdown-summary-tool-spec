"""DeepAgent-compatible visualization tool — DuckDB aggregates + Vega-Lite spec."""

from __future__ import annotations

import json
import re
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
            return fn

        if func is None:
            return _wrap
        return _wrap(func)


def _infer_chart_type(question: str, chart_type: str) -> str:
    if chart_type != "auto":
        return chart_type
    q = question.lower()
    if any(k in q for k in ("trend", "over time", "time series", "evolution")):
        return "line"
    if any(k in q for k in ("distribution", "share", "proportion", "pie")):
        return "pie"
    if any(k in q for k in ("scatter", "correlation", "relationship")):
        return "scatter"
    return "bar"


def _build_vega_spec(
    chart_type: str,
    data: list[dict[str, Any]],
    x_field: str,
    y_field: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "width": width,
        "height": height,
        "data": {"values": data},
    }
    if chart_type == "bar":
        base["mark"] = "bar"
        base["encoding"] = {
            "x": {"field": x_field, "type": "nominal", "axis": {"labelAngle": -30}},
            "y": {"field": y_field, "type": "quantitative"},
            "tooltip": [{"field": x_field}, {"field": y_field, "type": "quantitative"}],
        }
    elif chart_type == "line":
        base["mark"] = {"type": "line", "point": True}
        base["encoding"] = {
            "x": {"field": x_field, "type": "nominal"},
            "y": {"field": y_field, "type": "quantitative"},
            "tooltip": [{"field": x_field}, {"field": y_field, "type": "quantitative"}],
        }
    elif chart_type == "pie":
        base["mark"] = "arc"
        base["encoding"] = {
            "theta": {"field": y_field, "type": "quantitative"},
            "color": {"field": x_field, "type": "nominal"},
            "tooltip": [{"field": x_field}, {"field": y_field, "type": "quantitative"}],
        }
    elif chart_type == "scatter":
        base["mark"] = "point"
        base["encoding"] = {
            "x": {"field": x_field, "type": "quantitative"},
            "y": {"field": y_field, "type": "quantitative"},
            "tooltip": [{"field": x_field, "type": "quantitative"}, {"field": y_field, "type": "quantitative"}],
        }
    else:
        base["mark"] = "bar"
        base["encoding"] = {
            "x": {"field": x_field, "type": "nominal"},
            "y": {"field": y_field, "type": "quantitative"},
        }
    return base


def _compute_aggregates(
    datasets_json: str,
    question: str,
    chart_type: str,
    options: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], str, str]:
    import asyncio

    from markdown_summary_tool.connectors.inline import InlineConnector
    from markdown_summary_tool.engine.duckdb_engine import DuckDBEngine
    from markdown_summary_tool.normalizer.normalize import normalize_rows
    from markdown_summary_tool.profiler.profile import profile_dataset

    async def _fetch(datasets: list[dict[str, Any]]) -> tuple[dict[str, list[dict[str, Any]]], list[str]]:
        warnings: list[str] = []
        result: dict[str, list[dict[str, Any]]] = {}
        for ds in datasets:
            kind = ds.get("kind", "")
            name = ds.get("name", "dataset")
            if kind in ("inline_json", "inline_csv"):
                conn = InlineConnector(ds)
                rows = await conn.fetch()
                result[name] = rows
            elif kind == "url":
                from markdown_summary_tool.connectors.http import HttpConnector

                conn = HttpConnector(ds)
                rows = await conn.fetch()
                result[name] = rows
            else:
                warnings.append(f"unknown dataset kind '{kind}' for '{name}' — skipped")
                result[name] = []
        return result, warnings

    datasets: list[dict[str, Any]] = json.loads(datasets_json) if datasets_json else []
    if isinstance(datasets, str):
        datasets = json.loads(datasets)
    if not datasets:
        return [], ["no datasets provided"], [], "category", "value"

    raw, fetch_warnings = asyncio.run(_fetch(datasets))
    warnings: list[str] = list(fetch_warnings)

    max_rows = options.get("max_rows")
    normalized: dict[str, list[dict[str, Any]]] = {}
    for name, rows in raw.items():
        if max_rows is not None and len(rows) > max_rows:
            warnings.append(f"dataset '{name}' truncated from {len(rows)} to {max_rows} rows")
            rows = rows[:max_rows]
        normed, w = normalize_rows(rows)
        normalized[name] = normed
        warnings.extend(w)

    # Pick first non-empty dataset
    target_name: str | None = None
    target_rows: list[dict[str, Any]] = []
    for n, r in normalized.items():
        if r:
            target_name = n
            target_rows = r
            break
    if target_name is None:
        return [], warnings + ["all datasets empty"], [], "category", "value"

    profile = profile_dataset(target_name, target_rows)

    # Heuristic: pick first string column as x, first numeric as y; fallback to count aggregation
    str_cols = [c.name for c in profile.columns if c.inferred_type == "string"]
    num_cols = [c.name for c in profile.columns if c.inferred_type in ("integer", "float")]
    all_cols = [c.name for c in profile.columns]

    x_field = str_cols[0] if str_cols else (all_cols[0] if all_cols else "category")
    y_field = num_cols[0] if num_cols else "count"

    # Try DuckDB group-by if we have both dimensions
    facts: list[dict[str, Any]] = []
    chart_data: list[dict[str, Any]] = []

    engine = DuckDBEngine()
    try:
        engine.register(target_name, target_rows)
        safe = re.sub(r"[^A-Za-z0-9_]", "_", target_name)
        # Use engine's group_by for bar/pie, raw rows for scatter/line
        if chart_type in ("bar", "pie") and str_cols and num_cols:
            # Aggregate sum of numeric grouped by string
            agg = f"SUM(\"{y_field}\") AS \"{y_field}\""
            rows = engine.group_by(target_name, by=x_field, agg=agg, order_by=f'"{y_field}" DESC', limit=20)
            chart_data = rows
            facts.append({"id": "agg_rows", "kind": "group_sum", "value": len(rows), "formatted": str(len(rows))})
        elif chart_type == "scatter" and len(num_cols) >= 2:
            x_field = num_cols[0]
            y_field = num_cols[1]
            chart_data = [{x_field: r.get(x_field), y_field: r.get(y_field)} for r in target_rows[:100]]
        else:
            # Fallback: count by x_field
            if str_cols:
                rows = engine.group_by(target_name, by=x_field, agg="COUNT(*) AS count", order_by="count DESC", limit=20)
                chart_data = rows
                y_field = "count"
            else:
                chart_data = target_rows[:20]
                y_field = num_cols[0] if num_cols else all_cols[0] if all_cols else "value"
    except Exception as exc:
        warnings.append(f"aggregation failed: {exc}")
        chart_data = target_rows[:20]
    finally:
        engine.close()

    if not chart_data:
        warnings.append("no chart data produced")

    return chart_data, warnings, facts, x_field, y_field


@tool
def create_visualization(datasets_json: str, question: str, chart_type: str = "auto", options_json: str = "{}") -> str:
    """Create a chart specification from datasets.

    Args:
        datasets_json: JSON string of list[DataRef].
        question: Natural-language question describing the desired visualization.
        chart_type: Chart type — auto, bar, line, pie, scatter, table.
        options_json: JSON string of VisualizationOptions (width, height, max_rows).

    Returns:
        JSON string with chart_spec (Vega-Lite), facts, warnings, meta.
    """
    try:
        if not question or not question.strip():
            raise ValueError("question must be a non-empty string")

        options: dict[str, Any] = {}
        if options_json and options_json.strip():
            parsed = json.loads(options_json)
            if isinstance(parsed, dict):
                options = parsed

        resolved_type = _infer_chart_type(question, chart_type)
        width = int(options.get("width", 400))
        height = int(options.get("height", 300))

        chart_data, warnings, facts, x_field, y_field = _compute_aggregates(
            datasets_json, question, resolved_type, options
        )

        chart_spec = _build_vega_spec(resolved_type, chart_data, x_field, y_field, width, height)

        result: dict[str, Any] = {
            "chart_spec": chart_spec,
            "facts": facts,
            "warnings": warnings,
            "meta": {"chart_type": resolved_type, "x_field": x_field, "y_field": y_field, "row_count": len(chart_data)},
        }
        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as exc:
        return json.dumps(
            {"error_code": "visualization_failed", "message": str(exc), "details": {"exception": type(exc).__name__}},
            ensure_ascii=False,
        )


# DeepAgents registration exports
visualization_tool = create_visualization

VISUALIZATION_TOOL_SPEC: dict[str, Any] = {
    "name": "create_visualization",
    "description": (create_visualization.description if hasattr(create_visualization, "description") else create_visualization.__doc__ or "Create a chart specification from datasets."),
    "parameters": {
        "type": "object",
        "properties": {
            "datasets_json": {"type": "string", "description": "JSON string of list[DataRef]"},
            "question": {"type": "string", "description": "Natural-language question for the visualization"},
            "chart_type": {"type": "string", "description": "Chart type", "default": "auto"},
            "options_json": {"type": "string", "description": "JSON string of VisualizationOptions", "default": "{}"},
        },
        "required": ["datasets_json", "question"],
    },
}
