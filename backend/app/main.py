import logging

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.recovery_page import router as recovery_page
from app.api.v1.routers.routes import health, router
from app.core.config import settings
from app.core.errors import AppError
from app.core.middleware import RequestMiddleware


def create_app() -> FastAPI:
    cfg = settings()
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer()
            if cfg.environment == "local"
            else structlog.processors.JSONRenderer(),
        ]
    )
    production = cfg.environment == "production"
    app = FastAPI(
        title="Territory Run",
        version="0.3.0",
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=cfg.allowed_hosts, www_redirect=False)
    app.add_middleware(
        RequestMiddleware,
        max_bytes=cfg.max_body_bytes,
        body_timeout_seconds=cfg.body_timeout_seconds,
    )
    app.include_router(router, prefix="/api/v1")
    app.include_router(health)
    app.include_router(recovery_page)

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        return JSONResponse(
            {"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
            exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Pydantic's raw errors include input values, which can contain passwords or GPS history.
        details = [
            {"field": ".".join(str(x) for x in e["loc"]), "type": e["type"]} for e in exc.errors()
        ]
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Check the submitted fields.",
                    "details": {"fields": details},
                }
            },
            422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(
            {"error": {"code": "http_error", "message": str(exc.detail), "details": {}}},
            exc.status_code,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        structlog.get_logger().error(
            "integrity_error", path=getattr(request.scope.get("route"), "path", "<unmatched>")
        )
        return JSONResponse(
            {
                "error": {
                    "code": "conflict",
                    "message": "This change conflicts with existing data. Please retry.",
                    "details": {},
                }
            },
            409,
        )

    @app.exception_handler(OperationalError)
    @app.exception_handler(PoolTimeoutError)
    async def database_unavailable(request: Request, exc: Exception):
        structlog.get_logger().error(
            "database_unavailable",
            path=getattr(request.scope.get("route"), "path", "<unmatched>"),
            exception_type=type(exc).__name__,
        )
        return JSONResponse(
            {
                "error": {
                    "code": "service_unavailable",
                    "message": "The server is busy or unavailable. Please retry.",
                    "details": {},
                }
            },
            503,
            headers={"Retry-After": "5"},
        )

    return app


app = create_app()
