from __future__ import annotations

import uuid

import structlog
from thefuzz import fuzz

from backend.src.contracts.models import (
    AlertSchema,
    ChangeType,
    ProductChange,
    UserPreferences,
)

logger = structlog.get_logger(__name__)

# Threshold for fuzzy matching product names against watchlist terms
FUZZY_MATCH_THRESHOLD = 80

# Mapping of short size codes to their full-length equivalents.
# Used for normalising user-preferred sizes and product available sizes
# so that "M" matches "Medium", "S" matches "Small", etc.
SIZE_ALIASES: dict[str, list[str]] = {
    "xxs": ["xx-small", "extra extra small", "double extra small"],
    "xs": ["x-small", "extra small"],
    "s": ["small"],
    "m": ["medium", "med"],
    "l": ["large"],
    "xl": ["x-large", "extra large"],
    "xxl": ["xx-large", "extra extra large", "double extra large", "2xl"],
    "3xl": ["xxx-large", "xxxl", "triple extra large"],
}


def _normalise_size(size: str) -> str:
    """Normalise a size string to its canonical short form.

    Handles common variations like "Medium" -> "m", "Extra Large" -> "xl",
    "X-Small" -> "xs", etc. If the size cannot be mapped, it is returned
    as-is in lowercase with whitespace stripped.
    """
    cleaned = size.strip().lower()

    # Check if it's already a short code
    if cleaned in SIZE_ALIASES:
        return cleaned

    # Check if the cleaned value matches any alias
    for short_code, aliases in SIZE_ALIASES.items():
        if cleaned in aliases:
            return short_code

    return cleaned


def _sizes_match(preferred_size: str, available_sizes: list[str]) -> bool:
    """Check if the user's preferred size is among the available sizes.

    Compares using normalised forms so "M" matches "Medium", etc.
    """
    normalised_preferred = _normalise_size(preferred_size)
    normalised_available = {_normalise_size(s) for s in available_sizes}
    return normalised_preferred in normalised_available


def _matches_watchlist(product_name: str, watchlist_terms: list[str]) -> str | None:
    """Return the first watchlist term that fuzzy-matches the product name.

    Uses token_set_ratio from thefuzz for robust partial/case-insensitive
    matching. Returns None if no term meets the threshold.
    """
    for term in watchlist_terms:
        score = fuzz.token_set_ratio(product_name.lower(), term.lower())
        if score >= FUZZY_MATCH_THRESHOLD:
            return term
    return None


class PreferenceMatcher:
    """Match product changes against user preferences to produce alerts.

    Matching rules:
    - Watchlist terms: fuzzy match product name against watchlist_terms (threshold 80)
    - Size availability: check if user's preferred size is available
    - Price threshold: if max_price set, only alert for products at or below that price
    - Restock in user's exact size = highest priority ("restock_exact_size")
    """

    def match(
        self,
        changes: list[ProductChange],
        preferences: UserPreferences,
        user_id: uuid.UUID | None = None,
    ) -> list[AlertSchema]:
        effective_user_id = user_id if user_id is not None else uuid.uuid4()
        alerts: list[AlertSchema] = []

        for change in changes:
            product = change.new_state

            # Price threshold check: skip products above max_price
            if preferences.max_price is not None and product.price > preferences.max_price:
                logger.debug(
                    "skipped_above_max_price",
                    name=product.name,
                    price=product.price,
                    max_price=preferences.max_price,
                )
                continue

            # Check watchlist match
            matched_term = _matches_watchlist(product.name, preferences.watchlist_terms)
            if matched_term is None and preferences.watchlist_terms:
                logger.debug(
                    "skipped_no_watchlist_match",
                    name=product.name,
                    watchlist_terms=preferences.watchlist_terms,
                )
                continue

            # Determine the matched rule
            matched_rule = self._determine_rule(change, product.category, preferences)

            if matched_rule is not None:
                logger.info(
                    "alert_matched",
                    name=product.name,
                    change_type=change.change_type.value,
                    matched_rule=matched_rule,
                    matched_term=matched_term,
                )
                alerts.append(
                    AlertSchema(
                        user_id=effective_user_id,
                        product_change=change,
                        matched_rule=matched_rule,
                    )
                )

        logger.info(
            "matching_complete",
            changes_count=len(changes),
            alerts_count=len(alerts),
        )

        return alerts

    def _determine_rule(
        self,
        change: ProductChange,
        category: str,
        preferences: UserPreferences,
    ) -> str | None:
        """Determine the matched rule for a product change.

        Priority order:
        1. restock_exact_size - restock of user's exact preferred size
        2. restock - general restock
        3. price_drop_in_size - price drop and user's size is available
        4. price_drop - general price drop
        5. new_product_in_size - new product with user's size available
        6. new_product - general new product
        """
        product = change.new_state
        preferred_size = preferences.size_map.get(category)
        has_preferred_size = (
            preferred_size is not None
            and _sizes_match(preferred_size, product.available_sizes)
        )

        if change.change_type == ChangeType.RESTOCK:
            if has_preferred_size and preferred_size is not None:
                # Check if the user's exact size was one of the restocked sizes
                old_sizes = (
                    set(change.previous_state.available_sizes)
                    if change.previous_state is not None
                    else set()
                )
                new_sizes = set(product.available_sizes)
                restocked_sizes = new_sizes - old_sizes
                if _sizes_match(preferred_size, list(restocked_sizes)):
                    return "restock_exact_size"
                return "restock"
            return "restock"

        if change.change_type == ChangeType.PRICE_DROP:
            if has_preferred_size:
                return "price_drop_in_size"
            return "price_drop"

        if change.change_type == ChangeType.NEW:
            if has_preferred_size:
                return "new_product_in_size"
            return "new_product"

        return None
