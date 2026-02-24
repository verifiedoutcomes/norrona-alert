from __future__ import annotations

import asyncio
import json

import structlog
from pywebpush import webpush

from backend.src.config import Settings
from backend.src.contracts.models import AlertSchema, DeviceRegistration, Platform, User

logger = structlog.get_logger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0


def build_web_push_payload(alert: AlertSchema, frontend_url: str) -> str:
    """Build the JSON payload for a web push notification."""
    product = alert.product_change.new_state
    return json.dumps(
        {
            "title": "Norr\u00f8na Alert",
            "body": f"{product.name} \u2013 {product.price:.2f} NOK",
            "url": product.url,
            "icon": product.image_url,
        },
        ensure_ascii=False,
    )


class WebPushNotifier:
    """INotifier implementation that sends browser push notifications via pywebpush."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, alert: AlertSchema, user: User) -> bool:
        web_devices: list[DeviceRegistration] = [
            d for d in user.devices if d.platform == Platform.WEB
        ]

        if not web_devices:
            return True

        payload = build_web_push_payload(alert, self._settings.frontend_url)
        all_succeeded = True

        for device in web_devices:
            success = await self._send_to_device(device, payload, user)
            if not success:
                all_succeeded = False

        return all_succeeded

    async def _send_to_device(
        self,
        device: DeviceRegistration,
        payload: str,
        user: User,
    ) -> bool:
        log = logger.bind(
            user_id=str(user.id),
            device_id=str(device.id),
            channel="web_push",
        )

        subscription_info = json.loads(device.device_token)

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                await asyncio.to_thread(
                    webpush,
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=self._settings.vapid_private_key,
                    vapid_claims={"sub": self._settings.vapid_claims_email},
                )
                log.info("web_push_sent", attempt=attempt + 1)
                return True
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                delay = _BASE_DELAY * (2**attempt)
                log.warning(
                    "web_push_send_failed",
                    attempt=attempt + 1,
                    error=str(exc),
                    retry_in=delay,
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(delay)

        log.error("web_push_send_exhausted", error=str(last_exc))
        return False
