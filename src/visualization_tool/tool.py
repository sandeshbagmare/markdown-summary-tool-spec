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

            def _invoke(args: dict[str, Any]) -> Any:  # type: ignore[no-untyped-def]
                return fn(**args)

            fn.invoke = _invoke  # type: ignore[attr-defined]
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
        preamble = str(options.get("preamble", ""))
        postamble = str(options.get("postamble", ""))
        title = str(options.get("title", question[:60] if question else "Chart"))
        theme = str(options.get("theme", "light"))

        chart_data, warnings, facts, x_field, y_field = _compute_aggregates(
            datasets_json, question, resolved_type, options
        )

        chart_spec = _build_vega_spec(resolved_type, chart_data, x_field, y_field, width, height)

        # Self-contained HTML: preamble + chart + postamble
        html = _build_dashboard_html(
            [{"chart_spec": chart_spec, "meta": {"chart_type": resolved_type, "x_field": x_field, "y_field": y_field}, "title": title, "preamble": "", "postamble": ""}],
            layout="grid", preamble=preamble, postamble=postamble, title=title, theme=theme,
        ) if (preamble or postamble) else None
        # If no preamble/postamble, still build minimal HTML wrapper for self-containment
        if html is None:
            html = _build_dashboard_html(
                [{"chart_spec": chart_spec, "meta": {"chart_type": resolved_type}, "title": title, "preamble": "", "postamble": ""}],
                layout="grid", preamble="", postamble="", title=title, theme=theme,
            )

        result: dict[str, Any] = {
            "chart_spec": chart_spec,
            "html": html,
            "preamble": preamble,
            "postamble": postamble,
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


def _sanitize_fragment(fragment: str) -> str:
    """Sanitize HTML fragment via nh3 allowlist; fallback strips script/style."""
    if not fragment or not fragment.strip():
        return ""
    try:
        import nh3  # type: ignore[import-untyped]
        allowed = {"h1","h2","h3","h4","p","ul","ol","li","strong","em","a","span","div","section","header","footer","br","hr","code","pre","blockquote","table","thead","tbody","tr","th","td"}
        attrs = {"a": {"href","title"}, "span": {"class","style"}, "div": {"class","style"}, "th": {"align"}, "td": {"align"}}
        return nh3.clean(fragment, tags=allowed, attributes=attrs, link_rel=None)  # type: ignore[call-arg]
    except ImportError:
        import re as _re
        frag = _re.sub(r"<(script|style|iframe)[^>]*>.*?</\1>", "", fragment, flags=_re.DOTALL | _re.IGNORECASE)
        frag = _re.sub(r"\bon\w+\s*=\s*\"[^\"]*\"", "", frag, flags=_re.IGNORECASE)
        frag = _re.sub(r"javascript\s*:", "", frag, flags=_re.IGNORECASE)
        return frag


def _build_dashboard_html(
    charts: list[dict[str, Any]],
    layout: str,
    preamble: str,
    postamble: str,
    title: str = "Dashboard",
    theme: str = "light",
) -> str:
    import html as _html

    bg = "#ffffff" if theme != "dark" else "#1a1a1a"
    fg = "#1a1a1a" if theme != "dark" else "#e8e8e8"
    card_bg = "#ffffff" if theme != "dark" else "#2a2a2a"
    border = "#e0e0e0" if theme != "dark" else "#444"

    if layout == "row":
        container_style = "display:flex;flex-direction:row;flex-wrap:wrap;gap:16px;"
        item_style = f"flex:1 1 400px;min-width:300px;border:1px solid {border};border-radius:8px;padding:12px;background:{card_bg};"
    else:
        container_style = "display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:16px;"
        item_style = f"border:1px solid {border};border-radius:8px;padding:12px;background:{card_bg};"

    safe_title = _html.escape(title)
    pre_html = _sanitize_fragment(preamble)
    post_html = _sanitize_fragment(postamble)

    parts: list[str] = []
    parts.append('<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width,initial-scale=1">')
    parts.append(f"<title>{safe_title}</title>")
    parts.append(f"<style>*{{box-sizing:border-box}} body{{font-family:system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:24px;background:{bg};color:{fg}}} h1{{margin-top:0}} .preamble{{background:{'#f0f7ff' if theme!='dark' else '#1e3a5f'};border-left:4px solid #4a90d9;padding:12px 16px;border-radius:6px;margin-bottom:20px}} .postamble{{background:{'#f0faf0' if theme!='dark' else '#1e3a2e'};border-left:4px solid #7bc67e;padding:12px 16px;border-radius:6px;margin-top:20px}} .chart-card h3{{margin:0 0 8px 0}} .chart-preamble,.chart-postamble{{font-size:13px;color:#555;margin:6px 0}} .chart-meta{{font-size:11px;color:#888}}</style>")
    parts.append("</head><body>")
    parts.append(f"<header><h1>{safe_title}</h1></header>")
    if pre_html:
        parts.append(f'<section class="preamble">{pre_html}</section>')
    parts.append(f'<div class="dashboard-grid" style="{container_style}">')
    for idx, ch in enumerate(charts):
        t = _html.escape(str(ch.get("title", f"Chart {idx+1}")))
        c_pre = _sanitize_fragment(str(ch.get("preamble", "")))
        c_post = _sanitize_fragment(str(ch.get("postamble", "")))
        meta = ch.get("meta", {})
        chart_type = _html.escape(str(meta.get("chart_type", "")))
        spec_json = _html.escape(json.dumps(ch.get("chart_spec", {}), ensure_ascii=False))
        parts.append(f'<div class="chart-card" style="{item_style}">')
        parts.append(f"<h3>{t}</h3>")
        if c_pre:
            parts.append(f'<div class="chart-preamble">{c_pre}</div>')
        parts.append(f'<div class="chart-meta">{chart_type}</div>')
        parts.append(f'<div class="vega-chart" data-spec="{spec_json}" data-idx="{idx}" style="min-height:220px;display:flex;align-items:center;justify-content:center;background:#fafafa;border:1px dashed #ccc;border-radius:6px;color:#999;">Chart: {t}</div>')
        if c_post:
            parts.append(f'<div class="chart-postamble">{c_post}</div>')
        parts.append("</div>")
    parts.append("</div>")
    if post_html:
        parts.append(f'<section class="postamble">{post_html}</section>')
    # Vega-Embed loader for standalone HTML
    parts.append('<script src="https://cdn.jsdelivr.net/npm/vega@5"></script><script src="https://cdn.jsdelivr.net/npm/vega-lite@5"></script><script src="https://cdn.jsdelivr.net/npm/vega-embed@6"></script>')
    parts.append("<script>document.querySelectorAll('.vega-chart').forEach(function(el){try{var s=JSON.parse(el.getAttribute('data-spec')); if(s && s.data) vegaEmbed(el,s,{actions:false});}catch(e){}});</script>")
    parts.append("</body></html>")
    return "".join(parts)


@tool
def create_dashboard(datasets_json: str, question: str, charts_json: str = "[]", options_json: str = "{}") -> str:
    """Create a dashboard with multiple chart specifications from datasets.

    Args:
        datasets_json: JSON string of list[DataRef].
        question: Natural-language question describing the dashboard.
        charts_json: JSON array of {chart_type, title, question} — if empty, auto-generate 2-4 charts.
        options_json: JSON string of options (width, height, preamble, postamble, layout, max_charts).

    Returns:
        JSON string with dashboard (charts, layout, html), facts, warnings, meta.
    """
    try:
        if not question or not question.strip():
            raise ValueError("question must be a non-empty string")

        options: dict[str, Any] = {}
        if options_json and options_json.strip():
            parsed = json.loads(options_json)
            if isinstance(parsed, dict):
                options = parsed

        charts_cfg: list[dict[str, Any]] = []
        if charts_json and charts_json.strip():
            parsed_charts = json.loads(charts_json)
            if isinstance(parsed_charts, list):
                charts_cfg = [c for c in parsed_charts if isinstance(c, dict)]

        width = int(options.get("width", 400))
        height = int(options.get("height", 300))
        layout = str(options.get("layout", "grid"))
        if layout not in ("grid", "row"):
            layout = "grid"
        max_charts = int(options.get("max_charts", 4))
        max_charts = max(1, min(max_charts, 6))
        preamble = str(options.get("preamble", ""))
        postamble = str(options.get("postamble", ""))

        # Auto-generate charts if none provided
        if not charts_cfg:
            # Profile dataset to detect column types
            try:
                import asyncio

                from markdown_summary_tool.connectors.inline import InlineConnector
                from markdown_summary_tool.normalizer.normalize import normalize_rows
                from markdown_summary_tool.profiler.profile import profile_dataset

                datasets: list[dict[str, Any]] = json.loads(datasets_json) if datasets_json else []
                if isinstance(datasets, str):
                    datasets = json.loads(datasets)

                str_cols: list[str] = []
                num_cols: list[str] = []
                all_cols: list[str] = []

                if datasets:
                    async def _fetch_profile() -> dict[str, list[dict[str, Any]]]:
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
                                result[name] = []
                        return result

                    raw = asyncio.run(_fetch_profile())
                    # pick first non-empty
                    target_rows: list[dict[str, Any]] = []
                    target_name = ""
                    for n, r in raw.items():
                        if r:
                            target_rows = r
                            target_name = n
                            break
                    if target_rows:
                        normed, _w = normalize_rows(target_rows)
                        if normed:
                            profile = profile_dataset(target_name, normed)
                            str_cols = [c.name for c in profile.columns if c.inferred_type == "string"]
                            num_cols = [c.name for c in profile.columns if c.inferred_type in ("integer", "float")]
                            all_cols = [c.name for c in profile.columns]
            except Exception:
                pass

            candidates: list[dict[str, Any]] = []
            if str_cols and num_cols:
                candidates.append({"chart_type": "bar", "title": f"{num_cols[0]} by {str_cols[0]}", "question": question})
                candidates.append({"chart_type": "pie", "title": f"Distribution of {num_cols[0]} by {str_cols[0]}", "question": question})
            if len(num_cols) >= 2:
                candidates.append({"chart_type": "scatter", "title": f"{num_cols[1]} vs {num_cols[0]}", "question": question})
            if str_cols and num_cols:
                candidates.append({"chart_type": "line", "title": f"Trend of {num_cols[0]} by {str_cols[0]}", "question": question})
            elif num_cols and not str_cols:
                candidates.append({"chart_type": "bar", "title": f"{num_cols[0]} distribution", "question": question})
                if len(candidates) < 2:
                    candidates.append({"chart_type": "line", "title": f"Trend of {num_cols[0]}", "question": question})
            elif str_cols and not num_cols:
                candidates.append({"chart_type": "bar", "title": f"Count by {str_cols[0]}", "question": question})
                candidates.append({"chart_type": "pie", "title": f"Distribution by {str_cols[0]}", "question": question})

            if not candidates:
                candidates = [
                    {"chart_type": "bar", "title": "Overview", "question": question},
                    {"chart_type": "pie", "title": "Distribution", "question": question},
                ]

            # Ensure 2-4 charts when possible, respect max_charts
            limit = min(max_charts, max(2, min(4, len(candidates))) if len(candidates) >= 2 else len(candidates))
            # If candidates fewer than 2 but max_charts allows, keep as is; otherwise slice
            if len(candidates) > max_charts:
                limit = max_charts
            charts_cfg = candidates[:limit]
            # Ensure at least 2 if we have candidates and max_charts >=2
            if len(charts_cfg) == 1 and max_charts >= 2 and len(candidates) >= 1:
                # duplicate with different type if only one candidate
                extra_type = "line" if charts_cfg[0].get("chart_type") != "line" else "bar"
                charts_cfg.append({"chart_type": extra_type, "title": charts_cfg[0].get("title", "") + " (alt)", "question": question})

        # Respect max_charts for user-provided configs
        if len(charts_cfg) > max_charts:
            charts_cfg = charts_cfg[:max_charts]

        all_warnings: list[str] = []
        all_facts: list[dict[str, Any]] = []
        dashboard_charts: list[dict[str, Any]] = []

        for cfg in charts_cfg:
            c_type = str(cfg.get("chart_type", "auto"))
            c_title = str(cfg.get("title", c_type))
            c_question = str(cfg.get("question", question))
            c_preamble = str(cfg.get("preamble", ""))
            c_postamble = str(cfg.get("postamble", ""))
            resolved = _infer_chart_type(c_question, c_type)

            chart_data, warnings, facts, x_field, y_field = _compute_aggregates(
                datasets_json, c_question, resolved, options
            )
            chart_spec = _build_vega_spec(resolved, chart_data, x_field, y_field, width, height)

            all_warnings.extend(warnings)
            all_facts.extend(facts)

            dashboard_charts.append(
                {
                    "chart_spec": chart_spec,
                    "meta": {"chart_type": resolved, "x_field": x_field, "y_field": y_field, "row_count": len(chart_data)},
                    "title": c_title,
                    "preamble": c_preamble,
                    "postamble": c_postamble,
                }
            )

        title = str(options.get("title", question[:60] if question else "Dashboard"))
        theme = str(options.get("theme", "light"))
        html = _build_dashboard_html(dashboard_charts, layout, preamble, postamble, title=title, theme=theme)

        result: dict[str, Any] = {
            "dashboard": {"charts": dashboard_charts, "layout": layout, "html": html},
            "html": html,
            "preamble": preamble,
            "postamble": postamble,
            "facts": all_facts,
            "warnings": all_warnings,
            "meta": {"chart_count": len(dashboard_charts), "layout": layout, "width": width, "height": height},
        }
        return json.dumps(result, ensure_ascii=False, default=str)

    except Exception as exc:
        return json.dumps(
            {"error_code": "dashboard_failed", "message": str(exc), "details": {"exception": type(exc).__name__}},
            ensure_ascii=False,
        )


dashboard_tool = create_dashboard

DASHBOARD_TOOL_SPEC: dict[str, Any] = {
    "name": "create_dashboard",
    "description": (create_dashboard.description if hasattr(create_dashboard, "description") else create_dashboard.__doc__ or "Create a dashboard with multiple charts."),
    "parameters": {
        "type": "object",
        "properties": {
            "datasets_json": {"type": "string", "description": "JSON string of list[DataRef]"},
            "question": {"type": "string", "description": "Natural-language question for the dashboard"},
            "charts_json": {"type": "string", "description": "JSON array of {chart_type, title, question}", "default": "[]"},
            "options_json": {"type": "string", "description": "JSON string of options (width, height, preamble, postamble, layout, max_charts)", "default": "{}"},
        },
        "required": ["datasets_json", "question"],
    },
}
