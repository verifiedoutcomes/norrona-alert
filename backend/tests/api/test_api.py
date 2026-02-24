from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.src.api.auth import create_jwt, create_refresh_token, get_current_user
from backend.src.api.database import get_db
from backend.src.api.routes import router
from backend.src.contracts.models import (
    Base,
    DeviceRegistration,
    Locale,
    MagicLinkToken,
    Platform,
    ProductSnapshotRow,
    User,
    UserPreferences,
)
from backend.src.users.repository import UserRepository


# ── Test engine and session (in-memory SQLite) ───────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)

TestSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_database() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        yield session
        await session.rollback()


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def create_test_app() -> FastAPI:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from backend.src.api.routes import limiter

    app = FastAPI()
    # Disable rate limiting in tests — ASGI transport has no client.host
    limiter.enabled = False
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest_asyncio.fixture
async def app() -> FastAPI:
    return create_test_app()


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ── Helper: create a user directly in DB ──────────────────────────────────────


async def create_test_user(email: str = "test@example.com") -> User:
    async with TestSessionFactory() as session:
        repo = UserRepository(session)
        user = await repo.create(email)
        await session.commit()
        await session.refresh(user)
        return user


async def create_test_magic_link(
    email: str = "test@example.com",
    expired: bool = False,
    used: bool = False,
) -> str:
    import secrets

    token = secrets.token_urlsafe(48)
    if expired:
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

    async with TestSessionFactory() as session:
        ml = MagicLinkToken(
            id=uuid.uuid4(),
            email=email,
            token=token,
            expires_at=expires_at,
            used=used,
        )
        session.add(ml)
        await session.commit()
    return token


async def insert_product(
    name: str = "Test Jacket",
    url: str = "https://norrona.com/en-GB/products/test-jacket",
    price: float = 150.0,
    original_price: float = 300.0,
    discount_pct: float = 50.0,
    available_sizes: list[str] | None = None,
    category: str = "jackets",
    image_url: str = "https://norrona.com/images/test.jpg",
    locale: str = "en-GB",
) -> ProductSnapshotRow:
    async with TestSessionFactory() as session:
        row = ProductSnapshotRow(
            id=uuid.uuid4(),
            name=name,
            url=url,
            price=price,
            original_price=original_price,
            discount_pct=discount_pct,
            available_sizes=available_sizes or ["S", "M", "L"],
            category=category,
            image_url=image_url,
            locale=locale,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


def auth_cookies(user_id: uuid.UUID) -> dict[str, str]:
    token = create_jwt(user_id)
    return {"access_token": token}


# ── Tests: Magic Link Flow ────────────────────────────────────────────────────


class TestMagicLinkFlow:
    @pytest.mark.asyncio
    async def test_send_magic_link_returns_200(self, client: httpx.AsyncClient) -> None:
        with patch("backend.src.api.auth.resend") as mock_resend:
            mock_resend.Emails.send = MagicMock(return_value={"id": "fake"})
            response = await client.post(
                "/auth/magic-link",
                json={"email": "user@example.com"},
            )
        assert response.status_code == 200
        assert response.json()["message"] == "Magic link sent"

    @pytest.mark.asyncio
    async def test_send_magic_link_invalid_email(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/auth/magic-link",
            json={"email": "not-an-email"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_verify_valid_token(self, client: httpx.AsyncClient) -> None:
        token = await create_test_magic_link(email="verify@example.com")
        response = await client.post(
            "/auth/verify",
            json={"token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "verify@example.com"
        assert "access_token" in response.cookies or "set-cookie" in response.headers

    @pytest.mark.asyncio
    async def test_verify_expired_token(self, client: httpx.AsyncClient) -> None:
        token = await create_test_magic_link(email="expired@example.com", expired=True)
        response = await client.post(
            "/auth/verify",
            json={"token": token},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_used_token(self, client: httpx.AsyncClient) -> None:
        token = await create_test_magic_link(email="used@example.com", used=True)
        response = await client.post(
            "/auth/verify",
            json={"token": token},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/auth/verify",
            json={"token": "nonexistent-token"},
        )
        assert response.status_code == 400


# ── Tests: Auth Middleware ────────────────────────────────────────────────────


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_unauthenticated_request_rejected(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/preferences")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_jwt_rejected(self, client: httpx.AsyncClient) -> None:
        client.cookies.set("access_token", "invalid-jwt-token")
        response = await client.get("/api/preferences")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_jwt_accepted(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user("auth@example.com")
        client.cookies.set("access_token", create_jwt(user.id))
        response = await client.get("/api/preferences")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_expired_jwt_rejected(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user("expjwt@example.com")
        from jose import jwt as jose_jwt
        from backend.src.config import settings

        expired_payload = {
            "sub": str(user.id),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "type": "access",
        }
        expired_token = jose_jwt.encode(
            expired_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )
        client.cookies.set("access_token", expired_token)
        response = await client.get("/api/preferences")
        assert response.status_code == 401


# ── Tests: Preferences ───────────────────────────────────────────────────────


class TestPreferences:
    @pytest.mark.asyncio
    async def test_get_preferences(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user("prefs@example.com")
        client.cookies.set("access_token", create_jwt(user.id))
        response = await client.get("/api/preferences")
        assert response.status_code == 200
        data = response.json()
        assert "region" in data

    @pytest.mark.asyncio
    async def test_update_preferences(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user("update-prefs@example.com")
        client.cookies.set("access_token", create_jwt(user.id))
        new_prefs = {
            "region": "nb-NO",
            "size_map": {"jackets": "M", "pants": "L"},
            "watchlist_terms": ["falketind", "trollveggen"],
            "max_price": 3000.0,
        }
        response = await client.put("/api/preferences", json=new_prefs)
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "nb-NO"
        assert data["size_map"]["jackets"] == "M"
        assert "falketind" in data["watchlist_terms"]


# ── Tests: Outlet Products ───────────────────────────────────────────────────


class TestOutletProducts:
    @pytest.mark.asyncio
    async def test_get_outlet_products(self, client: httpx.AsyncClient) -> None:
        await insert_product(name="Jacket A", locale="en-GB")
        await insert_product(name="Jacket B", locale="en-GB")
        await insert_product(name="Bukse", locale="nb-NO")

        response = await client.get("/api/outlet", params={"locale": "en-GB"})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_outlet_no_locale_returns_all_or_default(
        self, client: httpx.AsyncClient
    ) -> None:
        await insert_product(name="Product", locale="en-GB")
        response = await client.get("/api/outlet")
        assert response.status_code in (200, 422)


# ── Tests: Device Registration ───────────────────────────────────────────────


class TestDeviceRegistration:
    @pytest.mark.asyncio
    async def test_register_device(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user("device@example.com")
        client.cookies.set("access_token", create_jwt(user.id))
        response = await client.post(
            "/api/devices",
            json={"device_token": "test-token-123", "platform": "web"},
        )
        assert response.status_code in (200, 201)

    @pytest.mark.asyncio
    async def test_register_device_unauthenticated(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/api/devices",
            json={"device_token": "test-token-123", "platform": "web"},
        )
        assert response.status_code == 401


# ── Tests: Health ────────────────────────────────────────────────────────────


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: httpx.AsyncClient) -> None:
        with (
            patch("backend.src.api.routes.aioredis") as mock_redis,
        ):
            mock_client = MagicMock()
            mock_client.ping = AsyncMock(return_value=True)
            mock_client.aclose = AsyncMock()
            mock_redis.from_url = MagicMock(return_value=mock_client)
            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
