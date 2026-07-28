"""Database engine, session lifecycle, and link persistence."""

from collections.abc import AsyncIterator

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import select

from app.config import get_settings
from app.models import Link
from app.shortcode import generate_code

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

# Bounded so a misconfigured code length or an exhausted keyspace surfaces as a
# 500 instead of spinning forever.
MAX_CODE_ATTEMPTS = 5


class CodeGenerationError(RuntimeError):
    """Raised when a unique code could not be found within the retry budget."""


def _is_code_collision(exc: IntegrityError) -> bool:
    """True only for a uniqueness violation on links.code.

    Postgres reports SQLSTATE 23505 for unique violations; SQLite has no such
    code, so its message is matched instead. Any other integrity error (a NOT
    NULL breach from a schema drift, say) is a genuine bug and must propagate.
    """
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if sqlstate is not None:
        return sqlstate == "23505" and "code" in str(exc.orig).lower()

    message = str(exc.orig).lower()
    return "unique" in message and "code" in message


def init_engine(database_url: str | None = None, **engine_kwargs) -> AsyncEngine:
    global _engine, _sessionmaker

    settings = get_settings()
    url = database_url or settings.database_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")

    kwargs = {"pool_pre_ping": True, "echo": False}
    # SQLite (used by the test suite) rejects pool sizing arguments.
    if not url.startswith("sqlite"):
        kwargs["pool_size"] = settings.db_pool_size
        kwargs["max_overflow"] = settings.db_max_overflow
    kwargs.update(engine_kwargs)

    _engine = create_async_engine(url, **kwargs)
    _sessionmaker = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("engine not initialised; call init_engine() first")
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session scoped to one request."""
    if _sessionmaker is None:
        raise RuntimeError("engine not initialised; call init_engine() first")
    async with _sessionmaker() as session:
        yield session


async def create_link(
    session: AsyncSession, target_url: str, client_ip: str | None = None
) -> Link:
    """Insert a link under a fresh random code, retrying on collision.

    Each attempt runs in a savepoint so that an IntegrityError from a losing
    race does not poison the surrounding transaction.
    """
    for _ in range(MAX_CODE_ATTEMPTS):
        link = Link(
            code=generate_code(), target_url=target_url, created_by_ip=client_ip
        )
        try:
            async with session.begin_nested():
                session.add(link)
            await session.commit()
            return link
        except IntegrityError as exc:
            await session.rollback()
            # Only a uniqueness violation on the code is a collision worth
            # retrying. Retrying anything else would silently burn the budget
            # and report a bogus "no codes available" to the caller.
            if not _is_code_collision(exc):
                raise
            continue

    raise CodeGenerationError(
        f"could not allocate a unique code in {MAX_CODE_ATTEMPTS} attempts"
    )


async def get_link_by_code(session: AsyncSession, code: str) -> Link | None:
    result = await session.execute(select(Link).where(Link.code == code))
    return result.scalar_one_or_none()
