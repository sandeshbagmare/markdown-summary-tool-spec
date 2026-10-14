"""FastAPI gateway for the Markdown Summary Tool."""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from markdown_summary_tool import __version__
from markdown_summary_tool.gateway.errors import AppError, ErrorCode, register_exception_handlers
from markdown_summary_tool.models.schemas import SummaryRequest, SummaryResponse

log = logging.getLogger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response


def create_app() -> FastAPI:
    app = FastAPI(
        title="Markdown Summary Tool",
        version=__version__,
        openapi_url="/v1/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    @app.get("/health", tags=["ops"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.post(
        "/v1/summarize",
        response_model=SummaryResponse,
        responses={
            422: {"description": "Validation error"},
            504: {"description": "Timeout"},
        },
        tags=["summarize"],
        summary="Generate a verified markdown summary",
    )
    async def summarize(req: SummaryRequest, request: Request) -> JSONResponse | SummaryResponse:
        timeout_ms = req.options.timeout_ms if req.options else 30_000
        timeout_s = timeout_ms / 1000

        try:
            from markdown_summary_tool.engine.pipeline import run as pipeline_run
        except ImportError as exc:
            raise AppError(
                ErrorCode.INTERNAL_ERROR,
                "Pipeline module not available.",
                status_code=500,
                details={"import_error": str(exc)},
            ) from exc

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(pipeline_run, req.model_dump(mode="json")),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise AppError(
                ErrorCode.TIMEOUT,
                f"Request exceeded timeout of {timeout_ms} ms.",
                status_code=504,
            ) from exc
        except AppError:
            raise
        except Exception as exc:
            msg = str(exc)
            lowered = msg.lower()
            if "too large" in lowered or "dataset_too_large" in lowered:
                raise AppError(ErrorCode.DATASET_TOO_LARGE, msg, status_code=413) from exc
            if "verification" in lowered:
                raise AppError(ErrorCode.VERIFICATION_FAILED, msg, status_code=422) from exc
            raise AppError(ErrorCode.INTERNAL_ERROR, "Internal error during summarization.", status_code=500) from exc

        if isinstance(result, dict):
            validated = SummaryResponse.model_validate(result)
            return JSONResponse(content=validated.model_dump(mode="json"))
        if isinstance(result, SummaryResponse):
            return result
        validated = SummaryResponse.model_validate(result)
        return validated

    return app


app = create_app()
