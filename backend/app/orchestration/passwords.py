"""Password hashing with bcrypt directly (Plan C.18; passlib removed in P0.6)."""

import bcrypt

BCRYPT_MAX_BYTES = 72
PASSWORD_MIN_CHARS = 8  # not set by the plan (Part E #24)
TOO_LONG = "Password is too long. Please use 72 characters or fewer."
TOO_SHORT = f"Password is too short. Please use at least {PASSWORD_MIN_CHARS} characters."

# Verified when the email is unknown, so a wrong email takes as long as a wrong password
_DUMMY_HASH = bcrypt.hashpw(b"no such user", bcrypt.gensalt(rounds=12)).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Accepts hashes made by passlib (same $2b$ format). The password is cut to
    72 bytes because older accounts were hashed from a cut password, and bcrypt 5
    raises on longer input instead of ignoring the extra bytes."""
    password_bytes = plain_password.encode("utf-8")[:BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def verify_unknown_user(plain_password: str) -> bool:
    """Spend the same time as a real check, then fail."""
    verify_password(plain_password, _DUMMY_HASH)
    return False


def password_problem(password: str) -> str | None:
    """Why a new password can't be used, or None."""
    if len(password) < PASSWORD_MIN_CHARS:
        return TOO_SHORT
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        return TOO_LONG  # bcrypt would silently ignore the extra bytes
    return None


def get_password_hash(password: str) -> str:
    """bcrypt, 12 rounds, random salt. Raises ValueError over 72 bytes."""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_BYTES:
        raise ValueError(TOO_LONG)
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")
