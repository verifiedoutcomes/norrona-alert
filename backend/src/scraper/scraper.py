from __future__ import annotations

import abc
import asyncio
import random
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
import structlog
from bs4 import BeautifulSoup, Tag

from backend.src.config import settings
from backend.src.contracts.models import Locale, ProductSnapshot

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_USER_AGENTS: list[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
        "Gecko/20100101 Firefox/121.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2; rv:121.0) "
        "Gecko/20100101 Firefox/121.0"
    ),
]

_MAX_RETRIES: int = 3
_BACKOFF_BASE_SECONDS: float = 2.0
_PRODUCT_CARD_SELECTOR: str = "li.product-card, div.product-card, article.product-card"
_PRODUCT_LINK_SELECTOR: str = "a.product-card__link, a.product-card__image-link, a[href*='/products/']"
_PRODUCT_NAME_SELECTOR: str = (
    "h3.product-card__title, span.product-card__title, "
    "h2.product-card__title, .product-card__name"
)
_PRODUCT_PRICE_SELECTOR: str = (
    "span.product-card__price--sale, span.product-card__price--current, "
    ".product-card__price--now, .price--sale"
)
_PRODUCT_ORIGINAL_PRICE_SELECTOR: str = (
    "span.product-card__price--original, span.product-card__price--was, "
    ".product-card__price--before, .price--original"
)
_PRODUCT_SIZE_SELECTOR: str = (
    "ul.product-card__sizes li, .product-card__sizes span, "
    ".product-card__size-list span, .size-option"
)
_PRODUCT_IMAGE_SELECTOR: str = "img.product-card__image, img.product-card__img, .product-card img"
_PRODUCT_CATEGORY_SELECTOR: str = (
    "span.product-card__category, .product-card__category, "
    ".product-card__type"
)


def _random_user_agent() -> str:
    return random.choice(_USER_AGENTS)


def _parse_price(text: str) -> float:
    """Extract a numeric price from text like '£149.00', 'kr 1 299,-', '149,00'."""
    cleaned = text.strip()
    # Remove currency symbols and words
    for char in ("£", "$", "€", "kr", "NOK", "GBP", ",-"):
        cleaned = cleaned.replace(char, "")
    cleaned = cleaned.strip()
    # Handle European format: "1 299" or "1.299" (thousands) with "," as decimal
    if "," in cleaned and "." in cleaned:
        # e.g. "1.299,00" -> "1299.00"
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            # e.g. "149,00" -> "149.00"
            cleaned = cleaned.replace(",", ".")
        else:
            # e.g. "1,299" -> "1299"
            cleaned = cleaned.replace(",", "")
    # Remove spaces used as thousands separators
    cleaned = cleaned.replace(" ", "").replace("\xa0", "")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _compute_discount_pct(original: float, current: float) -> float:
    if original <= 0:
        return 0.0
    discount = ((original - current) / original) * 100.0
    return round(max(discount, 0.0), 1)


