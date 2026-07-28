"""Link creation endpoint."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import CodeGenerationError, create_link, get_session
from app.ratelimit import SlidingWindowLimiter, client_ip
from app.schemas import ErrorResponse, ShortenRequest, ShortenResponse
from app.validate import InvalidURL, validate_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["links"])

_settings = get_settings()
limiter = SlidingWindowLimiter(
    max_requests=_settings.rate_limit_requests,
    window_seconds=_settings.rate_limit_window_seconds,
)


@router.post(
    "/shorten",
    response_model=ShortenResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        400: {"model": ErrorResponse, "description": "URL rejected by validation"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
)
async def shorten(
    payload: ShortenRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ShortenResponse:
    settings = get_settings()
    ip = client_ip(request, settings.trusted_proxy_hops)

    allowed, retry_after = limiter.check(ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded; slow down.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        target_url = validate_url(payload.url)
    except InvalidURL as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    try:
        link = await create_link(session, target_url, client_ip=ip)
    except CodeGenerationError:
        logger.exception("code allocation failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not allocate a short code; please retry.",
        ) from None

    logger.info("created link code=%s", link.code)

    return ShortenResponse(
        code=link.code,
        short_url=f"{settings.base_url}/{link.code}",
        target_url=link.target_url,
        created_at=link.created_at,
    )
