from __future__ import annotations

import structlog

from backend.src.contracts.models import ChangeType, ProductChange, ProductSnapshot

logger = structlog.get_logger(__name__)


class ProductDiffer:
    """Compare two lists of ProductSnapshot (old vs new) and detect changes.

    Detects:
    - New products: present in new but not in old (matched by URL)
    - Restocked sizes: product exists in both but new has sizes that old didn't
    - Price drops: same product, lower price in new
    """

    def diff(
        self, old: list[ProductSnapshot], new: list[ProductSnapshot]
    ) -> list[ProductChange]:
        changes: list[ProductChange] = []

        old_by_url: dict[str, ProductSnapshot] = {p.url: p for p in old}

        for new_product in new:
            old_product = old_by_url.get(new_product.url)

            if old_product is None:
                logger.info(
                    "new_product_detected",
                    name=new_product.name,
                    url=new_product.url,
                    price=new_product.price,
                )
                changes.append(
                    ProductChange(
                        product=new_product,
                        change_type=ChangeType.NEW,
                        previous_state=None,
                        new_state=new_product,
                    )
                )
                continue

            # Check for restocked sizes
            old_sizes = set(old_product.available_sizes)
            new_sizes = set(new_product.available_sizes)
            restocked = new_sizes - old_sizes

            if restocked:
                logger.info(
                    "restock_detected",
                    name=new_product.name,
                    url=new_product.url,
                    restocked_sizes=sorted(restocked),
                )
                changes.append(
                    ProductChange(
                        product=new_product,
                        change_type=ChangeType.RESTOCK,
                        previous_state=old_product,
                        new_state=new_product,
                    )
                )

            # Check for price drops
            if new_product.price < old_product.price:
                logger.info(
                    "price_drop_detected",
                    name=new_product.name,
                    url=new_product.url,
                    old_price=old_product.price,
                    new_price=new_product.price,
                )
                changes.append(
                    ProductChange(
                        product=new_product,
                        change_type=ChangeType.PRICE_DROP,
                        previous_state=old_product,
                        new_state=new_product,
                    )
                )

        logger.info(
            "diff_complete",
            old_count=len(old),
            new_count=len(new),
            changes_count=len(changes),
        )

        return changes
