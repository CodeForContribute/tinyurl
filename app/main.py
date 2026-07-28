"""Application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import dispose_engine, init_engine
from app.routers import health, redirect, shorten

logger = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    init_engine()
    logger.info("startup complete")
    try:
        yield
    finally:
        await dispose_engine()
        logger.info("shutdown complete")


def create_app(lifespan_handler=lifespan) -> FastAPI:
    app = FastAPI(
        title="tinyurl",
        description="A URL shortener.",
        version="1.0.0",
        lifespan=lifespan_handler,
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Never leak a traceback to the caller; log it with the path instead.
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500, content={"detail": "Internal server error"}
        )

    app.include_router(health.router)
    app.include_router(shorten.router)
    # Must come last: it owns the /{code} catch-all.
    app.include_router(redirect.router)

    return app


app = create_app()
