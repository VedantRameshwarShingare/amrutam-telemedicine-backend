from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import jwt
from app.common.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    ValidationError,
)
from app.core.config import settings
from app.core.redis import redis_client
from app.core.security import (
    create_access_token,
    create_refresh_token,
    generate_totp_secret,
    generate_totp_uri,
    hash_password,
    validate_password_policy,
    verify_password,
    verify_totp,
)
from app.modules.auth.models import RefreshToken
from app.modules.auth.repository import UserRepository
from app.modules.users.models import User, UserRole
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = UserRepository(session)

    async def register(
        self,
        *,
        email: str,
        phone: str,
        password: str,
        role: UserRole | None = None,
    ) -> User:
        email = email.lower().strip()
        phone = phone.strip()
        validate_password_policy(password)

        if await self.repository.get_by_email(email):
            raise ConflictError("Email already exists")
        if await self.repository.get_by_phone(phone):
            raise ConflictError("Phone already exists")

        if role is None:
            role = UserRole.PATIENT
        if role == UserRole.ADMIN:
            raise AuthorizationError("Public registration cannot create admin users")

        user = await self.repository.create(
            email=email,
            phone=phone,
            password_hash=hash_password(password),
            role=role,
        )
        await self.session.commit()
        return user

    async def login(
        self,
        *,
        email: str,
        password: str,
        mfa_code: str | None = None,
    ) -> dict[str, str]:
        user = await self.repository.get_by_email(email.lower())
        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid credentials")

        if user.mfa_enabled:
            if not mfa_code:
                raise AuthenticationError("MFA code required")
            if not user.mfa_secret or not verify_totp(user.mfa_secret, mfa_code):
                raise AuthenticationError("Invalid MFA code")

        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)
        self._store_refresh_token(user, refresh_token)
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def refresh_tokens(self, *, refresh_token: str) -> dict[str, str]:
        try:
            payload = jwt.decode(
                refresh_token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Refresh token is invalid") from exc

        if payload.get("type") != "refresh":
            raise AuthenticationError("Token type is invalid for refresh")

        try:
            revoked = await redis_client.get(f"revoked_refresh:{payload.get('jti')}")
            if revoked:
                raise AuthenticationError("Refresh token has been revoked")
        except Exception:
            pass

        token_jti = payload.get("jti")
        if not token_jti:
            raise AuthenticationError("Refresh token is missing identity")
        stmt = (
            select(RefreshToken)
            .where(RefreshToken.token_jti == token_jti)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        stored_token = result.scalar_one_or_none()
        expires_at = stored_token.expires_at if stored_token else None
        if expires_at is not None and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        expired = expires_at is None or expires_at <= datetime.now(UTC)
        if (
            stored_token is None
            or stored_token.revoked_at is not None
            or expired
        ):
            raise AuthenticationError("Refresh token has been revoked or expired")

        user_id = payload.get("sub")
        user = await self.repository.get_by_id(UUID(user_id)) if user_id else None
        if user is None or not user.is_active:
            raise AuthenticationError("User no longer active")

        new_access = create_access_token(user)
        new_refresh = create_refresh_token(user, token_family=payload.get("tf"))
        new_payload = jwt.decode(
            new_refresh,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        stored_token.revoked_at = datetime.now(UTC)
        stored_token.replaced_by = str(new_payload["jti"])
        self._store_refresh_token(user, new_refresh)
        return {
            "access_token": new_access,
            "refresh_token": new_refresh,
            "token_type": "bearer",
        }

    async def logout(self, *, refresh_token: str) -> None:
        try:
            payload = jwt.decode(
                refresh_token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError("Refresh token is invalid") from exc

        if payload.get("type") != "refresh":
            raise AuthenticationError("Token type is invalid for logout")

        token_jti = payload.get("jti")
        if token_jti:
            stmt = select(RefreshToken).where(RefreshToken.token_jti == token_jti)
            result = await self.session.execute(stmt)
            record = result.scalar_one_or_none()
            if record is None:
                user_id = payload.get("sub")
                try:
                    user_uuid = UUID(str(user_id)) if user_id else None
                except (TypeError, ValueError):
                    user_uuid = None
                record = RefreshToken(
                    user_id=user_uuid,
                    token_jti=token_jti,
                    token_family=payload.get("tf") or "unknown",
                    expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
                    revoked_at=datetime.now(UTC),
                    user_agent=None,
                    ip_address=None,
                )
                self.session.add(record)
            else:
                record.revoked_at = datetime.now(UTC)

        try:
            await redis_client.set(f"revoked_refresh:{payload['jti']}", "1", ex=60 * 60 * 24 * 7)
        except Exception:
            pass

    async def setup_mfa(self, *, email: str, password: str) -> dict[str, str | bool]:
        user = await self.repository.get_by_email(email.lower())
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid credentials")

        secret = generate_totp_secret()
        user.mfa_secret = secret
        user.mfa_enabled = False
        await self.session.commit()

        return {
            "secret": secret,
            "otpauth_url": generate_totp_uri(user.email, secret),
            "verified": False,
        }

    async def verify_mfa(
        self,
        *,
        email: str,
        password: str,
        totp_code: str,
    ) -> dict[str, bool | str]:
        user = await self.repository.get_by_email(email.lower())
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid credentials")
        if not user.mfa_secret:
            raise ValidationError("MFA setup is required before verification")
        if not verify_totp(user.mfa_secret, totp_code):
            raise AuthenticationError("Invalid TOTP code")

        user.mfa_enabled = True
        await self.session.commit()
        return {"verified": True, "status": "enabled"}

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self.repository.get_by_email(email.lower())
        if user is None or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid credentials")
        if not user.is_active:
            raise AuthenticationError("User account is inactive")
        return user

    def _store_refresh_token(self, user: User, token: str) -> None:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        self.session.add(
            RefreshToken(
                user_id=user.id,
                token_jti=str(payload["jti"]),
                token_family=str(payload["tf"]),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
            )
        )
