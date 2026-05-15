from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from nlp_parser.config import Settings, get_settings
from nlp_parser.persistence.postgres import UsersRepo


_bearer = HTTPBearer(auto_error=False)


def issue_access_token(user_id: UUID, *, role: str, settings: Settings | None = None) -> str:
    cfg = settings or get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=cfg.jwt_access_ttl_seconds)).timestamp()),
    }
    return jwt.encode(payload, cfg.jwt_secret, algorithm=cfg.jwt_algorithm)


def decode_token(token: str, *, settings: Settings | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    return jwt.decode(token, cfg.jwt_secret, algorithms=[cfg.jwt_algorithm])


async def current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return await _resolve_user(request, credentials.credentials)


async def current_user_sse(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    """Auth для SSE: EventSource не умеет ставить заголовок Authorization,
    поэтому принимаем токен либо из Bearer, либо из query ?token=."""
    token: str | None = None
    if credentials is not None and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    if token is None:
        token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    return await _resolve_user(request, token)


async def _resolve_user(request: Request, token: str) -> dict[str, Any]:
    try:
        claims = decode_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"invalid token: {exc}") from exc
    user_id_raw = claims.get("sub")
    if not user_id_raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token missing sub")
    try:
        user_id = UUID(user_id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad sub") from exc
    users = UsersRepo(request.app.state.postgres)
    user = await users.get_by_id(user_id)
    if user is None or not user.get("is_active"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return user


def require_role(role: str):
    async def _checker(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        if user.get("role") != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"role '{role}' required")
        return user

    return _checker


__all__ = [
    "issue_access_token",
    "decode_token",
    "current_user",
    "current_user_sse",
    "require_role",
]
