from __future__ import annotations

import asyncio
import pathlib
import time
from typing import Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.src.contracts.models import Locale, ProductSnapshot
from backend.src.scraper.scraper import (
    BaseScraper,
    NorwayScraper,
    UKScraper,
    _compute_discount_pct,
    _parse_price,
)

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def uk_scraper() -> UKScraper:
    scraper = UKScraper()
    # Reset timing so tests are not throttled
    scraper._last_request_time = 0.0
    scraper._last_scrape_time = 0.0
    return scraper


@pytest.fixture
def norway_scraper() -> NorwayScraper:
    scraper = NorwayScraper()
    scraper._last_request_time = 0.0
    scraper._last_scrape_time = 0.0
    return scraper


@pytest.fixture
def en_gb_html() -> str:
    return _load_fixture("outlet_en_gb.html")


@pytest.fixture
def nb_no_html() -> str:
    return _load_fixture("outlet_nb_no.html")


@pytest.fixture
def empty_html() -> str:
    return _load_fixture("outlet_empty.html")


@pytest.fixture
def partial_html() -> str:
    return _load_fixture("outlet_partial.html")


# ── Price parsing tests ──────────────────────────────────────────────────────


class TestParsePrice:
    def test_gbp_price(self) -> None:
        assert _parse_price("£280.00") == 280.00

    def test_nok_price_with_thousands_separator(self) -> None:
        assert _parse_price("kr 3 499,-") == 3499.0

    def test_nok_price_large(self) -> None:
        assert _parse_price("kr 5 499,-") == 5499.0

    def test_european_decimal_comma(self) -> None:
        assert _parse_price("149,00") == 149.00

    def test_european_thousands_dot_decimal_comma(self) -> None:
        assert _parse_price("1.299,00") == 1299.00

    def test_plain_number(self) -> None:
        assert _parse_price("100") == 100.0

    def test_empty_string(self) -> None:
        assert _parse_price("") == 0.0

    def test_non_numeric_string(self) -> None:
        assert _parse_price("N/A") == 0.0

    def test_gbp_symbol_only(self) -> None:
        assert _parse_price("£") == 0.0


class TestComputeDiscountPct:
    def test_standard_discount(self) -> None:
        assert _compute_discount_pct(400.0, 280.0) == 30.0

    def test_no_discount(self) -> None:
        assert _compute_discount_pct(100.0, 100.0) == 0.0

    def test_zero_original(self) -> None:
        assert _compute_discount_pct(0.0, 50.0) == 0.0

    def test_higher_current_than_original(self) -> None:
        assert _compute_discount_pct(100.0, 150.0) == 0.0


# ── Product parsing tests ────────────────────────────────────────────────────


