"""Submitted-URL validation.

A URL shortener is an open redirector by definition, which makes it attractive
for phishing and for laundering traffic at internal infrastructure. Everything
here exists to shrink that blast radius before a link is ever persisted.
"""

import ipaddress
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})
MAX_URL_LENGTH = 2048

# Hostnames that resolve to the machine itself or to cloud metadata endpoints.
BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "metadata",
        "metadata.google.internal",
    }
)


class InvalidURL(ValueError):
    """Raised when a submitted URL is not safe or well-formed enough to store."""


def _host_is_blocked(host: str) -> bool:
    host = host.strip("[]").rstrip(".").lower()

    if host in BLOCKED_HOSTNAMES or host.endswith(".localhost"):
        return True

    # Literal IPs get checked against every non-public range. Hostnames that
    # resolve to private space are deliberately NOT resolved here: a DNS lookup
    # on the request path is slow and racy (the name can be re-pointed after the
    # check), so egress filtering is the correct control for that case.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url(raw: str) -> str:
    """Normalize and validate a submitted URL, or raise InvalidURL."""
    if not raw or not raw.strip():
        raise InvalidURL("URL must not be empty")

    url = raw.strip()

    if len(url) > MAX_URL_LENGTH:
        raise InvalidURL(f"URL exceeds {MAX_URL_LENGTH} characters")

    # Control characters can be used to smuggle newlines into a Location header.
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in url):
        raise InvalidURL("URL must not contain control characters")

    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise InvalidURL("URL is malformed") from exc

    scheme = parts.scheme.lower()
    if not scheme:
        raise InvalidURL("URL must include a scheme (http:// or https://)")
    if scheme not in ALLOWED_SCHEMES:
        raise InvalidURL(f"scheme '{scheme}' is not allowed; use http or https")

    if not parts.hostname:
        raise InvalidURL("URL must include a host")

    # https://trusted.com@evil.com renders as "trusted.com" in many clients but
    # navigates to evil.com. There is no legitimate need for it in a short link.
    if parts.username or parts.password:
        raise InvalidURL("URL must not contain embedded credentials")

    if _host_is_blocked(parts.hostname):
        raise InvalidURL("URL must point to a publicly routable host")

    try:
        if parts.port is not None and not (0 < parts.port < 65536):
            raise InvalidURL("URL port is out of range")
    except ValueError as exc:
        raise InvalidURL("URL port is invalid") from exc

    return url
