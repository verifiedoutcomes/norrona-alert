from __future__ import annotations

import asyncio

import structlog

from backend.src.contracts.models import AlertSchema, Platform, User
from backend.src.notifier.apns_notifier import ApnsPushNotifier
from backend.src.notifier.email_notifier import EmailNotifier
from backend.src.notifier.web_push_notifier import WebPushNotifier

logger = structlog.get_logger(__name__)


class NotifierRegistry:
    """Adapter that dispatches alerts to the correct notification channels.

    Adding a new channel requires only adding a new notifier class and
    registering it here -- no existing code needs to change.
    """

    def __init__(
        self,
        email_notifier: EmailNotifier,
        web_push_notifier: WebPushNotifier,
        apns_notifier: ApnsPushNotifier,
    ) -> None:
        self._email = email_notifier
        self._web_push = web_push_notifier
        self._apns = apns_notifier

    async def notify(self, alert: AlertSchema, user: User) -> dict[str, bool]:
        """Dispatch the alert to all relevant channels for the given user.

        Returns a dict mapping channel name to success boolean.
        - ``email`` is always sent (every user has an email).
        - ``web_push`` is sent if the user has any device registrations
          with platform ``web``.
        - ``apns`` is sent if the user has any device registrations with
          platform ``ios``.
        """
        log = logger.bind(user_id=str(user.id), alert_rule=alert.matched_rule)

        tasks: dict[str, asyncio.Task[bool]] = {}

        # Email is always sent
        tasks["email"] = asyncio.create_task(self._email.send(alert, user))

        has_web = any(d.platform == Platform.WEB for d in user.devices)
        if has_web:
            tasks["web_push"] = asyncio.create_task(self._web_push.send(alert, user))

        has_ios = any(d.platform == Platform.IOS for d in user.devices)
        if has_ios:
            tasks["apns"] = asyncio.create_task(self._apns.send(alert, user))

        results: dict[str, bool] = {}
        for channel, task in tasks.items():
            try:
                results[channel] = await task
            except Exception as exc:  # noqa: BLE001
                log.error("notify_channel_error", channel=channel, error=str(exc))
                results[channel] = False

        log.info("notify_complete", results=results)
        return results
