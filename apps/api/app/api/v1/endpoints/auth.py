"""app.api.v1.endpoints.auth

Simple, secure-ish local auth for development.

This module intentionally mirrors the "in-memory now, DB later" approach used in
repositories. It provides:

- POST /auth/register   (create account)
- POST /auth/login      (get bearer token)
- GET  /auth/me         (who am I?)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field


# ----------------------------
# Pydantic models (API)
# ----------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=256)
    display_name: Optional[str] = Field(None, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=256)


class UserPublic(BaseModel):
    user_id: str
    email: EmailStr
    display_name: Optional[str]
    created_at: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: UserPublic


# ----------------------------
# In-memory storage (dev)
# ----------------------------


@dataclass
class _UserRow:
    user_id: str
    email: str
    display_name: Optional[str]
    password_hash: str
    created_at: str


@dataclass
class _SessionRow:
    token: str
    user_id: str
    expires_at: datetime


class AuthStorage:
    """In-memory auth storage.

    Swap this class for a DB-backed implementation later.
    """

    def __init__(self, *, token_ttl_hours: int = 24):
        self._users_by_email: Dict[str, _UserRow] = {}
        self._users_by_id: Dict[str, _UserRow] = {}
        self._sessions_by_token: Dict[str, _SessionRow] = {}
        self._token_ttl = timedelta(hours=token_ttl_hours)

    # ---- users ----
    def create_user(self, *, email: str, password: str, display_name: Optional[str]) -> _UserRow:
        email_key = email.strip().lower()
        if email_key in self._users_by_email:
            raise ValueError("email_already_registered")

        user_id = str(uuid.uuid4())
        password_hash = _hash_password(password)
        created_at = _utc_now().isoformat()
        row = _UserRow(
            user_id=user_id,
            email=email_key,
            display_name=display_name,
            password_hash=password_hash,
            created_at=created_at,
        )
        self._users_by_email[email_key] = row
        self._users_by_id[user_id] = row
        return row

    def get_user_by_email(self, email: str) -> Optional[_UserRow]:
        return self._users_by_email.get(email.strip().lower())

    def get_user_by_id(self, user_id: str) -> Optional[_UserRow]:
        return self._users_by_id.get(user_id)

    # ---- sessions ----
    def create_session(self, user_id: str) -> _SessionRow:
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + self._token_ttl
        row = _SessionRow(token=token, user_id=user_id, expires_at=expires_at)
        self._sessions_by_token[token] = row
        return row

    def get_session(self, token: str) -> Optional[_SessionRow]:
        row = self._sessions_by_token.get(token)
        if not row:
            return None
        if datetime.now(timezone.utc) >= row.expires_at:
            # expire lazily
            self._sessions_by_token.pop(token, None)
            return None
        return row


# Global auth storage instance
auth_storage = AuthStorage()


# ----------------------------
# Crypto helpers (PBKDF2)
# ----------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(txt: str) -> bytes:
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode((txt + pad).encode("ascii"))


def _hash_password(password: str, *, iterations: int = 210_000) -> str:
    if not isinstance(password, str):
        raise TypeError("password must be str")
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )
    return f"pbkdf2_sha256${iterations}${_b64e(salt)}${_b64e(dk)}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters_s, salt_b64, hash_b64 = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iters_s)
        salt = _b64d(salt_b64)
        expected = _b64d(hash_b64)
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False


# ----------------------------
# Router + endpoints
# ----------------------------


router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/auth/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest):
    """Create a new user account."""
    try:
        row = auth_storage.create_user(
            email=req.email,
            password=req.password,
            display_name=req.display_name,
        )
    except ValueError as e:
        if str(e) == "email_already_registered":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )
        raise

    return UserPublic(
        user_id=row.user_id,
        email=row.email,
        display_name=row.display_name,
        created_at=row.created_at,
    )


@router.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """Login with email/password and receive a bearer token."""
    row = auth_storage.get_user_by_email(req.email)
    # Avoid leaking whether an email exists: return the same error either way.
    if not row or not _verify_password(req.password, row.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    session = auth_storage.create_session(row.user_id)
    return TokenResponse(
        access_token=session.token,
        token_type="bearer",
        expires_at=session.expires_at.isoformat(),
        user=UserPublic(
            user_id=row.user_id,
            email=row.email,
            display_name=row.display_name,
            created_at=row.created_at,
        ),
    )


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> _UserRow:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = creds.credentials  # token WITHOUT "Bearer "
    session = auth_storage.get_session(token)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = auth_storage.get_user_by_id(session.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.get("/auth/me", response_model=UserPublic)
def me(user: _UserRow = Depends(get_current_user)):
    """Return the currently-authenticated user."""
    return UserPublic(
        user_id=user.user_id,
        email=user.email,
        display_name=user.display_name,
        created_at=user.created_at,
    )

