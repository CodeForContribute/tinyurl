"""Test fixtures.

Tests run against in-memory SQLite so the suite needs no external services. The
schema is created from the ORM metadata rather than by running Alembic, since
the migration targets Postgres types.
"""

import os

import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("BASE_URL", "http://testserver")

from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app import db as db_module  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402
from app.routers.shorten import limiter  # noqa: E402


@pytest_asyncio.fixture
async def engine():
    # StaticPool keeps every connection pointed at the same in-memory database.
    from sqlalchemy.pool import StaticPool

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    db_module._engine = eng
    db_module._sessionmaker = async_sessionmaker(eng, expire_on_commit=False)

    yield eng

    await eng.dispose()
    db_module._engine = None
    db_module._sessionmaker = None


@pytest_asyncio.fixture
async def client(engine):
    limiter.reset()

    # The app's own lifespan would build a Postgres engine; the fixture has
    # already installed a SQLite one, so it is replaced with a no-op.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    app = create_app(lifespan_handler=noop_lifespan)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as ac:
        yield ac

    limiter.reset()


@pytest_asyncio.fixture
async def session(engine):
    async with db_module._sessionmaker() as s:
        yield s
