from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from uuid import uuid4

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings


password_hasher = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_hasher.verify(password, password_hash)


def _encode(user_id: str, role: str, token_type: str, secret: str, expires_delta: timedelta) -> tuple[str, str, datetime]:
    expires_at = datetime.now(UTC) + expires_delta
    jti = str(uuid4())
    token = jwt.encode(
        {
            "sub": user_id,
            "role": role,
            "type": token_type,
            "jti": jti,
            "iat": datetime.now(UTC),
            "exp": expires_at,
        },
        secret,
        algorithm="HS256",
    )
    return token, jti, expires_at


def create_access_token(user_id: str, role: str) -> tuple[str, datetime]:
    settings = get_settings()
    token, _, expires_at = _encode(
        user_id, role, "access", settings.jwt_secret, timedelta(minutes=settings.access_token_minutes)
    )
    return token, expires_at


def create_refresh_token(user_id: str, role: str) -> tuple[str, str, datetime]:
    settings = get_settings()
    return _encode(
        user_id, role, "refresh", settings.refresh_token_secret, timedelta(days=settings.refresh_token_days)
    )


def decode_token(token: str, token_type: str) -> dict:
    settings = get_settings()
    secret = settings.jwt_secret if token_type == "access" else settings.refresh_token_secret
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    if payload.get("type") != token_type or not payload.get("sub"):
        raise jwt.InvalidTokenError("Unexpected token type")
    return payload


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

