"""Redirect endpoint — the hot path.

This router owns a catch-all route and must be registered last in main.py, or
it will shadow /healthz, /api/* and the docs.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_link_by_code, get_session
from app.schemas import ErrorResponse
from app.shortcode import is_valid_code

logger = logging.getLogger(__name__)

router = APIRouter(tags=["redirect"])


@router.get(
    "/{code}",
    status_code=status.HTTP_302_FOUND,
    responses={
        302: {"description": "Redirect to the target URL"},
        404: {"model": ErrorResponse, "description": "Unknown or malformed code"},
    },
    response_class=RedirectResponse,
)
async def redirect(
    code: str, session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    # Reject anything that cannot be a code before spending a database round
    # trip on it — scanners generate a lot of this traffic.
    if not is_valid_code(code):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found"
        )

    link = await get_link_by_code(session, code)
    if link is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Short link not found"
        )

    # 302 rather than 301 on purpose. A 301 is cached by the browser
    # indefinitely, which would make the destination impossible to change or
    # disable later — the response to an abusive link has to be immediate.
    # no-store keeps intermediary caches from doing the same thing.
    return RedirectResponse(
        url=link.target_url,
        status_code=status.HTTP_302_FOUND,
        headers={"Cache-Control": "no-store, max-age=0", "Referrer-Policy": "no-referrer"},
    )
