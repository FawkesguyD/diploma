from __future__ import annotations

import hashlib
import hmac
import secrets


PBKDF2_ALGORITHM = "sha256"
PBKDF2_ITERATIONS = 600_000
PBKDF2_PREFIX = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    derived_key = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"{PBKDF2_PREFIX}${PBKDF2_ITERATIONS}${salt}${derived_key.hex()}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        return False

    try:
        algorithm, iterations, salt, expected_hash = password_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != PBKDF2_PREFIX:
        return False

    derived_key = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    )
    return hmac.compare_digest(derived_key.hex(), expected_hash)
