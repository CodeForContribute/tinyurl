"""Per-IP sliding-window rate limiting for the shorten endpoint.

Scope caveat: this limiter lives in process memory, so each App Platform
instance enforces the budget independently — N instances means an effective
limit of N x RATE_LIMIT_REQUESTS. That is an accepted trade for the v1 core
(no Redis yet); the fix is to move the counter into Redis when the cache layer
lands. It still does the job it is here to do, which is stopping a single host
from bulk-submitting thousands of links.
"""

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Request

# Keys are evicted lazily; this bounds memory if the key space grows unbounded.
_CLEANUP_EVERY_SECONDS = 300


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._last_cleanup = time.monotonic()

    def _prune(self, bucket: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()

    def _cleanup(self, now: float) -> None:
        if now - self._last_cleanup < _CLEANUP_EVERY_SECONDS:
            return
        cutoff = now - self.window_seconds
        for key in [k for k, b in self._hits.items() if not b or b[-1] <= cutoff]:
            del self._hits[key]
        self._last_cleanup = now

    def check(self, key: str) -> tuple[bool, int]:
        """Record a hit for `key`. Returns (allowed, retry_after_seconds)."""
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            bucket = self._hits[key]
            self._prune(bucket, now)

            if len(bucket) >= self.max_requests:
                retry_after = max(1, int(bucket[0] + self.window_seconds - now) + 1)
                return False, retry_after

            bucket.append(now)
            return True, 0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request, trusted_hops: int = 1) -> str:
    """Resolve the caller's IP, honouring X-Forwarded-For behind known proxies.

    Each proxy appends the address it received the request from, so with one
    trusted hop the rightmost entry is the real client. Entries further left are
    caller-controlled and must not be trusted.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded and trusted_hops > 0:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            index = max(0, len(parts) - trusted_hops)
            return parts[index]

    return request.client.host if request.client else "unknown"
