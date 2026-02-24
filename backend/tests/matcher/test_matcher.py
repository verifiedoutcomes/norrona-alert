from __future__ import annotations

import uuid
from datetime import datetime

from backend.src.contracts.models import (
    AlertSchema,
    ChangeType,
    Locale,
    ProductChange,
    ProductSnapshot,
    UserPreferences,
)
from backend.src.matcher.matcher import (
    PreferenceMatcher,
    _matches_watchlist,
    _normalise_size,
    _sizes_match,
)

USER_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _make_snapshot(
    name: str = "Norrona Falketind Flex1 Jacket",
    url: str = "https://norrona.com/products/falketind-flex1-jacket",
    price: float = 199.0,
    original_price: float = 299.0,
    discount_pct: float = 33.0,
    available_sizes: list[str] | None = None,
    category: str = "jackets",
    image_url: str = "https://norrona.com/img/falketind.jpg",
    locale: Locale = Locale.EN_GB,
) -> ProductSnapshot:
    return ProductSnapshot(
        name=name,
        url=url,
        price=price,
        original_price=original_price,
        discount_pct=discount_pct,
        available_sizes=available_sizes if available_sizes is not None else ["S", "M", "L"],
        category=category,
        image_url=image_url,
        locale=locale,
        scraped_at=datetime(2024, 1, 1, 12, 0, 0),
    )


def _make_change(
    change_type: ChangeType = ChangeType.NEW,
    name: str = "Norrona Falketind Flex1 Jacket",
    url: str = "https://norrona.com/products/falketind-flex1-jacket",
    price: float = 199.0,
    available_sizes: list[str] | None = None,
    category: str = "jackets",
    previous_sizes: list[str] | None = None,
    previous_price: float | None = None,
) -> ProductChange:
    new_state = _make_snapshot(
        name=name,
        url=url,
        price=price,
        available_sizes=available_sizes,
        category=category,
    )
    previous_state: ProductSnapshot | None = None
    if change_type != ChangeType.NEW:
        prev_sizes = previous_sizes if previous_sizes is not None else ["S"]
        prev_price = previous_price if previous_price is not None else price
        previous_state = _make_snapshot(
            name=name,
            url=url,
            price=prev_price,
            available_sizes=prev_sizes,
            category=category,
        )
    return ProductChange(
        product=new_state,
        change_type=change_type,
        previous_state=previous_state,
        new_state=new_state,
    )


# ── Size normalisation tests ─────────────────────────────────────────────────


class TestNormaliseSize:
    """Tests for the _normalise_size helper."""

    def test_short_codes_returned_as_is(self) -> None:
        assert _normalise_size("S") == "s"
        assert _normalise_size("M") == "m"
        assert _normalise_size("L") == "l"
        assert _normalise_size("XL") == "xl"
        assert _normalise_size("XXS") == "xxs"
        assert _normalise_size("XS") == "xs"
        assert _normalise_size("XXL") == "xxl"

    def test_full_names_normalised(self) -> None:
        assert _normalise_size("Small") == "s"
        assert _normalise_size("Medium") == "m"
        assert _normalise_size("Large") == "l"
        assert _normalise_size("Extra Large") == "xl"
        assert _normalise_size("Extra Small") == "xs"
        assert _normalise_size("Extra Extra Small") == "xxs"
        assert _normalise_size("Extra Extra Large") == "xxl"

    def test_case_insensitive(self) -> None:
        assert _normalise_size("MEDIUM") == "m"
        assert _normalise_size("small") == "s"
        assert _normalise_size("EXTRA LARGE") == "xl"

    def test_whitespace_stripped(self) -> None:
        assert _normalise_size("  M  ") == "m"
        assert _normalise_size("  Medium  ") == "m"

    def test_unknown_size_returned_lowercase(self) -> None:
        assert _normalise_size("42") == "42"
        assert _normalise_size("10.5") == "10.5"

    def test_hyphenated_forms(self) -> None:
        assert _normalise_size("X-Small") == "xs"
        assert _normalise_size("X-Large") == "xl"
        assert _normalise_size("XX-Small") == "xxs"
        assert _normalise_size("XX-Large") == "xxl"


