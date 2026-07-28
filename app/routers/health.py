"""Liveness and readiness probes.

/healthz is deliberately dependency-free. If it checked the database, a Postgres
blip would fail the App Platform health check and trigger a restart loop that
cannot possibly fix the problem. /readyz is the one that touches the database,
for use by deploy gates and monitoring.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/readyz", response_model=HealthResponse)
async def readyz(
    response: Response, session: AsyncSession = Depends(get_session)
) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="database unavailable")

    return HealthResponse(status="ok")
