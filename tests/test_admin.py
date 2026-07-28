import pytest

from app.config import get_settings
from app.routers.admin import admin_limiter

pytestmark = pytest.mark.asyncio

ADMIN_TOKEN = "test-admin-token"
AUTH = {"X-Admin-Token": ADMIN_TOKEN}


@pytest.fixture(autouse=True)
def _configure_admin_token(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "admin_token", ADMIN_TOKEN)
    admin_limiter.reset()
    yield
    admin_limiter.reset()


async def _make_link(client, url="https://example.com/target"):
    r = await client.post("/api/shorten", json={"url": url})
    assert r.status_code == 201
    return r.json()["code"]


async def test_disable_stops_the_redirect(client):
    """The whole point: a disabled link must stop sending people onward."""
    code = await _make_link(client)

    before = await client.get(f"/{code}", follow_redirects=False)
    assert before.status_code == 302

    deleted = await client.delete(f"/api/links/{code}", headers=AUTH)
    assert deleted.status_code == 200

    after = await client.get(f"/{code}", follow_redirects=False)
    assert after.status_code == 404


async def test_disable_returns_the_record(client):
    code = await _make_link(client, "https://example.com/phish")

    r = await client.delete(
        f"/api/links/{code}", headers=AUTH, params={"reason": "reported as phishing"}
    )

    body = r.json()
    assert body["code"] == code
    assert body["target_url"] == "https://example.com/phish"
    assert body["disabled_reason"] == "reported as phishing"
    assert body["disabled_at"] is not None


async def test_disable_is_idempotent(client):
    code = await _make_link(client)

    first = await client.delete(f"/api/links/{code}", headers=AUTH, params={"reason": "a"})
    second = await client.delete(f"/api/links/{code}", headers=AUTH, params={"reason": "b"})

    assert first.status_code == 200
    assert second.status_code == 200
    # The original timestamp and reason survive a duplicate report.
    assert second.json()["disabled_at"] == first.json()["disabled_at"]
    assert second.json()["disabled_reason"] == "a"


async def test_reason_is_optional(client):
    code = await _make_link(client)
    r = await client.delete(f"/api/links/{code}", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["disabled_reason"] is None


async def test_rejects_missing_token(client):
    code = await _make_link(client)
    r = await client.delete(f"/api/links/{code}")
    assert r.status_code == 401
    # And the link must still work, i.e. the failed call changed nothing.
    assert (await client.get(f"/{code}", follow_redirects=False)).status_code == 302


async def test_rejects_wrong_token(client):
    code = await _make_link(client)
    r = await client.delete(f"/api/links/{code}", headers={"X-Admin-Token": "nope"})
    assert r.status_code == 401
    assert (await client.get(f"/{code}", follow_redirects=False)).status_code == 302


async def test_fails_closed_when_token_unconfigured(client, monkeypatch):
    """With no ADMIN_TOKEN set the endpoint must be unavailable, not open."""
    code = await _make_link(client)
    monkeypatch.setattr(get_settings(), "admin_token", "")

    r = await client.delete(f"/api/links/{code}")
    assert r.status_code == 503

    # Critically, an empty configured token must not match an empty header.
    r2 = await client.delete(f"/api/links/{code}", headers={"X-Admin-Token": ""})
    assert r2.status_code == 503
    assert (await client.get(f"/{code}", follow_redirects=False)).status_code == 302


async def test_unknown_code_404s(client):
    r = await client.delete("/api/links/zzzzzzz", headers=AUTH)
    assert r.status_code == 404


async def test_malformed_code_404s(client):
    r = await client.delete("/api/links/not-a-code", headers=AUTH)
    assert r.status_code == 404


async def test_disabled_code_is_not_reissued(client):
    """The row is retained, so the code stays reserved rather than recycled."""
    from app import db as db_module

    code = await _make_link(client)
    await client.delete(f"/api/links/{code}", headers=AUTH)

    # Force the generator to hand back the disabled code.
    codes = iter([code, "fresh99"])
    monkey = getattr(db_module, "generate_code")
    db_module.generate_code = lambda: next(codes)
    try:
        r = await client.post("/api/shorten", json={"url": "https://example.com/new"})
    finally:
        db_module.generate_code = monkey

    assert r.status_code == 201
    assert r.json()["code"] == "fresh99"


async def test_admin_endpoint_is_rate_limited(client):
    admin_limiter.reset()
    for _ in range(admin_limiter.max_requests):
        await client.delete("/api/links/zzzzzzz", headers={"X-Admin-Token": "wrong"})

    r = await client.delete("/api/links/zzzzzzz", headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 429
    admin_limiter.reset()
