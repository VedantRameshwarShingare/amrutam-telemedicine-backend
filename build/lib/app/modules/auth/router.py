from __future__ import annotations

from typing import Annotated

from app.common.exceptions import (
    AuthenticationError,
    ConflictError,
    RateLimitExceededError,
)
from app.core.database import get_db
from app.core.security import (
    get_current_active_user,
    rate_limit_login,
    rate_limit_mfa,
    rate_limit_refresh,
    rate_limit_registration,
    require_role,
)
from app.modules.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    MFASetupResponse,
    MFATokenSetupRequest,
    MFAVerifyRequest,
    RefreshTokenRequest,
    TokenPairResponse,
    UserPublicResponse,
    UserRegistrationRequest,
)
from app.modules.auth.service import AuthService
from app.modules.users.models import User, UserRole
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["Authentication"])


def auth_error_detail(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


@router.post("/register", response_model=UserPublicResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserRegistrationRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    try:
        client_ip = request.client.host if request.client else "unknown"
        await rate_limit_registration(client_ip)
        service = AuthService(db)
        user = await service.register(
            email=payload.email,
            phone=payload.phone,
            password=payload.password,
            role=payload.role,
        )
        return user
    except ConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=auth_error_detail("USER_ALREADY_EXISTS", str(exc)),
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=auth_error_detail("RATE_LIMIT_EXCEEDED", str(exc)),
        ) from exc


@router.post("/login", response_model=TokenPairResponse)
async def login_user(
    payload: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    try:
        client_ip = request.client.host if request.client else "unknown"
        await rate_limit_login(payload.email.lower(), client_ip)
        service = AuthService(db)
        tokens = await service.login(email=payload.email, password=payload.password)
        await db.commit()
        return tokens
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error_detail("INVALID_CREDENTIALS", "Invalid credentials"),
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=auth_error_detail("RATE_LIMIT_EXCEEDED", str(exc)),
        ) from exc


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_tokens(
    payload: RefreshTokenRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    try:
        user_identity = request.client.host if request.client else "unknown"
        service = AuthService(db)
        await rate_limit_refresh(user_identity, user_identity)
        tokens = await service.refresh_tokens(refresh_token=payload.refresh_token)
        await db.commit()
        return tokens
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error_detail("INVALID_REFRESH_TOKEN", "Invalid refresh token"),
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=auth_error_detail("RATE_LIMIT_EXCEEDED", str(exc)),
        ) from exc


@router.post("/logout")
async def logout_user(
    payload: LogoutRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    try:
        service = AuthService(db)
        await service.logout(refresh_token=payload.refresh_token)
        await db.commit()
        return {"status": "success"}
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error_detail("INVALID_REFRESH_TOKEN", "Invalid refresh token"),
        ) from exc


@router.post("/mfa/setup", response_model=MFASetupResponse)
async def setup_mfa(
    payload: MFATokenSetupRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str | bool]:
    try:
        await rate_limit_mfa(payload.email.lower())
        service = AuthService(db)
        result = await service.setup_mfa(email=payload.email, password=payload.password)
        await db.commit()
        return result
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error_detail("INVALID_CREDENTIALS", "Invalid credentials"),
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=auth_error_detail("RATE_LIMIT_EXCEEDED", str(exc)),
        ) from exc


@router.post("/mfa/verify")
async def verify_mfa(
    payload: MFAVerifyRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str | bool]:
    try:
        await rate_limit_mfa(payload.email.lower())
        service = AuthService(db)
        result = await service.verify_mfa(
            email=payload.email,
            password=payload.password,
            totp_code=payload.totp_code,
        )
        await db.commit()
        return result
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=auth_error_detail("INVALID_TOTP", "Invalid TOTP code"),
        ) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=auth_error_detail("RATE_LIMIT_EXCEEDED", str(exc)),
        ) from exc


@router.get("/me", response_model=UserPublicResponse)
async def get_me(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    return current_user


@router.get("/admin-example")
async def admin_example(
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
) -> dict[str, str]:
    return {"message": "admin access"}
