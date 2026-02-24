from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import resend
from fastapi import Cookie, Depends, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.database import get_db
from backend.src.config import settings
from backend.src.contracts.models import MagicLinkToken, User
from backend.src.users.repository import UserRepository


async def create_magic_link(email: str, session: AsyncSession) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.magic_link_expiry_minutes
    )

    magic_link = MagicLinkToken(
        id=uuid.uuid4(),
        email=email,
        token=token,
        expires_at=expires_at,
        used=False,
    )
    session.add(magic_link)
    await session.flush()

    verify_url = f"{settings.frontend_url}/auth/verify?token={token}"

    resend.api_key = settings.resend_api_key
    resend.Emails.send(
        {
            "from": settings.resend_from_email,
            "to": [email],
            "subject": "Your Norrona Alert sign-in link",
            "html": (
                f"<p>Click the link below to sign in to Norrona Alert:</p>"
                f'<p><a href="{verify_url}">Sign in to Norrona Alert</a></p>'
                f"<p>This link expires in {settings.magic_link_expiry_minutes} minutes.</p>"
            ),
        }
    )

    return token


async def verify_magic_link(token: str, session: AsyncSession) -> User:
    stmt = select(MagicLinkToken).where(
        MagicLinkToken.token == token,
        MagicLinkToken.used.is_(False),
    )
    result = await session.execute(stmt)
    magic_link = result.scalar_one_or_none()

    if magic_link is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    if magic_link.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired token",
        )

    magic_link.used = True
    await session.flush()

    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(magic_link.email)
    if user is None:
        user = await user_repo.create(magic_link.email)

    return user


def create_jwt(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: uuid.UUID) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expiry_days),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def get_current_user(
    session: AsyncSession = Depends(get_db),
    access_token: str | None = Cookie(default=None),
) -> User:
    if access_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    try:
        payload = jwt.decode(
            access_token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id_str: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")

        if user_id_str is None or token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user
