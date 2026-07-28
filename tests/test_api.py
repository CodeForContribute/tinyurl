import pytest

from app.routers.shorten import limiter

pytestmark = pytest.mark.asyncio


async def test_healthz(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readyz(client):
    r = await client.get("/readyz")
    assert r.status_code == 200


async def test_shorten_returns_created(client):
    r = await client.post("/api/shorten", json={"url": "https://example.com/long/path"})
    assert r.status_code == 201

    body = r.json()
    assert body["target_url"] == "https://example.com/long/path"
    assert body["short_url"].endswith(body["code"])
    assert len(body["code"]) == 7


async def test_shorten_then_redirect(client):
    created = await client.post("/api/shorten", json={"url": "https://example.com/dest"})
    code = created.json()["code"]

    r = await client.get(f"/{code}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://example.com/dest"


async def test_redirect_is_not_cacheable(client):
    # A 301 or a cacheable 302 would make an abusive link impossible to kill.
    created = await client.post("/api/shorten", json={"url": "https://example.com/x"})
    r = await client.get(f"/{created.json()['code']}", follow_redirects=False)

    assert r.status_code == 302
    assert "no-store" in r.headers["cache-control"]


async def test_same_url_gets_distinct_codes(client):
    url = {"url": "https://example.com/same"}
    a = await client.post("/api/shorten", json=url)
    b = await client.post("/api/shorten", json=url)

    assert a.json()["code"] != b.json()["code"]


async def test_redirect_unknown_code_404s(client):
    r = await client.get("/aaaaaaa", follow_redirects=False)
    assert r.status_code == 404


async def test_redirect_malformed_code_404s(client):
    r = await client.get("/not-a-valid-code", follow_redirects=False)
    assert r.status_code == 404


@pytest.mark.parametrize(
    "bad_url",
    [
        "javascript:alert(1)",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "https://example.com@evil.com/",
        "not-a-url",
        "",
    ],
)
async def test_shorten_rejects_bad_urls(client, bad_url):
    r = await client.post("/api/shorten", json={"url": bad_url})
    assert r.status_code == 400
    assert "detail" in r.json()


async def test_shorten_rejects_missing_field(client):
    r = await client.post("/api/shorten", json={})
    assert r.status_code == 422


async def test_rate_limit_kicks_in(client):
    limiter.reset()
    limit = limiter.max_requests

    for _ in range(limit):
        ok = await client.post("/api/shorten", json={"url": "https://example.com/ok"})
        assert ok.status_code == 201

    blocked = await client.post("/api/shorten", json={"url": "https://example.com/no"})
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers
    limiter.reset()


async def test_rate_limit_is_per_ip(client):
    limiter.reset()

    for _ in range(limiter.max_requests):
        await client.post(
            "/api/shorten",
            json={"url": "https://example.com/a"},
            headers={"X-Forwarded-For": "203.0.113.1"},
        )

    exhausted = await client.post(
        "/api/shorten",
        json={"url": "https://example.com/a"},
        headers={"X-Forwarded-For": "203.0.113.1"},
    )
    assert exhausted.status_code == 429

    other = await client.post(
        "/api/shorten",
        json={"url": "https://example.com/b"},
        headers={"X-Forwarded-For": "203.0.113.2"},
    )
    assert other.status_code == 201
    limiter.reset()


async def test_reserved_paths_are_not_shadowed_by_redirect(client):
    # /{code} is a catch-all; these must still hit their real handlers.
    assert (await client.get("/healthz")).status_code == 200
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/openapi.json")).status_code == 200
