from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from nlp_parser.auth.jwt_tools import current_user, issue_access_token
from nlp_parser.auth.passwords import hash_password, verify_password
from nlp_parser.config import get_settings
from nlp_parser.persistence.postgres import UsersRepo

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=200)
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


def _user_repo(request: Request) -> UsersRepo:
    return UsersRepo(request.app.state.postgres)


def _user_to_dict(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "display_name": user.get("display_name"),
        "role": user.get("role", "user"),
    }


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, users: UsersRepo = Depends(_user_repo)):
    existing = await users.get_by_email(body.email)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    user = await users.create(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    token = issue_access_token(UUID(str(user["id"])), role=user.get("role", "user"))
    return {"token": token, "user": _user_to_dict(user)}


@router.post("/login")
async def login(body: LoginRequest, users: UsersRepo = Depends(_user_repo)):
    user = await users.get_by_email(body.email)
    if user is None or not user.get("is_active") or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    token = issue_access_token(UUID(str(user["id"])), role=user.get("role", "user"))
    return {"token": token, "user": _user_to_dict(user)}


@router.get("/me")
async def me(user: dict[str, Any] = Depends(current_user)):
    return _user_to_dict(user)


class UpdateProfileRequest(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = Field(default=None, max_length=200)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=6, max_length=200)


@router.patch("/me")
async def update_me(
    body: UpdateProfileRequest,
    user: dict[str, Any] = Depends(current_user),
    users: UsersRepo = Depends(_user_repo),
):
    if body.email is not None and body.email != user["email"]:
        existing = await users.get_by_email(body.email)
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already registered")
    updated = await users.update_profile(
        UUID(str(user["id"])),
        email=body.email,
        display_name=body.display_name,
    )
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return _user_to_dict(updated)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: ChangePasswordRequest,
    user: dict[str, Any] = Depends(current_user),
    users: UsersRepo = Depends(_user_repo),
):
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid current password")
    await users.update_password(UUID(str(user["id"])), hash_password(body.new_password))
    return None


__all__ = ["router"]
