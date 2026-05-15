from __future__ import annotations

from uuid import uuid4

from nlp_parser.auth.jwt_tools import decode_token, issue_access_token
from nlp_parser.auth.passwords import hash_password, verify_password
from nlp_parser.config import Settings


def test_app_imports():
    from nlp_parser import main

    assert main.app.title == "AIS nlp-parser"


def test_password_hash_roundtrip():
    pw = "diploma-secret-123"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h) is True
    assert verify_password("wrong", h) is False


def test_jwt_issue_and_decode():
    settings = Settings(JWT_SECRET="unit-test-secret-min-32-chars-long-xx")
    user_id = uuid4()
    token = issue_access_token(user_id, role="user", settings=settings)
    claims = decode_token(token, settings=settings)
    assert claims["sub"] == str(user_id)
    assert claims["role"] == "user"
    assert "exp" in claims and "iat" in claims