class BaseScraper(abc.ABC):
    """Abstract base scraper implementing common logic for Norrona outlet pages."""

    def __init__(self) -> None:
        self._last_request_time: float = 0.0
        self._last_scrape_time: float = 0.0
        self._robots_parser: RobotFileParser | None = None
        self._robots_checked: bool = False

    @property
    @abc.abstractmethod
    def locale(self) -> Locale:
        ...

    @property
    @abc.abstractmethod
    def outlet_url(self) -> str:
        ...

    @property
    def base_url(self) -> str:
        parsed = urlparse(self.outlet_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def robots_url(self) -> str:
        return urljoin(self.base_url, "/robots.txt")

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={
                "User-Agent": _random_user_agent(),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": self.locale.value,
            },
            follow_redirects=True,
            timeout=httpx.Timeout(30.0),
        )

    async def _enforce_request_delay(self) -> None:
        """Ensure minimum delay between individual HTTP requests."""
        min_delay = float(settings.scrape_min_delay_seconds)
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < min_delay:
            wait = min_delay - elapsed
            log = logger.bind(wait_seconds=round(wait, 1))
            log.debug("rate_limit_wait")
            await asyncio.sleep(wait)
        self._last_request_time = time.monotonic()

    async def _check_robots_txt(self) -> bool:
        """Return True if scraping the outlet URL is allowed by robots.txt."""
        if self._robots_checked:
            return self._robots_parser is not None and self._robots_parser.can_fetch(
                _USER_AGENTS[0], self.outlet_url
            )

        log = logger.bind(robots_url=self.robots_url)
        try:
            async with self._build_client() as client:
                response = await client.get(self.robots_url)
                if response.status_code == 200:
                    parser = RobotFileParser()
                    parser.parse(response.text.splitlines())
                    self._robots_parser = parser
                    self._robots_checked = True
                    allowed = parser.can_fetch(_USER_AGENTS[0], self.outlet_url)
                    log.info("robots_txt_checked", allowed=allowed)
                    return allowed
                else:
                    # No robots.txt or error fetching it -> assume allowed
                    log.info("robots_txt_not_found", status_code=response.status_code)
                    self._robots_checked = True
                    self._robots_parser = RobotFileParser()
                    self._robots_parser.parse([])
                    return True
        except httpx.HTTPError as exc:
            log.warning("robots_txt_fetch_error", error=str(exc))
            self._robots_checked = True
            self._robots_parser = RobotFileParser()
            self._robots_parser.parse([])
            return True

    async def _fetch_html(self, url: str) -> str:
        """Fetch page HTML via httpx with retries and exponential backoff."""
        last_error: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            await self._enforce_request_delay()
            log = logger.bind(url=url, attempt=attempt)
            try:
                async with self._build_client() as client:
                    response = await client.get(url)
                    response.raise_for_status()
                    log.info("page_fetched", status_code=response.status_code)
                    return response.text
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                backoff = _BACKOFF_BASE_SECONDS ** attempt
                log.warning(
                    "fetch_retry",
                    error=str(exc),
                    backoff_seconds=backoff,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(backoff)

        raise RuntimeError(
            f"Failed to fetch {url} after {_MAX_RETRIES} retries"
        ) from last_error

    async def _fetch_with_playwright(self, url: str) -> str:
        """Fall back to Playwright for JS-rendered pages."""
        log = logger.bind(url=url)
        log.info("playwright_fallback_start")
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(
                        user_agent=_random_user_agent(),
                        locale=self.locale.value,
                    )
                    page = await context.new_page()
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    # Wait for product cards to appear
                    await page.wait_for_selector(
                        _PRODUCT_CARD_SELECTOR,
                        timeout=15000,
                    )
                    html = await page.content()
                    log.info("playwright_fallback_success")
                    return html
                finally:
                    await browser.close()
        except Exception as exc:
            log.error("playwright_fallback_failed", error=str(exc))
            raise RuntimeError(
                f"Playwright fallback failed for {url}: {exc}"
            ) from exc

    def parse_products(self, html: str) -> list[ProductSnapshot]:
        """Parse product data from outlet page HTML."""
        soup = BeautifulSoup(html, "lxml")
        cards: list[Tag] = soup.select(_PRODUCT_CARD_SELECTOR)
        products: list[ProductSnapshot] = []
        now = datetime.now(tz=timezone.utc)

        for card in cards:
            try:
                product = self._parse_single_card(card, now)
                if product is not None:
                    products.append(product)
            except Exception:
                logger.warning(
                    "product_parse_error",
                    card_html=str(card)[:200],
                    exc_info=True,
                )

        logger.info("products_parsed", count=len(products), locale=self.locale.value)
        return products

    def _parse_single_card(self, card: Tag, now: datetime) -> ProductSnapshot | None:
        """Parse a single product card element into a ProductSnapshot."""
        # Product URL and name
        link_el = card.select_one(_PRODUCT_LINK_SELECTOR)
        if link_el is None:
            return None

        raw_href = link_el.get("href", "")
        href: str = raw_href if isinstance(raw_href, str) else str(raw_href)
        if not href:
            return None
        product_url = href if href.startswith("http") else urljoin(self.base_url, href)

        name_el = card.select_one(_PRODUCT_NAME_SELECTOR)
        name = name_el.get_text(strip=True) if name_el else ""
        if not name:
            # Try link text as fallback
            name = link_el.get_text(strip=True)
        if not name:
            return None

        # Prices
        price_el = card.select_one(_PRODUCT_PRICE_SELECTOR)
        price = _parse_price(price_el.get_text()) if price_el else 0.0

        orig_price_el = card.select_one(_PRODUCT_ORIGINAL_PRICE_SELECTOR)
        original_price = _parse_price(orig_price_el.get_text()) if orig_price_el else price

        # Sizes
        size_els = card.select(_PRODUCT_SIZE_SELECTOR)
        available_sizes = [s.get_text(strip=True) for s in size_els if s.get_text(strip=True)]

        # Category
        category_el = card.select_one(_PRODUCT_CATEGORY_SELECTOR)
        category = category_el.get_text(strip=True) if category_el else self._infer_category(name)

        # Image
        img_el = card.select_one(_PRODUCT_IMAGE_SELECTOR)
        image_url = ""
        if img_el:
            raw_src = img_el.get("src") or img_el.get("data-src") or ""
            src: str = raw_src if isinstance(raw_src, str) else str(raw_src)
            image_url = src if src.startswith("http") else urljoin(self.base_url, src) if src else ""

        discount_pct = _compute_discount_pct(original_price, price)

        return ProductSnapshot(
            name=name,
            url=product_url,
            price=price,
            original_price=original_price,
            discount_pct=discount_pct,
            available_sizes=available_sizes,
            category=category,
            image_url=image_url,
            locale=self.locale,
            scraped_at=now,
        )

    @staticmethod
    def _infer_category(name: str) -> str:
        """Infer product category from name when no explicit category element exists."""
        lower = name.lower()
        category_keywords: dict[str, list[str]] = {
            "Jackets": ["jacket", "anorak", "parka", "coat", "shell"],
            "Pants": ["pant", "trouser", "bibs"],
            "Fleece": ["fleece", "midlayer"],
            "Base Layer": ["base layer", "wool", "merino", "superlight"],
            "Shirts": ["shirt", "tee", "t-shirt"],
            "Shorts": ["short"],
            "Accessories": ["hat", "cap", "glove", "beanie", "headband", "belt", "gaiter"],
            "Bags": ["bag", "pack", "backpack", "duffel"],
            "Footwear": ["boot", "shoe"],
            "Skirts & Dresses": ["skirt", "dress"],
            "Vests": ["vest", "gilet"],
        }
        for category, keywords in category_keywords.items():
            if any(kw in lower for kw in keywords):
                return category
        return "Other"

    async def scrape(self, locale: str) -> list[ProductSnapshot]:
        """Full scrape pipeline: check robots, fetch, parse, with JS fallback."""
        log = logger.bind(locale=locale, url=self.outlet_url)

        # Enforce minimum interval between full scrapes
        interval = float(settings.scrape_interval_minutes * 60)
        elapsed_since_last = time.monotonic() - self._last_scrape_time
        if self._last_scrape_time > 0 and elapsed_since_last < interval:
            remaining = interval - elapsed_since_last
            log.info("scrape_throttled", remaining_seconds=round(remaining, 0))
            return []

        # Check robots.txt
        allowed = await self._check_robots_txt()
        if not allowed:
            log.warning("scrape_blocked_by_robots_txt")
            return []

        # Fetch HTML
        html = await self._fetch_html(self.outlet_url)

        # Parse products
        products = self.parse_products(html)

        # Fall back to Playwright if no products found (JS rendering needed)
        if not products:
            log.info("no_products_found_trying_playwright")
            html = await self._fetch_with_playwright(self.outlet_url)
            products = self.parse_products(html)

        self._last_scrape_time = time.monotonic()
        log.info("scrape_complete", product_count=len(products))
        return products


class UKScraper(BaseScraper):
    """Scraper for the Norrona UK outlet (en-GB)."""

    @property
    def locale(self) -> Locale:
        return Locale.EN_GB

    @property
    def outlet_url(self) -> str:
        return "https://www.norrona.com/en-GB/outlet/"


class NorwayScraper(BaseScraper):
    """Scraper for the Norrona Norway outlet (nb-NO)."""

    @property
    def locale(self) -> Locale:
        return Locale.NB_NO

    @property
    def outlet_url(self) -> str:
        return "https://www.norrona.com/nb-NO/outlet/"