class TestSizesMatch:
    """Tests for the _sizes_match helper."""

    def test_exact_match(self) -> None:
        assert _sizes_match("M", ["S", "M", "L"]) is True

    def test_no_match(self) -> None:
        assert _sizes_match("XL", ["S", "M", "L"]) is False

    def test_cross_format_match_short_to_long(self) -> None:
        assert _sizes_match("M", ["Small", "Medium", "Large"]) is True

    def test_cross_format_match_long_to_short(self) -> None:
        assert _sizes_match("Medium", ["S", "M", "L"]) is True

    def test_cross_format_xl(self) -> None:
        assert _sizes_match("XL", ["Small", "Medium", "Large", "Extra Large"]) is True
        assert _sizes_match("Extra Large", ["S", "M", "L", "XL"]) is True

    def test_empty_available_sizes(self) -> None:
        assert _sizes_match("M", []) is False

    def test_numeric_size_match(self) -> None:
        assert _sizes_match("42", ["40", "42", "44"]) is True
        assert _sizes_match("42", ["40", "44"]) is False


# ── Fuzzy watchlist matching tests ────────────────────────────────────────────


class TestMatchesWatchlist:
    """Tests for fuzzy matching product names against watchlist terms."""

    def test_exact_match(self) -> None:
        result = _matches_watchlist("Falketind Jacket", ["Falketind Jacket"])
        assert result == "Falketind Jacket"

    def test_partial_match(self) -> None:
        result = _matches_watchlist(
            "Norrona Falketind Flex1 Jacket", ["Falketind"]
        )
        assert result == "Falketind"

    def test_case_insensitive_match(self) -> None:
        result = _matches_watchlist("FALKETIND JACKET", ["falketind jacket"])
        assert result == "falketind jacket"

    def test_no_match(self) -> None:
        result = _matches_watchlist("Bitihorn Pants", ["Falketind Jacket"])
        assert result is None

    def test_multiple_terms_first_match_returned(self) -> None:
        result = _matches_watchlist(
            "Falketind Flex1 Jacket",
            ["Lofoten", "Falketind", "Bitihorn"],
        )
        assert result == "Falketind"

    def test_empty_watchlist(self) -> None:
        result = _matches_watchlist("Falketind Jacket", [])
        assert result is None

    def test_fuzzy_match_with_typo(self) -> None:
        """token_set_ratio should handle slight variations."""
        result = _matches_watchlist(
            "Norrona Falketind Gore-Tex Jacket", ["Falketind Gore Tex"]
        )
        assert result is not None


# ── PreferenceMatcher tests ───────────────────────────────────────────────────


