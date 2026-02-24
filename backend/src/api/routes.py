import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.api.auth import (
    create_jwt,
    create_magic_link,
    create_refresh_token,
    get_current_user,
    verify_magic_link,
)
from backend.src.api.database import get_db
from backend.src.config import settings
from backend.src.contracts.models import (
    DeviceRegistration,
    DeviceRegistrationCreate,
    DeviceRegistrationRead,
    ProductSnapshot,
    User,
    UserPreferences,
    UserRead,
)
from backend.src.products.repository import ProductRepository
from backend.src.users.repository import UserRepository

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────────────


class MagicLinkRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    token: str


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str


# ── Auth routes ───────────────────────────────────────────────────────────────


@router.post("/auth/magic-link", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
async def send_magic_link(
    request: Request,
    body: MagicLinkRequest,
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    await create_magic_link(body.email, session)
    return JSONResponse(
        content={"message": "Magic link sent"},
        status_code=status.HTTP_200_OK,
    )


@router.post("/auth/verify", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def verify_token(
    request: Request,
    body: VerifyRequest,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> UserRead:
    user = await verify_magic_link(body.token, session)
    access_token = create_jwt(user.id)
    refresh_token = create_refresh_token(user.id)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.jwt_expiry_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.refresh_token_expiry_days * 86400,
        path="/auth/refresh",
    )

    return UserRead(
        id=user.id,
        email=user.email,
        preferences=user.get_preferences(),
        created_at=user.created_at,
    )


@router.post("/auth/refresh", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def refresh_jwt(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_db),
) -> JSONResponse:
    from jose import JWTError, jwt as jose_jwt

    refresh_token: str | None = request.cookies.get("refresh_token")
    if refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token",
        )

    try:
        payload = jose_jwt.decode(
            refresh_token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id_str: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")

        if user_id_str is None or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    new_access_token = create_jwt(user.id)
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=settings.jwt_expiry_minutes * 60,
        path="/",
    )

    return JSONResponse(
        content={"message": "Token refreshed"},
        status_code=status.HTTP_200_OK,
    )


# ── Preferences routes ───────────────────────────────────────────────────────


@router.get("/api/preferences")
async def get_preferences(
    current_user: User = Depends(get_current_user),
) -> UserPreferences:
    return current_user.get_preferences()


@router.put("/api/preferences")
async def update_preferences(
    prefs: UserPreferences,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserPreferences:
    user_repo = UserRepository(session)
    updated_user = await user_repo.update_preferences(current_user.id, prefs)
    return updated_user.get_preferences()


# ── Outlet routes ─────────────────────────────────────────────────────────────


@router.get("/api/outlet")
async def get_outlet_products(
    locale: str = "en-GB",
    session: AsyncSession = Depends(get_db),
) -> list[ProductSnapshot]:
    product_repo = ProductRepository(session)
    rows = await product_repo.get_latest_by_locale(locale)
    return [row.to_schema() for row in rows]


# ── Device registration ──────────────────────────────────────────────────────


@router.post("/api/devices", status_code=status.HTTP_201_CREATED)
async def register_device(
    body: DeviceRegistrationCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DeviceRegistrationRead:
    device = DeviceRegistration(
        id=uuid.uuid4(),
        user_id=current_user.id,
        device_token=body.device_token,
        platform=body.platform.value,
    )
    session.add(device)
    await session.flush()

    return DeviceRegistrationRead(
        id=device.id,
        user_id=device.user_id,
        device_token=device.device_token,
        platform=body.platform,
        created_at=device.created_at,
    )


# ── Health ────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health_check(
    session: AsyncSession = Depends(get_db),
) -> HealthResponse:
    db_status = "ok"
    redis_status = "ok"

    try:
        await session.execute(
            __import__("sqlalchemy").text("SELECT 1")
        )
    except Exception:
        db_status = "error"

    try:
        redis_client = aioredis.from_url(settings.redis_url)
        await redis_client.ping()
        await redis_client.aclose()
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(
        status=overall,
        db=db_status,
        redis=redis_status,
    )
