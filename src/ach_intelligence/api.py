import hmac
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .adapters import DependencyUnavailable, MoovAdapter
from .config import Settings
from .db import AuditRow, EntryRow, FileRow, make_engine, migrate, transaction
from .intelligence import interpret_return
from .schemas import ReturnRequest, ReviewRequest
from .service import NotFound, ReviewConflict, explain_exception, get_file, ingest, review, summary

logger = logging.getLogger("ach.api")


class BodyLimit:
    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        count = 0

        async def limited_receive() -> Message:
            nonlocal count
            message = await receive()
            count += len(message.get("body", b""))
            if count > self.limit:
                raise HTTPException(413, "Request exceeds the configured upload limit")
            return message

        await self.app(scope, limited_receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    engine = make_engine(config.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        migrate(engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="ACH Exception Intelligence",
        version="1.0.0",
        lifespan=lifespan,
        description="Synthetic PPD/CCD evidence and analyst review. No payment execution.",
    )
    app.state.engine, app.state.settings = engine, config
    app.add_middleware(BodyLimit, limit=config.max_upload_bytes + 16384)

    @app.middleware("http")
    async def authorize(request: Request, call_next: Any) -> Any:
        if config.api_token and request.url.path != "/health":
            provided = request.headers.get("authorization", "").removeprefix("Bearer ")
            if not hmac.compare_digest(provided, config.api_token):
                return JSONResponse({"detail": "Bearer token required"}, status_code=401)
        response = await call_next(request)
        # No body, query strings, accounts, tokens or model prompts in logs.
        logger.info(
            json.dumps({"event": "http", "method": request.method, "status": response.status_code})
        )
        return response

    @app.exception_handler(NotFound)
    async def missing(_: Request, error: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=404)

    @app.exception_handler(ReviewConflict)
    async def conflict(_: Request, error: ReviewConflict) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=409)

    @app.exception_handler(DependencyUnavailable)
    async def dependency(_: Request, error: DependencyUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(error)}, status_code=503)

    @app.get("/health")
    def health() -> JSONResponse:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False
        moov_ok = not config.moov_url or MoovAdapter(config.moov_url).ready()
        return JSONResponse(
            {
                "status": "ready" if db_ok and moov_ok else "unavailable",
                "database": db_ok,
                "moov": moov_ok if config.moov_url else "disabled",
                "mode": "moov" if config.moov_url else "offline",
            },
            status_code=200 if db_ok and moov_ok else 503,
        )

    @app.post("/api/v1/ach/files", status_code=201)
    async def upload(
        file: Annotated[UploadFile, File()], x_synthetic_data: Annotated[str, Header()] = ""
    ) -> dict[str, Any]:
        if x_synthetic_data.lower() != "true":
            raise HTTPException(400, "Set X-Synthetic-Data: true; synthetic data only")
        if file.content_type not in {"text/plain", "application/octet-stream"}:
            raise HTTPException(415, "Use text/plain or application/octet-stream")
        data = await file.read(config.max_upload_bytes + 1)
        await file.close()
        if len(data) > config.max_upload_bytes:
            raise HTTPException(413, "File exceeds the configured upload limit")
        try:
            data.decode("ascii")
        except UnicodeDecodeError as exc:
            raise HTTPException(422, "ACH records must use ASCII encoding") from exc
        return await run_in_threadpool(ingest, engine, config, data)

    @app.get("/api/v1/ach/files")
    def files() -> list[dict[str, Any]]:
        with transaction(engine) as session:
            return [
                summary(session, row)
                for row in session.scalars(
                    select(FileRow).order_by(FileRow.created_at.desc()).limit(100)
                )
            ]

    @app.get("/api/v1/ach/files/{file_id}")
    def file_detail(file_id: UUID) -> dict[str, Any]:
        with transaction(engine) as session:
            return summary(session, get_file(session, str(file_id)))

    @app.get("/api/v1/ach/files/{file_id}/exceptions")
    def exceptions(file_id: UUID) -> list[dict[str, Any]]:
        return list(file_detail(file_id)["exceptions"])

    @app.get("/api/v1/ach/files/{file_id}/entries")
    def entries(file_id: UUID) -> list[dict[str, Any]]:
        with transaction(engine) as session:
            get_file(session, str(file_id))
            return [
                {"id": row.id, **row.data}
                for row in session.scalars(select(EntryRow).where(EntryRow.file_id == str(file_id)))
            ]

    @app.get("/api/v1/ach/files/{file_id}/audit")
    def audit(file_id: UUID) -> list[dict[str, Any]]:
        with transaction(engine) as session:
            get_file(session, str(file_id))
            return [
                {
                    "id": a.id,
                    "exception_id": a.exception_id,
                    "action": a.action,
                    "actor": a.actor,
                    "data": a.data,
                    "created_at": a.created_at,
                }
                for a in session.scalars(
                    select(AuditRow)
                    .where(AuditRow.file_id == str(file_id))
                    .order_by(AuditRow.created_at, AuditRow.id)
                )
            ]

    @app.post("/api/v1/ach/exceptions/{exception_id}/explain")
    def explanation(exception_id: UUID) -> dict[str, Any]:
        return explain_exception(engine, config, str(exception_id))

    @app.post("/api/v1/ach/exceptions/{exception_id}/review")
    def disposition(exception_id: UUID, request: ReviewRequest) -> dict[str, Any]:
        return review(engine, str(exception_id), request)

    @app.post("/api/v1/ach/returns/interpret")
    def returns(request: ReturnRequest) -> dict[str, Any]:
        return interpret_return(request.code)

    return app


app = create_app()
