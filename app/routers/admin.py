"""Administrative endpoints — abuse response.

Gated on a shared admin token rather than a user account system, which does not
exist yet. That is deliberately the smallest thing that makes the endpoint safe
to expose: without it, anyone could disable anyone else's links, which would be
worse than shipping no delete endpoint at all.
"""

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import disable_link, get_session
from app.ratelimit import SlidingWindowLimiter, client_ip
from app.schemas import DisableLinkResponse, ErrorResponse
from app.shortcode import is_valid_code

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["admin"])

# Tighter than the public limiter: this exists to make brute-forcing the admin
# token impractical, not to shape ordinary traffic.
admin_limiter = SlidingWindowLimiter(max_requests=10, window_seconds=60)


async def require_admin(
    request: Request,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
) -> None:
    """Authorise an admin request, or raise.

    Fails closed: with no ADMIN_TOKEN configured the endpoint is unavailable
    rather than unprotected.
    """
    settings = get_settings()

    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin endpoints are disabled; ADMIN_TOKEN is not configured.",
        )

    ip = client_ip(request, settings.trusted_proxy_hops)
    allowed, retry_after = admin_limiter.check(ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded.",
            headers={"Retry-After": str(retry_after)},
        )

    # compare_digest so a wrong token cannot be recovered by timing the reply.
    if x_admin_token is None or not secrets.compare_digest(
        x_admin_token, settings.admin_token
    ):
        logger.warning("rejected admin request from ip=%s", ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin token.",
            headers={"WWW-Authenticate": "X-Admin-Token"},
        )


@router.delete(
    "/links/{code}",
    response_model=DisableLinkResponse,
    dependencies=[Depends(require_admin)],
    responses={
        401: {"model": ErrorResponse, "description": "Invalid or missing admin token"},
        404: {"model": ErrorResponse, "description": "Unknown code"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
        503: {"model": ErrorResponse, "description": "ADMIN_TOKEN not configured"},
    },
)
async def delete_link(
    code: str,
    reason: str | None = Query(
        default=None,
        max_length=500,
        description="Why the link was disabled; retained for audit.",
    ),
    session: AsyncSession = Depends(get_session),
) -> DisableLinkResponse:
    """Disable a short link. Idempotent — disabling twice is not an error.

    `reason` is a query parameter rather than a body: DELETE-with-a-body is
    unevenly supported across HTTP clients and proxies, and this endpoint needs
    to be usable from plain curl during an incident.
    """
    if not is_valid_code(code):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found"
        )

    link = await disable_link(session, code, reason=reason)

    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found"
        )

    logger.info("disabled link code=%s reason=%s", link.code, link.disabled_reason)

    return DisableLinkResponse(
        code=link.code,
        target_url=link.target_url,
        disabled_at=link.disabled_at,
        disabled_reason=link.disabled_reason,
    )
