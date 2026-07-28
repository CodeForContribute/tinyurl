import pytest

from app.validate import MAX_URL_LENGTH, InvalidURL, validate_url


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com",
        "http://example.com/path?q=1#frag",
        "https://sub.domain.example.co.uk:8443/a/b",
        "https://8.8.8.8/public",
        "https://例え.jp/path",
    ],
)
def test_accepts_public_urls(url):
    assert validate_url(url) == url


def test_strips_surrounding_whitespace():
    assert validate_url("  https://example.com  ") == "https://example.com"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "file:///etc/passwd",
        "ftp://example.com/x",
    ],
)
def test_rejects_disallowed_schemes(url):
    with pytest.raises(InvalidURL):
        validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:5432",
        "http://10.0.0.5/internal",
        "http://192.168.1.1",
        "http://172.16.0.1",
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://[::1]/",
        "http://0.0.0.0",
        "http://metadata.google.internal/",
    ],
)
def test_rejects_non_public_hosts(url):
    with pytest.raises(InvalidURL):
        validate_url(url)


def test_rejects_embedded_credentials():
    # Renders as "example.com" in many clients, navigates to evil.com.
    with pytest.raises(InvalidURL, match="credentials"):
        validate_url("https://example.com@evil.com/")


def test_rejects_missing_scheme():
    with pytest.raises(InvalidURL, match="scheme"):
        validate_url("example.com/path")


def test_rejects_missing_host():
    with pytest.raises(InvalidURL):
        validate_url("https:///path")


def test_rejects_empty():
    with pytest.raises(InvalidURL):
        validate_url("   ")


def test_rejects_overlong_url():
    with pytest.raises(InvalidURL, match="exceeds"):
        validate_url("https://example.com/" + "a" * MAX_URL_LENGTH)


def test_rejects_control_characters():
    # CR/LF here would let a caller smuggle headers into the redirect response.
    with pytest.raises(InvalidURL, match="control characters"):
        validate_url("https://example.com/\r\nSet-Cookie: x=1")


def test_trailing_dot_hostname_still_blocked():
    with pytest.raises(InvalidURL):
        validate_url("http://localhost./")
