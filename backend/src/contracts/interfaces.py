from __future__ import annotations

from typing import Protocol

from backend.src.contracts.models import AlertSchema, ProductChange, ProductSnapshot, UserPreferences, User


class IScraper(Protocol):
    async def scrape(self, locale: str) -> list[ProductSnapshot]: ...


class IProductDiffer(Protocol):
    def diff(
        self, old: list[ProductSnapshot], new: list[ProductSnapshot]
    ) -> list[ProductChange]: ...


class IMatcher(Protocol):
    def match(
        self, changes: list[ProductChange], preferences: UserPreferences
    ) -> list[AlertSchema]: ...


class INotifier(Protocol):
    async def send(self, alert: AlertSchema, user: User) -> bool: ...