class TestPreferenceMatcherWatchlist:
    """Tests for watchlist-based matching."""

    def test_matches_watchlist_term(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(name="Falketind Flex1 Jacket")
        prefs = UserPreferences(watchlist_terms=["Falketind"])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].user_id == USER_ID

    def test_no_match_when_not_in_watchlist(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(name="Bitihorn Pants")
        prefs = UserPreferences(watchlist_terms=["Falketind Jacket"])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 0

    def test_no_watchlist_means_match_all(self) -> None:
        """When no watchlist terms are set, all products should match."""
        matcher = PreferenceMatcher()
        change = _make_change(name="Any Product")
        prefs = UserPreferences(watchlist_terms=[])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1

    def test_fuzzy_match_partial_name(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(name="Norrona Falketind Gore-Tex Pro Jacket")
        prefs = UserPreferences(watchlist_terms=["Falketind"])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1

    def test_case_insensitive_watchlist(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(name="FALKETIND FLEX1 JACKET")
        prefs = UserPreferences(watchlist_terms=["falketind"])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1


class TestPreferenceMatcherSizeFormat:
    """Tests for size format inconsistency handling."""

    def test_short_code_matches_full_name(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            available_sizes=["Small", "Medium", "Large"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "M"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "new_product_in_size"

    def test_full_name_matches_short_code(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            available_sizes=["S", "M", "L"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "Medium"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "new_product_in_size"

    def test_xl_matches_extra_large(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            available_sizes=["Medium", "Large", "Extra Large"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "XL"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "new_product_in_size"

    def test_extra_large_matches_xl(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            available_sizes=["S", "M", "L", "XL"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "Extra Large"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1

    def test_small_matches_s(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            available_sizes=["S", "M", "L"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "Small"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1


class TestPreferenceMatcherPriceThreshold:
    """Tests for max_price filtering."""

    def test_product_at_max_price(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(price=200.0)
        prefs = UserPreferences(watchlist_terms=[], max_price=200.0)

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1

    def test_product_below_max_price(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(price=150.0)
        prefs = UserPreferences(watchlist_terms=[], max_price=200.0)

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1

    def test_product_above_max_price_filtered_out(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(price=250.0)
        prefs = UserPreferences(watchlist_terms=[], max_price=200.0)

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 0

    def test_no_max_price_means_no_filter(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(price=9999.0)
        prefs = UserPreferences(watchlist_terms=[], max_price=None)

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1


class TestPreferenceMatcherRestockExactSize:
    """Tests for restock_exact_size matched rule (highest priority)."""

    def test_restock_exact_size_detected(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            change_type=ChangeType.RESTOCK,
            available_sizes=["S", "M", "L"],
            previous_sizes=["S"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "M"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "restock_exact_size"

    def test_restock_but_not_users_size(self) -> None:
        """Restock of a different size should be 'restock', not 'restock_exact_size'."""
        matcher = PreferenceMatcher()
        change = _make_change(
            change_type=ChangeType.RESTOCK,
            available_sizes=["S", "M", "L"],
            previous_sizes=["S", "M"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "M"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "restock"

    def test_restock_exact_size_with_format_inconsistency(self) -> None:
        """User prefers 'M' but restocked size is listed as 'Medium'."""
        matcher = PreferenceMatcher()
        change = _make_change(
            change_type=ChangeType.RESTOCK,
            available_sizes=["Small", "Medium", "Large"],
            previous_sizes=["Small"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "M"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "restock_exact_size"

    def test_restock_no_size_preference(self) -> None:
        """Restock without size preference should give 'restock' rule."""
        matcher = PreferenceMatcher()
        change = _make_change(
            change_type=ChangeType.RESTOCK,
            available_sizes=["S", "M", "L"],
            previous_sizes=["S"],
            category="jackets",
        )
        prefs = UserPreferences(watchlist_terms=[])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "restock"


class TestPreferenceMatcherCombined:
    """Tests for combined matching rules (watchlist + size + price)."""

    def test_watchlist_plus_size_plus_price(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            name="Falketind Flex1 Jacket",
            price=150.0,
            available_sizes=["S", "M", "L"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=["Falketind"],
            size_map={"jackets": "M"},
            max_price=200.0,
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "new_product_in_size"

    def test_watchlist_match_but_price_too_high(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            name="Falketind Flex1 Jacket",
            price=300.0,
        )
        prefs = UserPreferences(
            watchlist_terms=["Falketind"],
            max_price=200.0,
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 0

    def test_price_ok_but_no_watchlist_match(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            name="Bitihorn Lightweight Pants",
            price=100.0,
        )
        prefs = UserPreferences(
            watchlist_terms=["Falketind Jacket"],
            max_price=200.0,
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 0

    def test_multiple_changes_mixed_results(self) -> None:
        matcher = PreferenceMatcher()
        changes = [
            _make_change(
                name="Falketind Jacket",
                url="https://norrona.com/a",
                price=150.0,
            ),
            _make_change(
                name="Bitihorn Pants",
                url="https://norrona.com/b",
                price=100.0,
            ),
            _make_change(
                name="Falketind Pants",
                url="https://norrona.com/c",
                price=350.0,
            ),
        ]
        prefs = UserPreferences(
            watchlist_terms=["Falketind"],
            max_price=200.0,
        )

        alerts = matcher.match(changes, prefs, user_id=USER_ID)

        # Only first Falketind matches (second is above max_price, Bitihorn doesn't match watchlist)
        assert len(alerts) == 1
        assert alerts[0].product_change.new_state.name == "Falketind Jacket"


class TestPreferenceMatcherMatchedRules:
    """Tests for the specific matched_rule values."""

    def test_new_product_rule(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(change_type=ChangeType.NEW)
        prefs = UserPreferences(watchlist_terms=[])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert alerts[0].matched_rule == "new_product"

    def test_new_product_in_size_rule(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            change_type=ChangeType.NEW,
            available_sizes=["S", "M", "L"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "M"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert alerts[0].matched_rule == "new_product_in_size"

    def test_price_drop_rule(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            change_type=ChangeType.PRICE_DROP,
            price=149.0,
            previous_price=199.0,
        )
        prefs = UserPreferences(watchlist_terms=[])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert alerts[0].matched_rule == "price_drop"

    def test_price_drop_in_size_rule(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            change_type=ChangeType.PRICE_DROP,
            price=149.0,
            previous_price=199.0,
            available_sizes=["S", "M", "L"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "M"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert alerts[0].matched_rule == "price_drop_in_size"

    def test_restock_rule(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            change_type=ChangeType.RESTOCK,
            available_sizes=["S", "M", "L"],
            previous_sizes=["S"],
        )
        prefs = UserPreferences(watchlist_terms=[])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert alerts[0].matched_rule == "restock"


class TestPreferenceMatcherEdgeCases:
    """Tests for edge cases."""

    def test_empty_changes_list(self) -> None:
        matcher = PreferenceMatcher()
        prefs = UserPreferences(watchlist_terms=["Falketind"])

        alerts = matcher.match([], prefs, user_id=USER_ID)

        assert alerts == []

    def test_empty_preferences(self) -> None:
        """Default preferences (no watchlist, no size_map, no max_price) should match all."""
        matcher = PreferenceMatcher()
        change = _make_change()
        prefs = UserPreferences()

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1

    def test_user_id_generated_when_not_provided(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change()
        prefs = UserPreferences(watchlist_terms=[])

        alerts = matcher.match([change], prefs)

        assert len(alerts) == 1
        assert alerts[0].user_id is not None

    def test_size_map_for_different_category(self) -> None:
        """Size preference for 'pants' should not affect 'jackets' category."""
        matcher = PreferenceMatcher()
        change = _make_change(
            change_type=ChangeType.NEW,
            available_sizes=["S", "M", "L"],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"pants": "M"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "new_product"

    def test_product_with_no_available_sizes(self) -> None:
        matcher = PreferenceMatcher()
        change = _make_change(
            available_sizes=[],
            category="jackets",
        )
        prefs = UserPreferences(
            watchlist_terms=[],
            size_map={"jackets": "M"},
        )

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        assert alerts[0].matched_rule == "new_product"

    def test_alert_schema_structure(self) -> None:
        """Verify the AlertSchema fields are correctly populated."""
        matcher = PreferenceMatcher()
        change = _make_change(name="Falketind Jacket", price=150.0)
        prefs = UserPreferences(watchlist_terms=["Falketind"])

        alerts = matcher.match([change], prefs, user_id=USER_ID)

        assert len(alerts) == 1
        alert = alerts[0]
        assert isinstance(alert, AlertSchema)
        assert alert.user_id == USER_ID
        assert alert.product_change == change
        assert isinstance(alert.matched_rule, str)
        assert len(alert.matched_rule) > 0
