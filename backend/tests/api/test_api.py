from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.src.api.auth import create_jwt, create_refresh_token, get_current_user
from backend.src.api.database import get_db
from backend.src.api.routes import limiter, router
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
        # For SQLite, start a nested transaction so that the test session
        # can be used with the same commit/rollback semantics.
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
    app = FastAPI()
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
    async def test_verify_valid_token_creates_user_and_sets_cookies(
        self, client: httpx.AsyncClient
    ) -> None:
        token = await create_test_magic_link(email="newuser@example.com")
        response = await client.post(
            "/auth/verify",
            json={"token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert "id" in data
        assert "preferences" in data
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    @pytest.mark.asyncio
    async def test_verify_existing_user_returns_user(
        self, client: httpx.AsyncClient
    ) -> None:
        user = await create_test_user(email="existing@example.com")
        token = await create_test_magic_link(email="existing@example.com")
        response = await client.post(
            "/auth/verify",
            json={"token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "existing@example.com"
        assert data["id"] == str(user.id)

    @pytest.mark.asyncio
    async def test_verify_invalid_token(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/auth/verify",
            json={"token": "nonexistent-token"},
        )
        assert response.status_code == 400

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


# ── Tests: Auth Middleware ────────────────────────────────────────────────────


class TestAuthMiddleware:
    @pytest.mark.asyncio
    async def test_reject_unauthenticated_preferences(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.get("/api/preferences")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_reject_unauthenticated_devices(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/api/devices",
            json={"device_token": "tok", "platform": "web"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_accept_valid_jwt(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user(email="authed@example.com")
        token = create_jwt(user.id)
        response = await client.get(
            "/api/preferences",
            cookies={"access_token": token},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reject_expired_jwt(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user(email="expiredtoken@example.com")
        with patch("backend.src.config.settings.jwt_expiry_minutes", -1):
            from jose import jwt as jose_jwt
            now = datetime.now(timezone.utc)
            payload = {
                "sub": str(user.id),
                "iat": now - timedelta(hours=1),
                "exp": now - timedelta(minutes=1),
                "type": "access",
            }
            from backend.src.config import settings
            expired_token = jose_jwt.encode(
                payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
            )
        response = await client.get(
            "/api/preferences",
            cookies={"access_token": expired_token},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_reject_invalid_jwt(self, client: httpx.AsyncClient) -> None:
        response = await client.get(
            "/api/preferences",
            cookies={"access_token": "not.a.valid.jwt"},
        )
        assert response.status_code == 401


# ── Tests: Preferences CRUD ──────────────────────────────────────────────────


class TestPreferences:
    @pytest.mark.asyncio
    async def test_get_default_preferences(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user(email="prefs@example.com")
        token = create_jwt(user.id)
        response = await client.get(
            "/api/preferences",
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "en-GB"
        assert data["size_map"] == {}
        assert data["watchlist_terms"] == []
        assert data["max_price"] is None

    @pytest.mark.asyncio
    async def test_update_preferences(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user(email="update@example.com")
        token = create_jwt(user.id)

        new_prefs = {
            "region": "nb-NO",
            "size_map": {"jackets": "M", "pants": "L"},
            "watchlist_terms": ["falketind", "lofoten"],
            "max_price": 200.0,
        }
        response = await client.put(
            "/api/preferences",
            json=new_prefs,
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "nb-NO"
        assert data["size_map"] == {"jackets": "M", "pants": "L"}
        assert data["watchlist_terms"] == ["falketind", "lofoten"]
        assert data["max_price"] == 200.0

    @pytest.mark.asyncio
    async def test_preferences_persist_after_update(
        self, client: httpx.AsyncClient
    ) -> None:
        user = await create_test_user(email="persist@example.com")
        token = create_jwt(user.id)

        new_prefs = {
            "region": "nb-NO",
            "size_map": {"jackets": "S"},
            "watchlist_terms": ["bitihorn"],
            "max_price": 100.0,
        }
        await client.put(
            "/api/preferences",
            json=new_prefs,
            cookies={"access_token": token},
        )

        response = await client.get(
            "/api/preferences",
            cookies={"access_token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["region"] == "nb-NO"
        assert data["watchlist_terms"] == ["bitihorn"]


# ── Tests: Outlet Endpoint ───────────────────────────────────────────────────


class TestOutlet:
    @pytest.mark.asyncio
    async def test_get_outlet_empty(self, client: httpx.AsyncClient) -> None:
        response = await client.get("/api/outlet?locale=en-GB")
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_get_outlet_with_products(self, client: httpx.AsyncClient) -> None:
        await insert_product(name="Falketind Jacket", locale="en-GB")
        await insert_product(
            name="Lofoten Pants",
            url="https://norrona.com/en-GB/products/lofoten-pants",
            locale="en-GB",
            category="pants",
        )
        response = await client.get("/api/outlet?locale=en-GB")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        names = {p["name"] for p in data}
        assert "Falketind Jacket" in names
        assert "Lofoten Pants" in names

    @pytest.mark.asyncio
    async def test_get_outlet_filters_by_locale(
        self, client: httpx.AsyncClient
    ) -> None:
        await insert_product(name="EN Product", locale="en-GB")
        await insert_product(
            name="NO Product",
            url="https://norrona.com/nb-NO/products/no-product",
            locale="nb-NO",
        )
        response = await client.get("/api/outlet?locale=nb-NO")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "NO Product"

    @pytest.mark.asyncio
    async def test_get_outlet_default_locale(self, client: httpx.AsyncClient) -> None:
        await insert_product(name="Default Locale Product", locale="en-GB")
        response = await client.get("/api/outlet")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Default Locale Product"


# ── Tests: Device Registration ────────────────────────────────────────────────


class TestDeviceRegistration:
    @pytest.mark.asyncio
    async def test_register_device(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user(email="device@example.com")
        token = create_jwt(user.id)
        response = await client.post(
            "/api/devices",
            json={"device_token": "fcm-token-123", "platform": "web"},
            cookies={"access_token": token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["device_token"] == "fcm-token-123"
        assert data["platform"] == "web"
        assert data["user_id"] == str(user.id)
        assert "id" in data
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_register_ios_device(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user(email="ios@example.com")
        token = create_jwt(user.id)
        response = await client.post(
            "/api/devices",
            json={"device_token": "apns-token-abc", "platform": "ios"},
            cookies={"access_token": token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["platform"] == "ios"

    @pytest.mark.asyncio
    async def test_register_device_unauthenticated(
        self, client: httpx.AsyncClient
    ) -> None:
        response = await client.post(
            "/api/devices",
            json={"device_token": "tok", "platform": "web"},
        )
        assert response.status_code == 401


# ── Tests: Health Endpoint ────────────────────────────────────────────────────


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_db_ok(self, client: httpx.AsyncClient) -> None:
        with patch("backend.src.api.routes.aioredis") as mock_redis:
            mock_client = MagicMock()
            mock_client.ping = MagicMock(return_value=None)
            mock_client.aclose = MagicMock(return_value=None)

            # Make the mock async-aware
            import asyncio

            async def async_ping() -> bool:
                return True

            async def async_close() -> None:
                pass

            mock_client.ping = async_ping
            mock_client.aclose = async_close
            mock_redis.from_url.return_value = mock_client

            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["db"] == "ok"
        assert data["redis"] == "ok"
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_redis_down(self, client: httpx.AsyncClient) -> None:
        with patch("backend.src.api.routes.aioredis") as mock_redis:
            mock_redis.from_url.side_effect = ConnectionError("Redis down")

            response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["db"] == "ok"
        assert data["redis"] == "error"
        assert data["status"] == "degraded"


# ── Tests: Refresh Token ─────────────────────────────────────────────────────


class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_refresh_with_valid_token(self, client: httpx.AsyncClient) -> None:
        user = await create_test_user(email="refresh@example.com")
        refresh = create_refresh_token(user.id)
        response = await client.post(
            "/auth/refresh",
            cookies={"refresh_token": refresh},
        )
        assert response.status_code == 200
        assert "access_token" in response.cookies

    @pytest.mark.asyncio
    async def test_refresh_without_token(self, client: httpx.AsyncClient) -> None:
        response = await client.post("/auth/refresh")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token(self, client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/auth/refresh",
            cookies={"refresh_token": "bad-token"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_type_rejected(
        self, client: httpx.AsyncClient
    ) -> None:
        user = await create_test_user(email="wrongtype@example.com")
        access = create_jwt(user.id)
        response = await client.post(
            "/auth/refresh",
            cookies={"refresh_token": access},
        )
        assert response.status_code == 401


# ── Tests: Rate Limiting ─────────────────────────────────────────────────────


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limit_magic_link(self) -> None:
        # Create a fresh app with strict rate limit for testing
        test_limiter = Limiter(key_func=get_remote_address)
        test_app = FastAPI()
        test_app.state.limiter = test_limiter
        test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        # Create a router with a stricter rate limit
        test_router = APIRouter()

        @test_router.post("/auth/magic-link-limited")
        @test_limiter.limit("2/minute")
        async def limited_endpoint(request: httpx.Request) -> dict[str, str]:
            return {"message": "ok"}

        test_app.include_router(test_router)

        transport = httpx.ASGITransport(app=test_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            # First two requests should succeed
            r1 = await c.post("/auth/magic-link-limited")
            assert r1.status_code == 200

            r2 = await c.post("/auth/magic-link-limited")
            assert r2.status_code == 200

            # Third request should be rate limited
            r3 = await c.post("/auth/magic-link-limited")
            assert r3.status_code == 429
