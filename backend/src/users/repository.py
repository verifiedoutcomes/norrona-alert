from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.src.contracts.models import User, UserPreferences


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, email: str) -> User:
        user = User(
            id=uuid.uuid4(),
            email=email,
            preferences=UserPreferences().model_dump(),
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def update_preferences(self, user_id: uuid.UUID, prefs: UserPreferences) -> User:
        user = await self.get_by_id(user_id)
        if user is None:
            raise ValueError(f"User {user_id} not found")
        user.preferences = prefs.model_dump()
        await self._session.flush()
        return user

    async def get_all_with_devices(self) -> list[User]:
        stmt = select(User).options(selectinload(User.devices))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
