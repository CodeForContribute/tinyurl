"""Short code generation.

Codes are drawn uniformly at random from a base62 alphabet rather than derived
from a sequential ID. Sequential codes would let anyone enumerate every link on
the service by walking /1, /2, /3 — a privacy leak, since people shorten
documents and one-off access links that are only "private" by obscurity.

At 7 characters the space is 62^7 = 3.5e12. Collisions are handled by the unique
index on links.code plus a bounded retry in the store layer, so the birthday
bound only affects insert latency, never correctness.
"""

import secrets

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
CODE_LENGTH = 7

# Codes are matched by a catch-all route, so anything the app serves at the
# top level must never be issued as a code.
RESERVED_CODES = frozenset(
    {
        "healthz",
        "readyz",
        "docs",
        "redoc",
        "openapi",
        "api",
        "static",
        "favicon",
        "robots",
        "admin",
    }
)


def generate_code(length: int = CODE_LENGTH) -> str:
    """Return a cryptographically random base62 code."""
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if code.lower() not in RESERVED_CODES:
            return code


def is_valid_code(code: str) -> bool:
    """Cheap syntactic check so obviously bogus paths never reach the database."""
    if not code or len(code) > 16:
        return False
    return all(c in ALPHABET for c in code)
