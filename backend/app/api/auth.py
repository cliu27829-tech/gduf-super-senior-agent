from __future__ import annotations

from datetime import UTC, datetime
import logging

import jwt
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, or_, select, update

from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DbSession
from app.core.rate_limit import auth_limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.entities import Campus, Location, RefreshToken, User, UserPreference
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    UserRead,
)


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("gduf-api.auth")


def _set_cookies(response: Response, access: str, refresh: str) -> None:
    settings = get_settings()
    common = {
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "httponly": True,
    }
    response.set_cookie("access_token", access, max_age=settings.access_token_minutes * 60, path="/", **common)
    response.set_cookie("refresh_token", refresh, max_age=settings.refresh_token_days * 86400, path="/api/auth", **common)


def _clear_cookies(response: Response) -> None:
    settings = get_settings()
    common = {
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "httponly": True,
    }
    response.delete_cookie("access_token", path="/", **common)
    response.delete_cookie("refresh_token", path="/api/auth", **common)


def _issue_tokens(db: DbSession, user: User, response: Response) -> AuthResponse:
    access, access_expires = create_access_token(user.id, user.role)
    refresh, jti, refresh_expires = create_refresh_token(user.id, user.role)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=jti,
            token_hash=hash_token(refresh),
            expires_at=refresh_expires,
        )
    )
    db.commit()
    _set_cookies(response, access, refresh)
    return AuthResponse(user=UserRead.model_validate(user), access_expires_at=access_expires)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, request: Request, response: Response, db: DbSession) -> AuthResponse:
    # Campus networks commonly place many students behind one public IP;
    # keep a short burst limit without blocking a small shared-NAT group.
    auth_limiter.check(f"register:{request.client.host if request.client else 'unknown'}", 10, 300)
    email = payload.email.lower()
    existing = db.scalar(
        select(User).where(or_(func.lower(User.email) == email, func.lower(User.username) == payload.username.lower()))
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱或用户名已被使用")
    campus = db.scalar(select(Campus).where(Campus.id == payload.campus_id, Campus.is_active.is_(True)))
    if not campus:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="所选校区不可用")
    user = User(
        email=email,
        username=payload.username.strip(),
        nickname=payload.nickname.strip() or payload.username.strip(),
        password_hash=hash_password(payload.password),
        campus_id=campus.id,
        grade=payload.grade.strip(),
        major=payload.major.strip(),
    )
    db.add(user)
    db.flush()
    return _issue_tokens(db, user, response)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession) -> AuthResponse:
    key = f"login:{request.client.host if request.client else 'unknown'}:{payload.email.lower()}"
    auth_limiter.check(key, 10, 300)
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    return _issue_tokens(db, user, response)


@router.post("/refresh", response_model=AuthResponse)
def refresh(request: Request, response: Response, db: DbSession) -> AuthResponse:
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新凭据不存在")
    try:
        payload = decode_token(token, "refresh")
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新凭据无效") from exc
    stored = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
    now = datetime.now(UTC)
    expires_at = stored.expires_at.replace(tzinfo=UTC) if stored and stored.expires_at.tzinfo is None else (stored.expires_at if stored else now)
    if not stored or stored.revoked_at or expires_at <= now or stored.token_hash != hash_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新凭据已失效")
    user = db.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="账户不可用")
    stored.revoked_at = now
    return _issue_tokens(db, user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession) -> Response:
    token = request.cookies.get("refresh_token")
    if token:
        try:
            payload = decode_token(token, "refresh")
            stored = db.scalar(select(RefreshToken).where(RefreshToken.jti == payload["jti"]))
            if stored and not stored.revoked_at:
                stored.revoked_at = datetime.now(UTC)
                db.commit()
        except jwt.PyJWTError as exc:
            logger.info("logout_with_invalid_refresh error_type=%s", type(exc).__name__)
    _clear_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserRead)
def update_me(payload: ProfileUpdate, user: CurrentUser, db: DbSession) -> User:
    changes = payload.model_dump(exclude_unset=True)
    preference_changes = {
        key: changes.pop(key)
        for key in ("preferred_name", "address_style", "preferred_location_id")
        if key in changes
    }
    if "campus_id" in changes and changes["campus_id"]:
        if not db.scalar(select(Campus).where(Campus.id == changes["campus_id"], Campus.is_active.is_(True))):
            raise HTTPException(status_code=422, detail="所选校区不可用")
    if preference_changes.get("preferred_location_id"):
        location = db.scalar(
            select(Location).where(
                Location.id == preference_changes["preferred_location_id"],
                Location.is_active.is_(True),
                Location.data_status != "demo_fixture",
            )
        )
        target_campus = changes.get("campus_id", user.campus_id)
        if not location or location.campus_id != target_campus:
            raise HTTPException(status_code=422, detail="常用地点必须属于当前校区且可公开查询")
    for key, value in changes.items():
        setattr(user, key, value.strip() if isinstance(value, str) else value)
    if preference_changes:
        preference = user.preference or UserPreference(user_id=user.id)
        for key, value in preference_changes.items():
            setattr(preference, key, value.strip() if isinstance(value, str) else value)
        if not user.preference:
            db.add(preference)
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: ChangePasswordRequest, response: Response, user: CurrentUser, db: DbSession) -> Response:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    user.password_hash = hash_password(payload.new_password)
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)).values(revoked_at=datetime.now(UTC)))
    db.commit()
    _clear_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(response: Response, user: CurrentUser, db: DbSession) -> Response:
    if user.role == "admin":
        raise HTTPException(status_code=409, detail="管理员账号包含审计记录，不能在个人中心自助删除")
    db.delete(user)
    db.commit()
    _clear_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
