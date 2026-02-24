from __future__ import annotations

import asyncio

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from backend.src.api.database import async_session_factory
from backend.src.config import settings
from backend.src.contracts.models import Locale
from backend.src.differ.differ import ProductDiffer
from backend.src.matcher.matcher import PreferenceMatcher
from backend.src.notifier.apns_notifier import ApnsPushNotifier
from backend.src.notifier.email_notifier import EmailNotifier
from backend.src.notifier.registry import NotifierRegistry
from backend.src.notifier.web_push_notifier import WebPushNotifier
from backend.src.products.repository import ProductRepository
from backend.src.scraper.scraper import NorwayScraper, UKScraper
from backend.src.users.repository import UserRepository

logger = structlog.get_logger(__name__)


class AlertScheduler:
    """Orchestrates periodic scraping, diffing, matching, and notification dispatch."""

    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._differ = ProductDiffer()
        self._matcher = PreferenceMatcher()
        self._scrapers = {
            Locale.EN_GB: UKScraper(),
            Locale.NB_NO: NorwayScraper(),
        }
        self._notifier = NotifierRegistry(
            email_notifier=EmailNotifier(settings),
            web_push_notifier=WebPushNotifier(settings),
            apns_notifier=ApnsPushNotifier(settings),
        )

    def start(self) -> None:
        self._scheduler.add_job(
            self._run_cycle,
            trigger=IntervalTrigger(minutes=settings.scrape_interval_minutes),
            id="alert_cycle",
            name="Scrape outlets and send alerts",
            replace_existing=True,
            next_run_time=None,  # Don't run immediately; let first interval pass
        )
        self._scheduler.start()
        logger.info(
            "scheduler_configured",
            interval_minutes=settings.scrape_interval_minutes,
        )

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        logger.info("scheduler_shutdown")

    async def trigger_now(self) -> None:
        """Manually trigger an alert cycle (useful for testing or admin endpoints)."""
        await self._run_cycle()

    async def _run_cycle(self) -> None:
        logger.info("alert_cycle_start")

        for locale, scraper in self._scrapers.items():
            try:
                await self._process_locale(locale, scraper)
            except Exception:
                logger.error(
                    "alert_cycle_locale_error",
                    locale=locale.value,
                    exc_info=True,
                )

        logger.info("alert_cycle_complete")

    async def _process_locale(self, locale: Locale, scraper: UKScraper | NorwayScraper) -> None:
        log = logger.bind(locale=locale.value)

        # 1. Scrape
        new_products = await scraper.scrape(locale.value)
        if not new_products:
            log.info("no_products_scraped")
            return

        log.info("products_scraped", count=len(new_products))

        async with async_session_factory() as session:
            product_repo = ProductRepository(session)
            user_repo = UserRepository(session)

            # 2. Get previous snapshot for diffing
            old_rows = await product_repo.get_latest_by_locale(locale.value)
            old_products = [row.to_schema() for row in old_rows]

            # 3. Diff
            changes = self._differ.diff(old_products, new_products)
            log.info("changes_detected", count=len(changes))

            # 4. Persist new snapshot
            await product_repo.bulk_upsert(new_products)
            await session.commit()
            log.info("snapshot_persisted")

            if not changes:
                return

            # 5. Match against all users and notify
            users = await user_repo.get_all_with_devices()
            log.info("users_to_check", count=len(users))

            for user in users:
                preferences = user.get_preferences()

                # Only alert users whose region matches this locale
                if preferences.region != locale:
                    continue

                alerts = self._matcher.match(changes, preferences, user.id)
                if not alerts:
                    continue

                log.info(
                    "sending_alerts",
                    user_id=str(user.id),
                    alert_count=len(alerts),
                )

                for alert in alerts:
                    try:
                        await self._notifier.notify(alert, user)
                    except Exception:
                        log.error(
                            "notify_error",
                            user_id=str(user.id),
                            product=alert.product_change.new_state.name,
                            exc_info=True,
                        )
