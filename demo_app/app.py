"""ChatGPT-style live demo — SSE streaming for both tools."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Tools Live Demo", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ── Presets ──────────────────────────────────────────────────────────────
PRESETS: list[dict[str, Any]] = [
    {
        "id": "orders",
        "label": "Orders — totals & averages by region",
        "question": "Summarize total and average order amount by region",
        "tool": "markdown",
        "datasets": [
            {
                "kind": "inline_json",
                "name": "orders",
                "data": [
                    {"customer": "Alice", "amount": 120.5, "region": "East"},
                    {"customer": "Bob", "amount": 80.0, "region": "West"},
                    {"customer": "Alice", "amount": 200.0, "region": "East"},
                    {"customer": "Carol", "amount": 50.0, "region": "West"},
                    {"customer": "Dave", "amount": 310.0, "region": "East"},
                    {"customer": "Eve", "amount": 95.0, "region": "North"},
                ],
            }
        ],
    },
    {
        "id": "sales-trend",
        "label": "Sales — monthly trend (line chart)",
        "question": "Show sales trend over time as a line chart",
        "tool": "visualization",
        "datasets": [
            {
                "kind": "inline_json",
                "name": "sales",
                "data": [
                    {"month": "Jan", "revenue": 12000, "orders": 120},
                    {"month": "Feb", "revenue": 15000, "orders": 140},
                    {"month": "Mar", "revenue": 11000, "orders": 100},
                    {"month": "Apr", "revenue": 18000, "orders": 170},
                    {"month": "May", "revenue": 22000, "orders": 210},
                    {"month": "Jun", "revenue": 19000, "orders": 180},
                ],
            }
        ],
    },
    {
        "id": "revenue-share",
        "label": "Revenue — share by product (pie chart)",
        "question": "Show revenue distribution by product as a pie chart",
        "tool": "visualization",
        "datasets": [
            {
                "kind": "inline_json",
                "name": "products",
                "data": [
                    {"product": "Widget A", "revenue": 45000},
                    {"product": "Widget B", "revenue": 32000},
                    {"product": "Widget C", "revenue": 18000},
                    {"product": "Widget D", "revenue": 9000},
                ],
            }
        ],
    },
    {
        "id": "group-counts",
        "label": "Orders — group counts & top regions",
        "question": "How many orders per region and which region has the most orders?",
        "tool": "markdown",
        "datasets": [
            {
                "kind": "inline_json",
                "name": "orders",
                "data": [
                    {"customer": "Alice", "amount": 120.5, "region": "East"},
                    {"customer": "Bob", "amount": 80.0, "region": "West"},
                    {"customer": "Alice", "amount": 200.0, "region": "East"},
                    {"customer": "Carol", "amount": 50.0, "region": "West"},
                    {"customer": "Dave", "amount": 310.0, "region": "East"},
                    {"customer": "Eve", "amount": 95.0, "region": "North"},
                    {"customer": "Frank", "amount": 70.0, "region": "West"},
                ],
            }
        ],
    },
    {
        "id": "scatter",
        "label": "Spend vs Orders — correlation (scatter)",
        "question": "Show correlation between amount and quantity as a scatter plot",
        "tool": "visualization",
        "datasets": [
            {
                "kind": "inline_json",
                "name": "purchases",
                "data": [
                    {"amount": 120, "quantity": 2},
                    {"amount": 80, "quantity": 1},
                    {"amount": 200, "quantity": 4},
                    {"amount": 50, "quantity": 1},
                    {"amount": 310, "quantity": 6},
                    {"amount": 95, "quantity": 2},
                    {"amount": 150, "quantity": 3},
                ],
            }
        ],
    },
    {
        "id": "bar-simple",
        "label": "Revenue — by region (bar chart)",
        "question": "Bar chart of total revenue by region",
        "tool": "visualization",
        "datasets": [
            {
                "kind": "inline_json",
                "name": "orders",
                "data": [
                    {"customer": "Alice", "amount": 120.5, "region": "East"},
                    {"customer": "Bob", "amount": 80.0, "region": "West"},
                    {"customer": "Alice", "amount": 200.0, "region": "East"},
                    {"customer": "Carol", "amount": 50.0, "region": "West"},
                    {"customer": "Dave", "amount": 310.0, "region": "East"},
                    {"customer": "Eve", "amount": 95.0, "region": "North"},
                ],
            }
        ],
    },
]


class ChatRequest(BaseModel):
    question: str
    datasets: list[dict[str, Any]]
    tool: str = "auto"  # auto | markdown | visualization
    chart_type: str = "auto"
    options: dict[str, Any] = {}


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _infer_tool(question: str, tool: str) -> str:
    if tool in ("markdown", "visualization"):
        return tool
    q = question.lower()
    if any(k in q for k in ("chart", "graph", "plot", "visualize", "bar", "line", "pie", "scatter", "trend", "distribution")):
        return "visualization"
    return "markdown"


async def _stream_markdown(req: ChatRequest) -> AsyncGenerator[str, None]:
    t0 = time.monotonic()
    # Step events — mimic pipeline stages
    yield _sse("status", {"stage": "fetch", "label": "Fetching datasets…"})
    await asyncio.sleep(0.15)
    yield _sse("status", {"stage": "normalize", "label": "Normalizing rows…"})
    await asyncio.sleep(0.1)
    yield _sse("status", {"stage": "profile", "label": "Profiling columns…"})
    await asyncio.sleep(0.1)
    yield _sse("status", {"stage": "compute", "label": "Computing facts (DuckDB)…"})
    await asyncio.sleep(0.1)

    # Actual pipeline call (sync, run in thread)
    def _run():
        from markdown_summary_tool.engine.pipeline import run

        return run({"datasets": req.datasets, "question": req.question, "options": req.options})

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        yield _sse("error", {"message": str(exc), "type": type(exc).__name__})
        yield _sse("done", {"elapsed_ms": int((time.monotonic() - t0) * 1000)})
        return

    yield _sse("status", {"stage": "llm", "label": "Verbalizing facts (LLM)…"})
    await asyncio.sleep(0.08)
    yield _sse("status", {"stage": "verify", "label": "Verifying numbers…"})
    await asyncio.sleep(0.08)

    # Stream markdown token-by-token (word chunks) for ChatGPT feel
    md: str = result.get("markdown", "")
    words = md.split(" ")
    buf = ""
    for i, w in enumerate(words):
        buf += w + (" " if i < len(words) - 1 else "")
        if i % 6 == 0 or i == len(words) - 1:
            yield _sse("markdown_chunk", {"text": buf})
            buf = ""
            await asyncio.sleep(0.02)
    if buf:
        yield _sse("markdown_chunk", {"text": buf})

    yield _sse("facts", {"facts": result.get("facts", [])})
    yield _sse("warnings", {"warnings": result.get("warnings", [])})
    yield _sse("meta", {"meta": result.get("meta", {})})
    yield _sse("done", {"elapsed_ms": int((time.monotonic() - t0) * 1000)})


async def _stream_visualization(req: ChatRequest) -> AsyncGenerator[str, None]:
    t0 = time.monotonic()
    yield _sse("status", {"stage": "fetch", "label": "Fetching datasets…"})
    await asyncio.sleep(0.12)
    yield _sse("status", {"stage": "aggregate", "label": "Aggregating (DuckDB)…"})
    await asyncio.sleep(0.1)
    yield _sse("status", {"stage": "spec", "label": "Building Vega-Lite spec…"})
    await asyncio.sleep(0.08)

    def _run():
        from visualization_tool.tool import create_visualization

        raw = create_visualization.invoke(
            {
                "datasets_json": json.dumps(req.datasets),
                "question": req.question,
                "chart_type": req.chart_type,
                "options_json": json.dumps(req.options),
            }
        )
        return json.loads(raw)

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        yield _sse("error", {"message": str(exc), "type": type(exc).__name__})
        yield _sse("done", {"elapsed_ms": int((time.monotonic() - t0) * 1000)})
        return

    if "error_code" in result:
        yield _sse("error", {"message": result.get("message", "visualization failed"), "details": result})
        yield _sse("done", {"elapsed_ms": int((time.monotonic() - t0) * 1000)})
        return

    yield _sse("chart", {"chart_spec": result.get("chart_spec"), "meta": result.get("meta", {})})
    yield _sse("facts", {"facts": result.get("facts", [])})
    yield _sse("warnings", {"warnings": result.get("warnings", [])})
    yield _sse("done", {"elapsed_ms": int((time.monotonic() - t0) * 1000)})


@app.get("/api/presets")
async def presets() -> JSONResponse:
    return JSONResponse(PRESETS)


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    chosen = _infer_tool(req.question, req.tool)

    async def gen() -> AsyncGenerator[str, None]:
        yield _sse("tool", {"tool": chosen, "question": req.question})
        if chosen == "visualization":
            async for chunk in _stream_visualization(req):
                if await request.is_disconnected():
                    break
                yield chunk
        else:
            async for chunk in _stream_markdown(req):
                if await request.is_disconnected():
                    break
                yield chunk

    from fastapi.responses import StreamingResponse

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/health")
async def health():
    return {"status": "ok"}


# Static — serve index.html at /
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html)
