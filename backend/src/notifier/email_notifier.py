from __future__ import annotations

import asyncio

import resend
import structlog

from backend.src.config import Settings
from backend.src.contracts.models import (
    AlertSchema,
    Locale,
    User,
    UserPreferences,
)

logger = structlog.get_logger(__name__)

_MAX_RETRIES = 3
_BASE_DELAY = 1.0


def _build_subject(product_name: str, locale: Locale) -> str:
    if locale == Locale.NB_NO:
        return f"Prisvarsel: {product_name}"
    return f"Price Alert: {product_name}"


def render_email_html(
    alert: AlertSchema,
    user_email: str,
    preferences: UserPreferences,
    frontend_url: str,
) -> str:
    """Render a clean HTML email template for the price alert.

    Returns Norwegian template for nb-NO users, English for all others.
    """
    product = alert.product_change.new_state
    locale = preferences.region
    change_type = alert.product_change.change_type.value

    product_url = product.url
    unsubscribe_url = f"{frontend_url}/unsubscribe?email={user_email}"
    discount_display = f"{product.discount_pct:.0f}"

    if locale == Locale.NB_NO:
        return _render_nb_no(
            product_name=product.name,
            product_url=product_url,
            image_url=product.image_url,
            price=product.price,
            original_price=product.original_price,
            discount_display=discount_display,
            change_type=change_type,
            unsubscribe_url=unsubscribe_url,
        )
    return _render_en_gb(
        product_name=product.name,
        product_url=product_url,
        image_url=product.image_url,
        price=product.price,
        original_price=product.original_price,
        discount_display=discount_display,
        change_type=change_type,
        unsubscribe_url=unsubscribe_url,
    )


def _render_en_gb(
    product_name: str,
    product_url: str,
    image_url: str,
    price: float,
    original_price: float,
    discount_display: str,
    change_type: str,
    unsubscribe_url: str,
) -> str:
    change_labels = {
        "price_drop": "Price Drop",
        "new": "New Product",
        "restock": "Back in Stock",
    }
    change_label = change_labels.get(change_type, change_type.replace("_", " ").title())

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:24px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;">
  <tr><td style="background:#1a1a2e;padding:20px 24px;color:#ffffff;font-size:20px;font-weight:bold;">
    Norr&oslash;na Alert
  </td></tr>
  <tr><td style="padding:0;">
    <img src="{image_url}" alt="{product_name}" width="600" style="display:block;width:100%;height:auto;">
  </td></tr>
  <tr><td style="padding:24px;">
    <span style="display:inline-block;background:#e0f2fe;color:#0369a1;font-size:12px;font-weight:600;padding:4px 10px;border-radius:4px;margin-bottom:12px;">{change_label}</span>
    <h1 style="margin:12px 0 8px;font-size:22px;color:#1a1a2e;">{product_name}</h1>
    <p style="margin:0 0 16px;font-size:28px;font-weight:bold;color:#16a34a;">
      {price:.2f} NOK
      <span style="font-size:16px;color:#9ca3af;text-decoration:line-through;margin-left:8px;">{original_price:.2f} NOK</span>
      <span style="font-size:14px;color:#dc2626;margin-left:8px;">-{discount_display}%</span>
    </p>
    <a href="{product_url}" style="display:inline-block;background:#1a1a2e;color:#ffffff;text-decoration:none;padding:12px 32px;border-radius:6px;font-size:16px;font-weight:600;">View Product</a>
  </td></tr>
  <tr><td style="padding:16px 24px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;text-align:center;">
    You received this because you set up an alert on Norr&oslash;na Alert.<br>
    <a href="{unsubscribe_url}" style="color:#6b7280;">Unsubscribe</a>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


def _render_nb_no(
    product_name: str,
    product_url: str,
    image_url: str,
    price: float,
    original_price: float,
    discount_display: str,
    change_type: str,
    unsubscribe_url: str,
) -> str:
    change_labels = {
        "price_drop": "Prisfall",
        "new": "Nytt produkt",
        "restock": "Tilbake p\u00e5 lager",
    }
    change_label = change_labels.get(change_type, change_type.replace("_", " ").title())

    return f"""\
<!DOCTYPE html>
<html lang="nb">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:24px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;">
  <tr><td style="background:#1a1a2e;padding:20px 24px;color:#ffffff;font-size:20px;font-weight:bold;">
    Norr&oslash;na Alert
  </td></tr>
  <tr><td style="padding:0;">
    <img src="{image_url}" alt="{product_name}" width="600" style="display:block;width:100%;height:auto;">
  </td></tr>
  <tr><td style="padding:24px;">
    <span style="display:inline-block;background:#e0f2fe;color:#0369a1;font-size:12px;font-weight:600;padding:4px 10px;border-radius:4px;margin-bottom:12px;">{change_label}</span>
    <h1 style="margin:12px 0 8px;font-size:22px;color:#1a1a2e;">{product_name}</h1>
    <p style="margin:0 0 16px;font-size:28px;font-weight:bold;color:#16a34a;">
      {price:.2f} NOK
      <span style="font-size:16px;color:#9ca3af;text-decoration:line-through;margin-left:8px;">{original_price:.2f} NOK</span>
      <span style="font-size:14px;color:#dc2626;margin-left:8px;">-{discount_display}%</span>
    </p>
    <a href="{product_url}" style="display:inline-block;background:#1a1a2e;color:#ffffff;text-decoration:none;padding:12px 32px;border-radius:6px;font-size:16px;font-weight:600;">Se produkt</a>
  </td></tr>
  <tr><td style="padding:16px 24px;background:#f9fafb;border-top:1px solid #e5e7eb;font-size:12px;color:#9ca3af;text-align:center;">
    Du mottar denne e-posten fordi du har satt opp et varsel p&aring; Norr&oslash;na Alert.<br>
    <a href="{unsubscribe_url}" style="color:#6b7280;">Avmeld</a>
  </td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


class EmailNotifier:
    """INotifier implementation that sends email alerts via the Resend API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        resend.api_key = settings.resend_api_key

    async def send(self, alert: AlertSchema, user: User) -> bool:
        preferences = user.get_preferences()
        product = alert.product_change.new_state

        html = render_email_html(
            alert=alert,
            user_email=user.email,
            preferences=preferences,
            frontend_url=self._settings.frontend_url,
        )
        subject = _build_subject(product.name, preferences.region)

        log = logger.bind(
            user_id=str(user.id),
            email=user.email,
            product=product.name,
            channel="email",
        )

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                await asyncio.to_thread(
                    resend.Emails.send,
                    {
                        "from": self._settings.resend_from_email,
                        "to": [user.email],
                        "subject": subject,
                        "html": html,
                    },
                )
                log.info("email_sent", attempt=attempt + 1)
                return True
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                delay = _BASE_DELAY * (2**attempt)
                log.warning(
                    "email_send_failed",
                    attempt=attempt + 1,
                    error=str(exc),
                    retry_in=delay,
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(delay)

        log.error("email_send_exhausted", error=str(last_exc))
        return False
