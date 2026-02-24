from __future__ import annotations

import asyncio

import structlog
from aioapns import APNs, NotificationRequest

from backend.src.config import Settings
from backend.src.contracts.models import AlertSchema, DeviceRegistration, Platform, User

logger = structlog.get_logger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0


def build_apns_notification(
    alert: AlertSchema,
    device_token: str,
    bundle_id: str,
) -> NotificationRequest:
    """Build an APNs NotificationRequest with rich notification support."""
    product = alert.product_change.new_state
    return NotificationRequest(
        device_token=device_token,
        message={
            "aps": {
                "alert": {
                    "title": "Norr\u00f8na Alert",
                    "body": f"{product.name} \u2013 {product.price:.2f} NOK",
                },
                "sound": "default",
                "mutable-content": 1,
            },
            "product_url": product.url,
            "image_url": product.image_url,
            "product_name": product.name,
            "price": product.price,
        },
        apns_topic=bundle_id,
    )


class ApnsPushNotifier:
    """INotifier implementation that sends iOS push notifications via APNs."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: APNs | None = None

    def _get_client(self) -> APNs:
        if self._client is None:
            self._client = APNs(
                key=self._settings.apns_auth_key_path,
                key_id=self._settings.apns_auth_key_id,
                team_id=self._settings.apns_team_id,
                topic=self._settings.apns_bundle_id,
                use_sandbox=self._settings.apns_use_sandbox,
            )
        return self._client

    async def send(self, alert: AlertSchema, user: User) -> bool:
        ios_devices: list[DeviceRegistration] = [
            d for d in user.devices if d.platform == Platform.IOS
        ]

        if not ios_devices:
            return True

        all_succeeded = True
        for device in ios_devices:
            success = await self._send_to_device(device, alert, user)
            if not success:
                all_succeeded = False

        return all_succeeded

    async def _send_to_device(
        self,
        device: DeviceRegistration,
        alert: AlertSchema,
        user: User,
    ) -> bool:
        log = logger.bind(
            user_id=str(user.id),
            device_id=str(device.id),
            channel="apns",
        )

        notification = build_apns_notification(
            alert=alert,
            device_token=device.device_token,
            bundle_id=self._settings.apns_bundle_id,
        )

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                client = self._get_client()
                result = await client.send_notification(notification)
                if result.is_successful:
                    log.info("apns_sent", attempt=attempt + 1)
                    return True
                log.warning(
                    "apns_rejected",
                    attempt=attempt + 1,
                    reason=result.description,
                )
                last_exc = RuntimeError(f"APNs rejected: {result.description}")
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                log.warning(
                    "apns_send_failed",
                    attempt=attempt + 1,
                    error=str(exc),
                )

            if attempt < _MAX_RETRIES - 1:
                delay = _BASE_DELAY * (2**attempt)
                log.warning("apns_retrying", retry_in=delay)
                await asyncio.sleep(delay)

        log.error("apns_send_exhausted", error=str(last_exc))
        return False
