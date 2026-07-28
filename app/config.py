"""Runtime configuration, read from the environment."""

import os
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit


def _normalize_database_url(url: str) -> str:
    """Point a libpq-style URL at SQLAlchemy's psycopg (v3) async driver.

    DigitalOcean Managed Postgres injects DATABASE_URL as
    postgresql://...?sslmode=require. SQLAlchemy needs an explicit driver in the
    scheme; psycopg3 understands sslmode natively, so the query string is left
    untouched.
    """
    if not url:
        return url

    parts = urlsplit(url)
    if parts.scheme in ("postgres", "postgresql"):
        parts = parts._replace(scheme="postgresql+psycopg")
    return urlunsplit(parts)


class Settings:
    def __init__(self) -> None:
        self.database_url: str = _normalize_database_url(
            os.getenv("DATABASE_URL", "")
        )

        # Used to build the short_url returned by the API. On App Platform set
        # this to your custom domain, e.g. https://sho.rt
        self.base_url: str = os.getenv("BASE_URL", "http://localhost:8080").rstrip("/")

        self.port: int = int(os.getenv("PORT", "8080"))
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()

        # Requests per window, per client IP, on the shorten endpoint.
        self.rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
        self.rate_limit_window_seconds: int = int(
            os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60")
        )

        # Number of proxy hops in front of the app. App Platform terminates TLS
        # and appends one entry to X-Forwarded-For.
        self.trusted_proxy_hops: int = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))

        # Gates the disable endpoint. Left unset the endpoint fails closed
        # (503) rather than being open — an unauthenticated delete would be
        # strictly worse than having no delete at all.
        self.admin_token: str = os.getenv("ADMIN_TOKEN", "")

        self.db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
        self.db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
