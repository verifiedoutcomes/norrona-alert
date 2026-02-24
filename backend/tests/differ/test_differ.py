from __future__ import annotations

from datetime import datetime

from backend.src.contracts.models import ChangeType, Locale, ProductSnapshot
from backend.src.differ.differ import ProductDiffer


def _make_snapshot(
    name: str = "Norrona Falketind Jacket",
    url: str = "https://norrona.com/products/falketind-jacket",
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


class TestNewProductDetection:
    """Tests for detecting products present in new but not in old."""

    def test_single_new_product(self) -> None:
        differ = ProductDiffer()
        old: list[ProductSnapshot] = []
        new = [_make_snapshot()]

        changes = differ.diff(old, new)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.NEW
        assert changes[0].new_state.name == "Norrona Falketind Jacket"
        assert changes[0].previous_state is None

    def test_multiple_new_products(self) -> None:
        differ = ProductDiffer()
        old: list[ProductSnapshot] = []
        new = [
            _make_snapshot(name="Jacket A", url="https://norrona.com/a"),
            _make_snapshot(name="Jacket B", url="https://norrona.com/b"),
            _make_snapshot(name="Jacket C", url="https://norrona.com/c"),
        ]

        changes = differ.diff(old, new)

        assert len(changes) == 3
        assert all(c.change_type == ChangeType.NEW for c in changes)

    def test_new_product_among_existing(self) -> None:
        differ = ProductDiffer()
        existing = _make_snapshot(name="Existing", url="https://norrona.com/existing")
        old = [existing]
        new = [
            existing,
            _make_snapshot(name="Brand New", url="https://norrona.com/new"),
        ]

        changes = differ.diff(old, new)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.NEW
        assert changes[0].new_state.name == "Brand New"


class TestRestockDetection:
    """Tests for detecting restocked sizes."""

    def test_single_size_restock(self) -> None:
        differ = ProductDiffer()
        old = [_make_snapshot(available_sizes=["S", "M"])]
        new = [_make_snapshot(available_sizes=["S", "M", "L"])]

        changes = differ.diff(old, new)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.RESTOCK
        assert changes[0].previous_state is not None
        assert "L" in changes[0].new_state.available_sizes
        assert "L" not in changes[0].previous_state.available_sizes

    def test_multiple_sizes_restocked(self) -> None:
        differ = ProductDiffer()
        old = [_make_snapshot(available_sizes=["M"])]
        new = [_make_snapshot(available_sizes=["S", "M", "L", "XL"])]

        changes = differ.diff(old, new)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.RESTOCK

    def test_no_restock_when_same_sizes(self) -> None:
        differ = ProductDiffer()
        old = [_make_snapshot(available_sizes=["S", "M", "L"])]
        new = [_make_snapshot(available_sizes=["S", "M", "L"])]

        changes = differ.diff(old, new)

        assert len(changes) == 0

    def test_no_restock_when_sizes_removed(self) -> None:
        """Sizes being removed (going out of stock) is not a restock."""
        differ = ProductDiffer()
        old = [_make_snapshot(available_sizes=["S", "M", "L"])]
        new = [_make_snapshot(available_sizes=["S", "M"])]

        changes = differ.diff(old, new)

        assert len(changes) == 0

    def test_restock_detected_alongside_size_removal(self) -> None:
        """If some sizes are removed and others added, still detect restock."""
        differ = ProductDiffer()
        old = [_make_snapshot(available_sizes=["S", "M"])]
        new = [_make_snapshot(available_sizes=["M", "XL"])]

        changes = differ.diff(old, new)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.RESTOCK


class TestPriceDropDetection:
    """Tests for detecting price drops."""

    def test_price_drop(self) -> None:
        differ = ProductDiffer()
        old = [_make_snapshot(price=199.0)]
        new = [_make_snapshot(price=149.0)]

        changes = differ.diff(old, new)

        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.PRICE_DROP
        assert changes[0].previous_state is not None
        assert changes[0].previous_state.price == 199.0
        assert changes[0].new_state.price == 149.0

    def test_no_change_when_price_same(self) -> None:
        differ = ProductDiffer()
        old = [_make_snapshot(price=199.0)]
        new = [_make_snapshot(price=199.0)]

        changes = differ.diff(old, new)

        assert len(changes) == 0

    def test_no_change_when_price_increases(self) -> None:
        """Price increase should not generate a change."""
        differ = ProductDiffer()
        old = [_make_snapshot(price=149.0)]
        new = [_make_snapshot(price=199.0)]

        changes = differ.diff(old, new)

        assert len(changes) == 0

    def test_price_drop_and_restock_together(self) -> None:
        """A product can have both a price drop and a restock simultaneously."""
        differ = ProductDiffer()
        old = [_make_snapshot(price=199.0, available_sizes=["S"])]
        new = [_make_snapshot(price=149.0, available_sizes=["S", "M", "L"])]

        changes = differ.diff(old, new)

        assert len(changes) == 2
        change_types = {c.change_type for c in changes}
        assert ChangeType.RESTOCK in change_types
        assert ChangeType.PRICE_DROP in change_types


class TestNoChanges:
    """Tests for scenarios where no changes are detected."""

    def test_both_lists_empty(self) -> None:
        differ = ProductDiffer()

        changes = differ.diff([], [])

        assert changes == []

    def test_old_list_empty_new_empty(self) -> None:
        differ = ProductDiffer()

        changes = differ.diff([], [])

        assert changes == []

    def test_identical_snapshots(self) -> None:
        differ = ProductDiffer()
        snapshot = _make_snapshot()
        old = [snapshot]
        new = [snapshot]

        changes = differ.diff(old, new)

        assert changes == []

    def test_product_removed_from_new(self) -> None:
        """Products disappearing from the catalog should not generate changes."""
        differ = ProductDiffer()
        old = [_make_snapshot()]
        new: list[ProductSnapshot] = []

        changes = differ.diff(old, new)

        assert changes == []


class TestMultipleProductChanges:
    """Tests for handling multiple products with various changes."""

    def test_mixed_changes_across_products(self) -> None:
        differ = ProductDiffer()
        old = [
            _make_snapshot(name="Jacket A", url="https://norrona.com/a", price=200.0, available_sizes=["S"]),
            _make_snapshot(name="Jacket B", url="https://norrona.com/b", price=300.0, available_sizes=["M", "L"]),
        ]
        new = [
            _make_snapshot(name="Jacket A", url="https://norrona.com/a", price=150.0, available_sizes=["S"]),  # price drop
            _make_snapshot(name="Jacket B", url="https://norrona.com/b", price=300.0, available_sizes=["M", "L", "XL"]),  # restock
            _make_snapshot(name="Jacket C", url="https://norrona.com/c", price=100.0),  # new product
        ]

        changes = differ.diff(old, new)

        assert len(changes) == 3
        change_types = {c.change_type for c in changes}
        assert ChangeType.PRICE_DROP in change_types
        assert ChangeType.RESTOCK in change_types
        assert ChangeType.NEW in change_types

    def test_url_used_as_identity(self) -> None:
        """Products are matched by URL, not by name."""
        differ = ProductDiffer()
        old = [_make_snapshot(name="Old Name", url="https://norrona.com/product")]
        new = [_make_snapshot(name="New Name", url="https://norrona.com/product")]

        changes = differ.diff(old, new)

        # Name change alone doesn't trigger any change type
        assert len(changes) == 0
