from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.contracts.models import ProductSnapshot, ProductSnapshotRow


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_latest_by_locale(self, locale: str) -> list[ProductSnapshotRow]:
        stmt = (
            select(ProductSnapshotRow)
            .where(ProductSnapshotRow.locale == locale)
            .order_by(ProductSnapshotRow.scraped_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_upsert(self, snapshots: list[ProductSnapshot]) -> None:
        for snapshot in snapshots:
            stmt = select(ProductSnapshotRow).where(
                ProductSnapshotRow.url == snapshot.url,
                ProductSnapshotRow.locale == snapshot.locale.value,
            )
            result = await self._session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing is not None:
                existing.name = snapshot.name
                existing.price = snapshot.price
                existing.original_price = snapshot.original_price
                existing.discount_pct = snapshot.discount_pct
                existing.available_sizes = snapshot.available_sizes
                existing.category = snapshot.category
                existing.image_url = snapshot.image_url
                existing.scraped_at = snapshot.scraped_at
            else:
                row = ProductSnapshotRow(
                    id=uuid.uuid4(),
                    name=snapshot.name,
                    url=snapshot.url,
                    price=snapshot.price,
                    original_price=snapshot.original_price,
                    discount_pct=snapshot.discount_pct,
                    available_sizes=snapshot.available_sizes,
                    category=snapshot.category,
                    image_url=snapshot.image_url,
                    locale=snapshot.locale.value,
                    scraped_at=snapshot.scraped_at,
                )
                self._session.add(row)

        await self._session.flush()
