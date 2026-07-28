from app.shortcode import (
    ALPHABET,
    CODE_LENGTH,
    RESERVED_CODES,
    generate_code,
    is_valid_code,
)


def test_generated_code_shape():
    for _ in range(200):
        code = generate_code()
        assert len(code) == CODE_LENGTH
        assert all(c in ALPHABET for c in code)


def test_generated_codes_are_not_sequential():
    # The point of random codes is that links cannot be enumerated, so a large
    # sample should show essentially no repeats.
    codes = [generate_code() for _ in range(5000)]
    assert len(set(codes)) == len(codes)


def test_never_generates_reserved_code():
    for _ in range(500):
        assert generate_code().lower() not in RESERVED_CODES


def test_is_valid_code_accepts_generated():
    assert is_valid_code(generate_code())


def test_is_valid_code_rejects_junk():
    assert not is_valid_code("")
    assert not is_valid_code("has-dash")
    assert not is_valid_code("has_underscore")
    assert not is_valid_code("with space")
    assert not is_valid_code("a" * 17)
    assert not is_valid_code("../../etc/passwd")
