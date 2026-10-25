"""Password hashing with bcrypt directly (no passlib)."""

import pytest

from app.auth import get_password_hash, verify_password

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
