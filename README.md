# tinyurl

A URL shortener. FastAPI + Postgres, deployed on DigitalOcean App Platform.

This is the **v1 core**: create a link, follow a link, and the hardening needed
to survive contact with the public internet. Analytics, custom aliases,
expiration, Redis caching and accounts are deliberately not here yet — see
[Roadmap](#roadmap).

## API

| Method | Path           | Purpose                                    |
| ------ | -------------- | ------------------------------------------ |
| `POST` | `/api/shorten` | Create a short link                        |
| `GET`  | `/{code}`      | 302 redirect to the target                 |
| `GET`  | `/healthz`     | Liveness — no dependencies                 |
| `GET`  | `/readyz`      | Readiness — checks the database            |
| `GET`  | `/docs`        | OpenAPI browser                            |

```bash
curl -X POST http://localhost:8080/api/shorten \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://example.com/a/very/long/path"}'
```

```json
{
  "code": "5UgvBuv",
  "short_url": "http://localhost:8080/5UgvBuv",
  "target_url": "https://example.com/a/very/long/path",
  "created_at": "2026-07-29T01:20:28Z"
}
```

## Design decisions

**Random codes, not sequential IDs.** Base62-encoding an auto-increment ID would
make every link enumerable — anyone could walk `/1`, `/2`, `/3` and harvest every
URL on the service. People shorten documents and one-off access links whose only
protection is obscurity, so codes are 7 characters drawn from a CSPRNG (62^7 =
3.5e12). Uniqueness is enforced by an index, with a bounded retry on collision.

**302, not 301.** A 301 is cached by the browser indefinitely: you would never
see a repeat visit and, worse, could never change or disable a destination. The
response to an abusive link has to take effect immediately, so redirects are 302
with `Cache-Control: no-store`.

**Validation is a security control, not a formatting check.** A shortener is an
open redirector by definition. `app/validate.py` enforces an http/https scheme
allowlist, blocks private, loopback, link-local and cloud-metadata addresses,
rejects embedded credentials (`https://trusted.com@evil.com`), and strips
control characters that could smuggle headers into the `Location` response.

**Liveness does not touch the database.** If `/healthz` checked Postgres, a
database blip would fail the App Platform health check and trigger a restart
loop that cannot possibly fix the problem. `/readyz` is the one that checks.

## Local development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env          # then edit DATABASE_URL

.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8080
```

Tests run against in-memory SQLite and need no external services:

```bash
.venv/bin/python -m pytest -q
```

## Deploying to App Platform

The spec is already pointed at `CodeForContribute/tinyurl` on branch `main`.
If you fork or rename, update the `repo` field in **both** the `services` and
`jobs` blocks, and set `region` if `blr` is not nearest you.

1. Push this repo to GitHub.
2. Authorize DigitalOcean to read it — one-time, at
   <https://cloud.digitalocean.com/apps/github/install>.
3. Create the app:

```bash
doctl apps create --spec .do/app.yaml
```

The spec provisions a managed Postgres instance, injects its connection string
as `DATABASE_URL`, and runs `alembic upgrade head` as a `PRE_DEPLOY` job so
migrations land before new containers take traffic. `BASE_URL` is wired to
`${APP_URL}`; point it at your custom domain once you attach one, otherwise
`short_url` will echo the `ondigitalocean.app` hostname.

Subsequent pushes to `main` deploy automatically. To apply spec changes:

```bash
doctl apps update <APP_ID> --spec .do/app.yaml
```

### Cost note

`apps-s-1vcpu-0.5gb` plus a dev Postgres runs roughly $12–17/month. The database
is `production: false`, which means a single node with no standby — fine for now,
not for anything you care about losing. Flip it before real traffic.

## Known limitations

- **Rate limiting is per-instance.** The limiter holds counters in process
  memory, so scaling to N instances yields an effective limit of
  N x `RATE_LIMIT_REQUESTS`. It still stops a single host from bulk-submitting,
  which is what it is there for. Moving the counter to Redis is the fix and is
  tied to the caching work below.
- **No malware or phishing screening.** Any valid public URL is accepted.
  Google Safe Browsing integration is the intended control.
- **Hostnames are not resolved during validation.** A DNS lookup on the request
  path is slow and racy — the name can be re-pointed after the check passes — so
  literal private IPs are blocked but `evil.com` resolving to `10.0.0.1` is not.
  Egress filtering is the correct layer for that.
- **No delete or edit.** Links are permanent once created, which means abuse
  response currently requires a manual `DELETE FROM links`.

## Roadmap

Tier 2 — the features that make it a product:

- Click analytics (timestamp, referrer, user agent, country)
- Custom aliases
- Link expiration
- Redis read-through cache on the redirect path, plus negative caching so
  scanners hammering random codes do not reach Postgres

Tier 3:

- Accounts and API keys, per-user link management
- Safe Browsing integration and an abuse-report endpoint
- QR code generation, bulk shorten API