class TestUKScraperParsing:
    def test_parses_all_products(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        assert len(products) == 5

    def test_product_names(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        names = [p.name for p in products]
        assert "falketind Gore-Tex Jacket Men" in names
        assert "lyngen down850 Hood Jacket Women" in names
        assert "bitihorn flex1 Pants Men" in names
        assert "trollveggen Thermal Pro Fleece Jacket Men" in names
        assert "svalbard Wool Beanie" in names

    def test_product_urls(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        jacket = _find_product(products, "falketind Gore-Tex Jacket Men")
        assert jacket.url == "https://www.norrona.com/en-GB/products/falketind-gore-tex-jacket-men-1234"

    def test_product_prices(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        jacket = _find_product(products, "falketind Gore-Tex Jacket Men")
        assert jacket.price == 280.00
        assert jacket.original_price == 400.00

    def test_product_discount(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        jacket = _find_product(products, "falketind Gore-Tex Jacket Men")
        assert jacket.discount_pct == 30.0

    def test_product_sizes(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        jacket = _find_product(products, "falketind Gore-Tex Jacket Men")
        assert jacket.available_sizes == ["S", "M", "L", "XL"]

    def test_product_category(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        jacket = _find_product(products, "falketind Gore-Tex Jacket Men")
        assert jacket.category == "Jackets"

    def test_product_image_url(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        jacket = _find_product(products, "falketind Gore-Tex Jacket Men")
        assert jacket.image_url == "https://images.norrona.com/falketind-gore-tex-jacket.jpg"

    def test_product_locale(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        for product in products:
            assert product.locale == Locale.EN_GB

    def test_beanie_sizes(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        beanie = _find_product(products, "svalbard Wool Beanie")
        assert beanie.available_sizes == ["One Size"]

    def test_beanie_category(self, uk_scraper: UKScraper, en_gb_html: str) -> None:
        products = uk_scraper.parse_products(en_gb_html)
        beanie = _find_product(products, "svalbard Wool Beanie")
        assert beanie.category == "Accessories"


class TestNorwayScraperParsing:
    def test_parses_all_products(self, norway_scraper: NorwayScraper, nb_no_html: str) -> None:
        products = norway_scraper.parse_products(nb_no_html)
        assert len(products) == 3

    def test_nok_price_parsing(self, norway_scraper: NorwayScraper, nb_no_html: str) -> None:
        products = norway_scraper.parse_products(nb_no_html)
        jacket = _find_product(products, "falketind Gore-Tex Jacket Herre")
        assert jacket.price == 3499.0
        assert jacket.original_price == 4999.0

    def test_product_locale_nb_no(self, norway_scraper: NorwayScraper, nb_no_html: str) -> None:
        products = norway_scraper.parse_products(nb_no_html)
        for product in products:
            assert product.locale == Locale.NB_NO

    def test_norway_product_urls(self, norway_scraper: NorwayScraper, nb_no_html: str) -> None:
        products = norway_scraper.parse_products(nb_no_html)
        jacket = _find_product(products, "falketind Gore-Tex Jacket Herre")
        assert jacket.url == "https://www.norrona.com/nb-NO/products/falketind-gore-tex-jakke-herre-1234"

    def test_norway_discount_calculation(
        self, norway_scraper: NorwayScraper, nb_no_html: str
    ) -> None:
        products = norway_scraper.parse_products(nb_no_html)
        jacket = _find_product(products, "falketind Gore-Tex Jacket Herre")
        # (4999 - 3499) / 4999 * 100 = 30.0%
        assert jacket.discount_pct == 30.0


class TestPartialProducts:
    def test_skips_products_without_name(self, uk_scraper: UKScraper, partial_html: str) -> None:
        products = uk_scraper.parse_products(partial_html)
        names = [p.name for p in products]
        # Product 3002 (empty name) and 3003 (no link) should be skipped
        assert len(products) == 3
        assert "lofoten Gore-Tex Pro Jacket Men" in names
        assert "bitihorn lightweight Shorts Men" in names
        assert "/29 cotton T-Shirt Men" in names

    def test_infers_category_from_name(self, uk_scraper: UKScraper, partial_html: str) -> None:
        products = uk_scraper.parse_products(partial_html)
        shorts = _find_product(products, "bitihorn lightweight Shorts Men")
        assert shorts.category == "Shorts"

    def test_product_without_sizes_has_empty_list(
        self, uk_scraper: UKScraper, partial_html: str
    ) -> None:
        products = uk_scraper.parse_products(partial_html)
        tshirt = _find_product(products, "/29 cotton T-Shirt Men")
        assert tshirt.available_sizes == []


class TestEmptyProductList:
    def test_empty_page_returns_no_products(
        self, uk_scraper: UKScraper, empty_html: str
    ) -> None:
        products = uk_scraper.parse_products(empty_html)
        assert products == []


# ── Scraper property tests ───────────────────────────────────────────────────


class TestScraperProperties:
    def test_uk_scraper_locale(self) -> None:
        scraper = UKScraper()
        assert scraper.locale == Locale.EN_GB

    def test_norway_scraper_locale(self) -> None:
        scraper = NorwayScraper()
        assert scraper.locale == Locale.NB_NO

    def test_uk_scraper_outlet_url(self) -> None:
        scraper = UKScraper()
        assert scraper.outlet_url == "https://www.norrona.com/en-GB/outlet/"

    def test_norway_scraper_outlet_url(self) -> None:
        scraper = NorwayScraper()
        assert scraper.outlet_url == "https://www.norrona.com/nb-NO/outlet/"

    def test_base_url(self) -> None:
        scraper = UKScraper()
        assert scraper.base_url == "https://www.norrona.com"

    def test_robots_url(self) -> None:
        scraper = UKScraper()
        assert scraper.robots_url == "https://www.norrona.com/robots.txt"


# ── Category inference tests ─────────────────────────────────────────────────


class TestCategoryInference:
    def test_jacket(self) -> None:
        assert BaseScraper._infer_category("falketind Gore-Tex Jacket Men") == "Jackets"

    def test_pants(self) -> None:
        assert BaseScraper._infer_category("bitihorn flex1 Pants Men") == "Pants"

    def test_fleece(self) -> None:
        assert BaseScraper._infer_category("warm2 Fleece Jacket") == "Fleece"

    def test_shorts(self) -> None:
        assert BaseScraper._infer_category("bitihorn Shorts Men") == "Shorts"

    def test_accessories_beanie(self) -> None:
        assert BaseScraper._infer_category("svalbard Wool Beanie") == "Accessories"

    def test_accessories_glove(self) -> None:
        assert BaseScraper._infer_category("falketind Windstopper Gloves") == "Accessories"

    def test_base_layer(self) -> None:
        assert BaseScraper._infer_category("Wool Base Layer Top") == "Base Layer"

    def test_unknown(self) -> None:
        assert BaseScraper._infer_category("Something Completely Different") == "Other"

    def test_bags(self) -> None:
        assert BaseScraper._infer_category("falketind 35L Backpack") == "Bags"

    def test_shirt(self) -> None:
        assert BaseScraper._infer_category("/29 cotton T-Shirt Men") == "Shirts"


# ── Robots.txt tests ─────────────────────────────────────────────────────────


class TestRobotsTxt:
    @pytest.mark.asyncio
    async def test_robots_txt_allowed(self, uk_scraper: UKScraper) -> None:
        robots_content = "User-agent: *\nAllow: /\n"
        mock_response = httpx.Response(
            status_code=200,
            text=robots_content,
            request=httpx.Request("GET", "https://www.norrona.com/robots.txt"),
        )
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            allowed = await uk_scraper._check_robots_txt()
            assert allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_disallowed(self, uk_scraper: UKScraper) -> None:
        robots_content = "User-agent: *\nDisallow: /en-GB/outlet/\n"
        mock_response = httpx.Response(
            status_code=200,
            text=robots_content,
            request=httpx.Request("GET", "https://www.norrona.com/robots.txt"),
        )
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            allowed = await uk_scraper._check_robots_txt()
            assert allowed is False

    @pytest.mark.asyncio
    async def test_robots_txt_not_found_allows_scraping(self, uk_scraper: UKScraper) -> None:
        mock_response = httpx.Response(
            status_code=404,
            text="Not Found",
            request=httpx.Request("GET", "https://www.norrona.com/robots.txt"),
        )
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            allowed = await uk_scraper._check_robots_txt()
            assert allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_fetch_error_allows_scraping(self, uk_scraper: UKScraper) -> None:
        with patch.object(
            httpx.AsyncClient,
            "get",
            new_callable=AsyncMock,
            side_effect=httpx.ConnectError("Connection refused"),
        ):
            allowed = await uk_scraper._check_robots_txt()
            assert allowed is True

    @pytest.mark.asyncio
    async def test_robots_txt_cached_after_first_check(self, uk_scraper: UKScraper) -> None:
        robots_content = "User-agent: *\nAllow: /\n"
        mock_response = httpx.Response(
            status_code=200,
            text=robots_content,
            request=httpx.Request("GET", "https://www.norrona.com/robots.txt"),
        )
        mock_get = AsyncMock(return_value=mock_response)
        with patch.object(httpx.AsyncClient, "get", mock_get):
            await uk_scraper._check_robots_txt()
            await uk_scraper._check_robots_txt()
            # Should only fetch once; second call uses cached result
            assert mock_get.call_count == 1


# ── Retry logic tests ────────────────────────────────────────────────────────


class TestRetryLogic:
    @pytest.mark.asyncio
    async def test_fetch_retries_on_failure(self, uk_scraper: UKScraper) -> None:
        call_count = 0

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("Connection refused")
            return httpx.Response(
                status_code=200,
                text="<html><body>OK</body></html>",
                request=httpx.Request("GET", url),
            )

        with patch.object(httpx.AsyncClient, "get", side_effect=mock_get):
            with patch("backend.src.scraper.scraper.asyncio.sleep", new_callable=AsyncMock):
                with _patch_settings(scrape_min_delay_seconds=0):
                    html = await uk_scraper._fetch_html("https://example.com/test")
                    assert "OK" in html
                    assert call_count == 3

    @pytest.mark.asyncio
    async def test_fetch_raises_after_max_retries(self, uk_scraper: UKScraper) -> None:
        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        with patch.object(httpx.AsyncClient, "get", side_effect=mock_get):
            with patch("backend.src.scraper.scraper.asyncio.sleep", new_callable=AsyncMock):
                with _patch_settings(scrape_min_delay_seconds=0):
                    with pytest.raises(RuntimeError, match="Failed to fetch.*after 3 retries"):
                        await uk_scraper._fetch_html("https://example.com/test")

    @pytest.mark.asyncio
    async def test_exponential_backoff_timings(self, uk_scraper: UKScraper) -> None:
        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("Connection refused")

        sleep_calls: list[float] = []

        async def mock_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        with patch.object(httpx.AsyncClient, "get", side_effect=mock_get):
            with patch("backend.src.scraper.scraper.asyncio.sleep", side_effect=mock_sleep):
                with _patch_settings(scrape_min_delay_seconds=0):
                    with pytest.raises(RuntimeError):
                        await uk_scraper._fetch_html("https://example.com/test")
                    # Filter out rate-limit sleeps (they'd be ~0 with min_delay=0)
                    backoff_sleeps = [s for s in sleep_calls if s >= 1.0]
                    # 2^1=2.0, 2^2=4.0 (only 2 backoff sleeps for 3 attempts)
                    assert backoff_sleeps == [2.0, 4.0]

    @pytest.mark.asyncio
    async def test_fetch_succeeds_on_first_try(self, uk_scraper: UKScraper) -> None:
        mock_response = httpx.Response(
            status_code=200,
            text="<html><body>Success</body></html>",
            request=httpx.Request("GET", "https://example.com/test"),
        )
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=mock_response
        ):
            with _patch_settings(scrape_min_delay_seconds=0):
                html = await uk_scraper._fetch_html("https://example.com/test")
                assert "Success" in html

    @pytest.mark.asyncio
    async def test_http_status_error_triggers_retry(self, uk_scraper: UKScraper) -> None:
        call_count = 0

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            response = httpx.Response(
                status_code=500 if call_count < 3 else 200,
                text="<html>OK</html>" if call_count >= 3 else "Error",
                request=httpx.Request("GET", url),
            )
            if call_count < 3:
                response.raise_for_status()
            return response

        # The raise_for_status will throw, but we need to simulate it differently
        # since the mock response won't auto-raise. Let's use side_effect.
        attempt = 0

        async def mock_get_v2(url: str, **kwargs: object) -> httpx.Response:
            nonlocal attempt
            attempt += 1
            if attempt < 3:
                raise httpx.HTTPStatusError(
                    "Server Error",
                    request=httpx.Request("GET", url),
                    response=httpx.Response(status_code=500),
                )
            return httpx.Response(
                status_code=200,
                text="<html>OK</html>",
                request=httpx.Request("GET", url),
            )

        with patch.object(httpx.AsyncClient, "get", side_effect=mock_get_v2):
            with patch("backend.src.scraper.scraper.asyncio.sleep", new_callable=AsyncMock):
                with _patch_settings(scrape_min_delay_seconds=0):
                    html = await uk_scraper._fetch_html("https://example.com/test")
                    assert "OK" in html
                    assert attempt == 3


# ── Playwright fallback tests ────────────────────────────────────────────────


class TestPlaywrightFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_playwright_on_empty_product_list(
        self, uk_scraper: UKScraper, empty_html: str, en_gb_html: str
    ) -> None:
        """When httpx returns HTML with no products, the scraper falls back to Playwright."""
        # First fetch returns empty HTML (no products), Playwright returns full HTML
        robots_response = httpx.Response(
            status_code=200,
            text="User-agent: *\nAllow: /\n",
            request=httpx.Request("GET", "https://www.norrona.com/robots.txt"),
        )
        httpx_response = httpx.Response(
            status_code=200,
            text=empty_html,
            request=httpx.Request("GET", "https://www.norrona.com/en-GB/outlet/"),
        )

        get_call_count = 0

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            nonlocal get_call_count
            get_call_count += 1
            if "robots.txt" in url:
                return robots_response
            return httpx_response

        with patch.object(httpx.AsyncClient, "get", side_effect=mock_get):
            with patch.object(
                uk_scraper,
                "_fetch_with_playwright",
                new_callable=AsyncMock,
                return_value=en_gb_html,
            ) as mock_pw:
                with _patch_settings(scrape_min_delay_seconds=0):
                    products = await uk_scraper.scrape("en-GB")
                    mock_pw.assert_called_once_with(uk_scraper.outlet_url)
                    assert len(products) == 5

    @pytest.mark.asyncio
    async def test_no_playwright_when_products_found(
        self, uk_scraper: UKScraper, en_gb_html: str
    ) -> None:
        """When httpx returns HTML with products, Playwright is not invoked."""
        robots_response = httpx.Response(
            status_code=200,
            text="User-agent: *\nAllow: /\n",
            request=httpx.Request("GET", "https://www.norrona.com/robots.txt"),
        )
        httpx_response = httpx.Response(
            status_code=200,
            text=en_gb_html,
            request=httpx.Request("GET", "https://www.norrona.com/en-GB/outlet/"),
        )

        async def mock_get(url: str, **kwargs: object) -> httpx.Response:
            if "robots.txt" in url:
                return robots_response
            return httpx_response

        with patch.object(httpx.AsyncClient, "get", side_effect=mock_get):
            with patch.object(
                uk_scraper,
                "_fetch_with_playwright",
                new_callable=AsyncMock,
            ) as mock_pw:
                with _patch_settings(scrape_min_delay_seconds=0):
                    products = await uk_scraper.scrape("en-GB")
                    mock_pw.assert_not_called()
                    assert len(products) == 5

    @pytest.mark.asyncio
    async def test_playwright_fallback_failure_raises(self, uk_scraper: UKScraper) -> None:
        with patch(
            "backend.src.scraper.scraper.async_playwright",
            side_effect=RuntimeError("Playwright not installed"),
        ):
            with pytest.raises(RuntimeError, match="Playwright fallback failed"):
                await uk_scraper._fetch_with_playwright("https://example.com")


# ── Rate limiting / throttle tests ───────────────────────────────────────────


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_scrape_throttled_when_called_too_soon(self, uk_scraper: UKScraper) -> None:
        """Second scrape within the interval returns empty list."""
        uk_scraper._last_scrape_time = time.monotonic()  # Just scraped

        robots_response = httpx.Response(
            status_code=200,
            text="User-agent: *\nAllow: /\n",
            request=httpx.Request("GET", "https://www.norrona.com/robots.txt"),
        )
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=robots_response
        ):
            products = await uk_scraper.scrape("en-GB")
            assert products == []

    @pytest.mark.asyncio
    async def test_scrape_blocked_by_robots(self, uk_scraper: UKScraper) -> None:
        """Scrape returns empty list when robots.txt disallows."""
        robots_content = "User-agent: *\nDisallow: /en-GB/outlet/\n"
        robots_response = httpx.Response(
            status_code=200,
            text=robots_content,
            request=httpx.Request("GET", "https://www.norrona.com/robots.txt"),
        )
        with patch.object(
            httpx.AsyncClient, "get", new_callable=AsyncMock, return_value=robots_response
        ):
            products = await uk_scraper.scrape("en-GB")
            assert products == []


# ── User agent rotation tests ────────────────────────────────────────────────


class TestUserAgentRotation:
    def test_user_agent_is_in_pool(self) -> None:
        from backend.src.scraper.scraper import _USER_AGENTS, _random_user_agent

        for _ in range(50):
            ua = _random_user_agent()
            assert ua in _USER_AGENTS

    def test_multiple_user_agents_in_pool(self) -> None:
        from backend.src.scraper.scraper import _USER_AGENTS

        assert len(_USER_AGENTS) >= 3


# ── Helper functions ─────────────────────────────────────────────────────────


def _find_product(products: Sequence[ProductSnapshot], name: str) -> ProductSnapshot:
    for product in products:
        if product.name == name:
            return product
    raise ValueError(f"Product '{name}' not found in {[p.name for p in products]}")


class _patch_settings:
    """Context manager to temporarily patch settings values."""

    def __init__(self, **kwargs: object) -> None:
        self._patches: dict[str, object] = kwargs
        self._originals: dict[str, object] = {}

    def __enter__(self) -> _patch_settings:
        from backend.src.config import settings as _settings

        for key, value in self._patches.items():
            self._originals[key] = getattr(_settings, key)
            object.__setattr__(_settings, key, value)
        return self

    def __exit__(self, *args: object) -> None:
        from backend.src.config import settings as _settings

        for key, value in self._originals.items():
            object.__setattr__(_settings, key, value)
