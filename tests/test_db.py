import pytest
from sqlalchemy.exc import IntegrityError

from app import db as db_module
from app.db import CodeGenerationError, create_link, get_link_by_code

pytestmark = pytest.mark.asyncio


async def test_create_and_fetch_roundtrip(session):
    link = await create_link(session, "https://example.com/x", client_ip="203.0.113.9")

    fetched = await get_link_by_code(session, link.code)
    assert fetched is not None
    assert fetched.target_url == "https://example.com/x"
    assert fetched.created_by_ip == "203.0.113.9"
    assert fetched.created_at is not None


async def test_fetch_unknown_code_returns_none(session):
    assert await get_link_by_code(session, "zzzzzzz") is None


async def test_retries_past_a_code_collision(session, monkeypatch):
    """A losing race on the unique index must retry, not surface an error."""
    taken = await create_link(session, "https://example.com/first")
    # Held as a plain string: the rollback inside create_link expires the ORM
    # instance, and re-reading an attribute would then trigger IO off-thread.
    taken_code = taken.code

    codes = iter([taken_code, "fresh01"])
    monkeypatch.setattr(db_module, "generate_code", lambda: next(codes))

    link = await create_link(session, "https://example.com/second")

    assert link.code == "fresh01"
    assert (await get_link_by_code(session, taken_code)).target_url == (
        "https://example.com/first"
    )


async def test_gives_up_after_exhausting_attempts(session, monkeypatch):
    taken = await create_link(session, "https://example.com/only")
    taken_code = taken.code
    monkeypatch.setattr(db_module, "generate_code", lambda: taken_code)

    with pytest.raises(CodeGenerationError):
        await create_link(session, "https://example.com/doomed")


async def test_non_collision_integrity_error_propagates(session, monkeypatch):
    """A schema-level failure must not be misreported as code exhaustion.

    This is the bug the SQLite BIGINT mismatch originally hid: every insert was
    failing on a NOT NULL breach, but the retry loop reported it as a collision.
    """
    monkeypatch.setattr(db_module, "generate_code", lambda: None)  # violates NOT NULL

    with pytest.raises(IntegrityError):
        await create_link(session, "https://example.com/bad")
