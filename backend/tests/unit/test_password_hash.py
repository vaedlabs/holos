"""Password hashing with bcrypt directly (no passlib)."""

import pytest

from app.orchestration.passwords import get_password_hash, password_problem, verify_password

pytestmark = pytest.mark.unit

# Made by passlib 1.7.4 CryptContext(schemes=["bcrypt"]) from "LegacyPass123"
PASSLIB_HASH = "$2b$12$Ka0azVEAmKEKhYSHFTN86eD0X9icSWRFrHJ1JnpCEoF08MVG5Sbm2"


def test_hash_and_verify():
    hashed = get_password_hash("Correct-Horse-1")
    assert hashed.startswith("$2b$12$")
    assert verify_password("Correct-Horse-1", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_passlib_hash_still_verifies():
    assert verify_password("LegacyPass123", PASSLIB_HASH) is True
    assert verify_password("LegacyPass124", PASSLIB_HASH) is False


def test_password_over_72_bytes_is_rejected():
    with pytest.raises(ValueError, match="Password is too long"):
        get_password_hash("a" * 100)


def test_multibyte_password_counted_in_bytes():
    # 25 x 3-byte characters = 75 bytes, though only 25 characters
    with pytest.raises(ValueError, match="Password is too long"):
        get_password_hash("€" * 25)
    assert verify_password("€" * 24, get_password_hash("€" * 24)) is True


def test_72_byte_password_is_accepted():
    password = "a" * 72
    assert verify_password(password, get_password_hash(password)) is True


def test_long_login_password_behaves_like_first_72_bytes():
    # Older accounts were hashed from a cut password; login must not raise
    hashed = get_password_hash("a" * 72)
    assert verify_password("a" * 100, hashed) is True


def test_malformed_hash_returns_false():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_same_password_hashes_differently_each_time():
    # Moved from tests/test_auth.py (P4.2): the salt is random
    first, second = get_password_hash("Correct-Horse-1"), get_password_hash("Correct-Horse-1")
    assert first != second
    assert verify_password("Correct-Horse-1", first) and verify_password("Correct-Horse-1", second)


def test_malformed_stored_hash_fails_closed():
    assert verify_password("anything", "not-a-bcrypt-hash") is False


@pytest.mark.parametrize(("password", "problem"), [
    ("short7!", "too short"),
    ("eight8!!", None),
    ("a" * 72, None),
    ("a" * 73, "too long"),
    ("€" * 25, "too long"),  # 25 characters, 75 bytes
])
def test_new_password_rules(password, problem):
    found = password_problem(password)
    assert (found is None) if problem is None else (problem in found.lower())


def test_an_unknown_email_costs_as_much_as_a_wrong_password():
    import time

    from app.orchestration.passwords import verify_unknown_user

    real = get_password_hash("Correct-Horse-1")
    start = time.perf_counter()
    verify_password("wrong-password", real)
    known = time.perf_counter() - start
    start = time.perf_counter()
    assert verify_unknown_user("wrong-password") is False
    unknown = time.perf_counter() - start
    assert unknown > known * 0.5  # both run a full 12-round bcrypt check
