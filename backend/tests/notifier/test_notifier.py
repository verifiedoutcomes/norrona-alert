from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.src.config import Settings
from backend.src.contracts.models import (
    AlertSchema,
    ChangeType,
    DeviceRegistration,
    Locale,
    Platform,
    ProductChange,
    ProductSnapshot,
    User,
    UserPreferences,
)
from backend.src.notifier.apns_notifier import ApnsPushNotifier, build_apns_notification
from backend.src.notifier.email_notifier import EmailNotifier, render_email_html
from backend.src.notifier.registry import NotifierRegistry
from backend.src.notifier.web_push_notifier import WebPushNotifier, build_web_push_payload


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        resend_api_key="re_test_key",
        resend_from_email="alerts@norronaalert.com",
        vapid_public_key="test-public-key",
        vapid_private_key="test-private-key",
        vapid_claims_email="mailto:admin@norronaalert.com",
        apns_auth_key_id="TESTKEY123",
        apns_team_id="TESTTEAM12",
        apns_bundle_id="com.norronaalert.app",
        apns_auth_key_path="./test_key.p8",
        apns_use_sandbox=True,
        frontend_url="https://norronaalert.com",
        database_url="sqlite+aiosqlite:///:memory:",
    )


def _make_product(
    name: str = "Falketind Gore-Tex Jacket",
    price: float = 2999.0,
    original_price: float = 5999.0,
    discount_pct: float = 50.0,
    locale: Locale = Locale.EN_GB,
) -> ProductSnapshot:
    return ProductSnapshot(
        name=name,
        url="https://norrona.com/products/falketind-jacket",
        price=price,
        original_price=original_price,
        discount_pct=discount_pct,
        available_sizes=["S", "M", "L"],
        category="jackets",
        image_url="https://cdn.norrona.com/falketind.jpg",
        locale=locale,
        scraped_at=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
    )


def _make_alert(
    user_id: uuid.UUID | None = None,
    product: ProductSnapshot | None = None,
) -> AlertSchema:
    if user_id is None:
        user_id = uuid.uuid4()
    if product is None:
        product = _make_product()
    return AlertSchema(
        user_id=user_id,
        product_change=ProductChange(
            product=product,
            change_type=ChangeType.PRICE_DROP,
            previous_state=_make_product(price=5999.0, discount_pct=0.0),
            new_state=product,
        ),
        matched_rule="price_drop > 20%",
    )


def _make_user(
    region: Locale = Locale.EN_GB,
    devices: list[DeviceRegistration] | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        preferences={"region": region.value},
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    if devices is not None:
        user.devices = devices
    return user


def _make_web_device(user_id: uuid.UUID) -> DeviceRegistration:
    return DeviceRegistration(
        id=uuid.uuid4(),
        user_id=user_id,
        device_token=json.dumps(
            {
                "endpoint": "https://push.example.com/sub/abc123",
                "keys": {"p256dh": "test-p256dh", "auth": "test-auth"},
            }
        ),
        platform=Platform.WEB,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def _make_ios_device(user_id: uuid.UUID) -> DeviceRegistration:
    return DeviceRegistration(
        id=uuid.uuid4(),
        user_id=user_id,
        device_token="abc123def456",
        platform=Platform.IOS,
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


# ── Email template rendering ─────────────────────────────────────────────────


class TestEmailTemplateRendering:
    def test_render_en_gb_template(self, settings: Settings) -> None:
        alert = _make_alert()
        preferences = UserPreferences(region=Locale.EN_GB)
        html = render_email_html(
            alert=alert,
            user_email="test@example.com",
            preferences=preferences,
            frontend_url=settings.frontend_url,
        )

        assert "Falketind Gore-Tex Jacket" in html
        assert "2999.00 NOK" in html
        assert "5999.00 NOK" in html
        assert "-50%" in html
        assert "https://norrona.com/products/falketind-jacket" in html
        assert "https://cdn.norrona.com/falketind.jpg" in html
        assert "View Product" in html
        assert "Unsubscribe" in html
        assert "unsubscribe?email=test@example.com" in html
        assert 'lang="en"' in html
        assert "Price Drop" in html

    def test_render_nb_no_template(self, settings: Settings) -> None:
        alert = _make_alert()
        preferences = UserPreferences(region=Locale.NB_NO)
        html = render_email_html(
            alert=alert,
            user_email="bruker@example.com",
            preferences=preferences,
            frontend_url=settings.frontend_url,
        )

        assert "Falketind Gore-Tex Jacket" in html
        assert "2999.00 NOK" in html
        assert "5999.00 NOK" in html
        assert "-50%" in html
        assert "Se produkt" in html
        assert "Avmeld" in html
        assert "unsubscribe?email=bruker@example.com" in html
        assert 'lang="nb"' in html
        assert "Prisfall" in html

    def test_render_new_product_en_gb(self, settings: Settings) -> None:
        product = _make_product()
        alert = AlertSchema(
            user_id=uuid.uuid4(),
            product_change=ProductChange(
                product=product,
                change_type=ChangeType.NEW,
                new_state=product,
            ),
            matched_rule="new_product",
        )
        preferences = UserPreferences(region=Locale.EN_GB)
        html = render_email_html(
            alert=alert,
            user_email="test@example.com",
            preferences=preferences,
            frontend_url=settings.frontend_url,
        )
        assert "New Product" in html

    def test_render_restock_nb_no(self, settings: Settings) -> None:
        product = _make_product()
        alert = AlertSchema(
            user_id=uuid.uuid4(),
            product_change=ProductChange(
                product=product,
                change_type=ChangeType.RESTOCK,
                new_state=product,
            ),
            matched_rule="restock",
        )
        preferences = UserPreferences(region=Locale.NB_NO)
        html = render_email_html(
            alert=alert,
            user_email="test@example.com",
            preferences=preferences,
            frontend_url=settings.frontend_url,
        )
        assert "Tilbake p\u00e5 lager" in html


# ── Email sending ─────────────────────────────────────────────────────────────


class TestEmailNotifier:
    @pytest.mark.asyncio
    async def test_send_success(self, settings: Settings) -> None:
        notifier = EmailNotifier(settings)
        user = _make_user()
        alert = _make_alert(user_id=user.id)

        with patch("backend.src.notifier.email_notifier.resend.Emails.send") as mock_send:
            mock_send.return_value = {"id": "msg_123"}
            result = await notifier.send(alert, user)

        assert result is True
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0][0]
        assert call_args["to"] == [user.email]
        assert call_args["from"] == settings.resend_from_email
        assert "Price Alert" in call_args["subject"]
        assert "Falketind" in call_args["subject"]

    @pytest.mark.asyncio
    async def test_send_nb_no_subject(self, settings: Settings) -> None:
        notifier = EmailNotifier(settings)
        user = _make_user(region=Locale.NB_NO)
        alert = _make_alert(user_id=user.id)

        with patch("backend.src.notifier.email_notifier.resend.Emails.send") as mock_send:
            mock_send.return_value = {"id": "msg_123"}
            result = await notifier.send(alert, user)

        assert result is True
        call_args = mock_send.call_args[0][0]
        assert "Prisvarsel" in call_args["subject"]

    @pytest.mark.asyncio
    async def test_send_retry_on_failure(self, settings: Settings) -> None:
        notifier = EmailNotifier(settings)
        user = _make_user()
        alert = _make_alert(user_id=user.id)

        with (
            patch("backend.src.notifier.email_notifier.resend.Emails.send") as mock_send,
            patch("backend.src.notifier.email_notifier.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_send.side_effect = [
                RuntimeError("API error"),
                RuntimeError("API error"),
                {"id": "msg_123"},
            ]
            result = await notifier.send(alert, user)

        assert result is True
        assert mock_send.call_count == 3

    @pytest.mark.asyncio
    async def test_send_exhausts_retries(self, settings: Settings) -> None:
        notifier = EmailNotifier(settings)
        user = _make_user()
        alert = _make_alert(user_id=user.id)

        with (
            patch("backend.src.notifier.email_notifier.resend.Emails.send") as mock_send,
            patch("backend.src.notifier.email_notifier.asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_send.side_effect = RuntimeError("persistent failure")
            result = await notifier.send(alert, user)

        assert result is False
        assert mock_send.call_count == 3


# ── Web push payload construction ────────────────────────────────────────────


class TestWebPushPayload:
    def test_build_web_push_payload(self, settings: Settings) -> None:
        alert = _make_alert()
        payload_str = build_web_push_payload(alert, settings.frontend_url)
        payload = json.loads(payload_str)

        assert payload["title"] == "Norr\u00f8na Alert"
        assert "Falketind Gore-Tex Jacket" in payload["body"]
        assert "2999.00 NOK" in payload["body"]
        assert payload["url"] == "https://norrona.com/products/falketind-jacket"
        assert payload["icon"] == "https://cdn.norrona.com/falketind.jpg"


# ── Web push sending ─────────────────────────────────────────────────────────


class TestWebPushNotifier:
    @pytest.mark.asyncio
    async def test_send_success(self, settings: Settings) -> None:
        notifier = WebPushNotifier(settings)
        user = _make_user()
        device = _make_web_device(user.id)
        user.devices = [device]
        alert = _make_alert(user_id=user.id)

        with patch("backend.src.notifier.web_push_notifier.webpush") as mock_push:
            mock_push.return_value = MagicMock(status_code=201)
            result = await notifier.send(alert, user)

        assert result is True
        mock_push.assert_called_once()
        call_kwargs = mock_push.call_args
        sub_info = call_kwargs[1]["subscription_info"] if call_kwargs[1] else call_kwargs[0][0]
        assert "endpoint" in sub_info

    @pytest.mark.asyncio
    async def test_send_no_web_devices(self, settings: Settings) -> None:
        notifier = WebPushNotifier(settings)
        user = _make_user(devices=[])
        alert = _make_alert(user_id=user.id)

        result = await notifier.send(alert, user)
        assert result is True

    @pytest.mark.asyncio
    async def test_send_retry_on_failure(self, settings: Settings) -> None:
        notifier = WebPushNotifier(settings)
        user = _make_user()
        device = _make_web_device(user.id)
        user.devices = [device]
        alert = _make_alert(user_id=user.id)

        with (
            patch("backend.src.notifier.web_push_notifier.webpush") as mock_push,
            patch(
                "backend.src.notifier.web_push_notifier.asyncio.sleep", new_callable=AsyncMock
            ),
        ):
            mock_push.side_effect = [
                RuntimeError("Network error"),
                MagicMock(status_code=201),
            ]
            result = await notifier.send(alert, user)

        assert result is True
        assert mock_push.call_count == 2

    @pytest.mark.asyncio
    async def test_send_exhausts_retries(self, settings: Settings) -> None:
        notifier = WebPushNotifier(settings)
        user = _make_user()
        device = _make_web_device(user.id)
        user.devices = [device]
        alert = _make_alert(user_id=user.id)

        with (
            patch("backend.src.notifier.web_push_notifier.webpush") as mock_push,
            patch(
                "backend.src.notifier.web_push_notifier.asyncio.sleep", new_callable=AsyncMock
            ),
        ):
            mock_push.side_effect = RuntimeError("persistent failure")
            result = await notifier.send(alert, user)

        assert result is False
        assert mock_push.call_count == 3


# ── APNs payload construction ────────────────────────────────────────────────


class TestApnsPayload:
    def test_build_apns_notification(self) -> None:
        alert = _make_alert()
        notification = build_apns_notification(
            alert=alert,
            device_token="abc123def456",
            bundle_id="com.norronaalert.app",
        )

        assert notification.device_token == "abc123def456"
        assert notification.apns_topic == "com.norronaalert.app"

        aps = notification.message["aps"]
        assert aps["alert"]["title"] == "Norr\u00f8na Alert"
        assert "Falketind Gore-Tex Jacket" in aps["alert"]["body"]
        assert "2999.00 NOK" in aps["alert"]["body"]
        assert aps["mutable-content"] == 1
        assert aps["sound"] == "default"

        assert notification.message["product_url"] == "https://norrona.com/products/falketind-jacket"
        assert notification.message["image_url"] == "https://cdn.norrona.com/falketind.jpg"
        assert notification.message["product_name"] == "Falketind Gore-Tex Jacket"
        assert notification.message["price"] == 2999.0


# ── APNs sending ──────────────────────────────────────────────────────────────


class TestApnsPushNotifier:
    @pytest.mark.asyncio
    async def test_send_success(self, settings: Settings) -> None:
        notifier = ApnsPushNotifier(settings)
        user = _make_user()
        device = _make_ios_device(user.id)
        user.devices = [device]
        alert = _make_alert(user_id=user.id)

        mock_result = MagicMock()
        mock_result.is_successful = True

        mock_client = AsyncMock()
        mock_client.send_notification = AsyncMock(return_value=mock_result)

        with patch.object(notifier, "_get_client", return_value=mock_client):
            result = await notifier.send(alert, user)

        assert result is True
        mock_client.send_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_no_ios_devices(self, settings: Settings) -> None:
        notifier = ApnsPushNotifier(settings)
        user = _make_user(devices=[])
        alert = _make_alert(user_id=user.id)

        result = await notifier.send(alert, user)
        assert result is True

    @pytest.mark.asyncio
    async def test_send_retry_on_failure(self, settings: Settings) -> None:
        notifier = ApnsPushNotifier(settings)
        user = _make_user()
        device = _make_ios_device(user.id)
        user.devices = [device]
        alert = _make_alert(user_id=user.id)

        mock_result_fail = MagicMock()
        mock_result_fail.is_successful = False
        mock_result_fail.description = "BadDeviceToken"

        mock_result_ok = MagicMock()
        mock_result_ok.is_successful = True

        mock_client = AsyncMock()
        mock_client.send_notification = AsyncMock(
            side_effect=[mock_result_fail, mock_result_ok]
        )

        with (
            patch.object(notifier, "_get_client", return_value=mock_client),
            patch("backend.src.notifier.apns_notifier.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await notifier.send(alert, user)

        assert result is True
        assert mock_client.send_notification.call_count == 2

    @pytest.mark.asyncio
    async def test_send_exhausts_retries(self, settings: Settings) -> None:
        notifier = ApnsPushNotifier(settings)
        user = _make_user()
        device = _make_ios_device(user.id)
        user.devices = [device]
        alert = _make_alert(user_id=user.id)

        mock_client = AsyncMock()
        mock_client.send_notification = AsyncMock(
            side_effect=RuntimeError("connection failed")
        )

        with (
            patch.object(notifier, "_get_client", return_value=mock_client),
            patch("backend.src.notifier.apns_notifier.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await notifier.send(alert, user)

        assert result is False
        assert mock_client.send_notification.call_count == 3


# ── Registry dispatching ─────────────────────────────────────────────────────


class TestNotifierRegistry:
    @pytest.mark.asyncio
    async def test_dispatch_email_only_no_devices(self, settings: Settings) -> None:
        """When user has no devices, only email is sent."""
        email = EmailNotifier(settings)
        web = WebPushNotifier(settings)
        apns = ApnsPushNotifier(settings)
        registry = NotifierRegistry(email, web, apns)

        user = _make_user(devices=[])
        alert = _make_alert(user_id=user.id)

        with patch.object(email, "send", new_callable=AsyncMock, return_value=True) as m_email:
            with patch.object(web, "send", new_callable=AsyncMock) as m_web:
                with patch.object(apns, "send", new_callable=AsyncMock) as m_apns:
                    results = await registry.notify(alert, user)

        assert results == {"email": True}
        m_email.assert_called_once_with(alert, user)
        m_web.assert_not_called()
        m_apns.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_all_channels(self, settings: Settings) -> None:
        """When user has web and iOS devices, all three channels fire."""
        email = EmailNotifier(settings)
        web = WebPushNotifier(settings)
        apns = ApnsPushNotifier(settings)
        registry = NotifierRegistry(email, web, apns)

        user = _make_user()
        user.devices = [
            _make_web_device(user.id),
            _make_ios_device(user.id),
        ]
        alert = _make_alert(user_id=user.id)

        with (
            patch.object(email, "send", new_callable=AsyncMock, return_value=True),
            patch.object(web, "send", new_callable=AsyncMock, return_value=True),
            patch.object(apns, "send", new_callable=AsyncMock, return_value=True),
        ):
            results = await registry.notify(alert, user)

        assert results == {"email": True, "web_push": True, "apns": True}

    @pytest.mark.asyncio
    async def test_dispatch_web_only(self, settings: Settings) -> None:
        """When user has only web devices, email and web_push fire."""
        email = EmailNotifier(settings)
        web = WebPushNotifier(settings)
        apns = ApnsPushNotifier(settings)
        registry = NotifierRegistry(email, web, apns)

        user = _make_user()
        user.devices = [_make_web_device(user.id)]
        alert = _make_alert(user_id=user.id)

        with (
            patch.object(email, "send", new_callable=AsyncMock, return_value=True),
            patch.object(web, "send", new_callable=AsyncMock, return_value=True),
            patch.object(apns, "send", new_callable=AsyncMock) as m_apns,
        ):
            results = await registry.notify(alert, user)

        assert results == {"email": True, "web_push": True}
        m_apns.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_ios_only(self, settings: Settings) -> None:
        """When user has only iOS devices, email and apns fire."""
        email = EmailNotifier(settings)
        web = WebPushNotifier(settings)
        apns = ApnsPushNotifier(settings)
        registry = NotifierRegistry(email, web, apns)

        user = _make_user()
        user.devices = [_make_ios_device(user.id)]
        alert = _make_alert(user_id=user.id)

        with (
            patch.object(email, "send", new_callable=AsyncMock, return_value=True),
            patch.object(web, "send", new_callable=AsyncMock) as m_web,
            patch.object(apns, "send", new_callable=AsyncMock, return_value=True),
        ):
            results = await registry.notify(alert, user)

        assert results == {"email": True, "apns": True}
        m_web.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_partial_failure(self, settings: Settings) -> None:
        """When one channel fails, others still report correctly."""
        email = EmailNotifier(settings)
        web = WebPushNotifier(settings)
        apns = ApnsPushNotifier(settings)
        registry = NotifierRegistry(email, web, apns)

        user = _make_user()
        user.devices = [
            _make_web_device(user.id),
            _make_ios_device(user.id),
        ]
        alert = _make_alert(user_id=user.id)

        with (
            patch.object(email, "send", new_callable=AsyncMock, return_value=True),
            patch.object(web, "send", new_callable=AsyncMock, return_value=False),
            patch.object(apns, "send", new_callable=AsyncMock, return_value=True),
        ):
            results = await registry.notify(alert, user)

        assert results == {"email": True, "web_push": False, "apns": True}

    @pytest.mark.asyncio
    async def test_dispatch_channel_exception(self, settings: Settings) -> None:
        """When a channel raises an unhandled exception, it returns False."""
        email = EmailNotifier(settings)
        web = WebPushNotifier(settings)
        apns = ApnsPushNotifier(settings)
        registry = NotifierRegistry(email, web, apns)

        user = _make_user()
        user.devices = [_make_web_device(user.id)]
        alert = _make_alert(user_id=user.id)

        with (
            patch.object(email, "send", new_callable=AsyncMock, return_value=True),
            patch.object(
                web,
                "send",
                new_callable=AsyncMock,
                side_effect=RuntimeError("unexpected"),
            ),
        ):
            results = await registry.notify(alert, user)

        assert results["email"] is True
        assert results["web_push"] is False
