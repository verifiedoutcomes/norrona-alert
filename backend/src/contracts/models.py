from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, HttpUrl
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Enums ──────────────────────────────────────────────────────────────────────


class Locale(str, enum.Enum):
    EN_GB = "en-GB"
    NB_NO = "nb-NO"


class ChangeType(str, enum.Enum):
    NEW = "new"
    RESTOCK = "restock"
    PRICE_DROP = "price_drop"


class Platform(str, enum.Enum):
    WEB = "web"
    IOS = "ios"


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class ProductSnapshot(BaseModel):
    name: str
    url: str
    price: float
    original_price: float
    discount_pct: float
    available_sizes: list[str]
    category: str
    image_url: str
    locale: Locale
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class ProductChange(BaseModel):
    product: ProductSnapshot
    change_type: ChangeType
    previous_state: ProductSnapshot | None = None
    new_state: ProductSnapshot


class UserPreferences(BaseModel):
    region: Locale = Locale.EN_GB
    size_map: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of category to preferred size, e.g. {'jackets': 'M', 'pants': 'L'}",
    )
    watchlist_terms: list[str] = Field(default_factory=list)
    max_price: float | None = None


class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    preferences: UserPreferences
    created_at: datetime


class AlertSchema(BaseModel):
    user_id: uuid.UUID
    product_change: ProductChange
    matched_rule: str


class DeviceRegistrationCreate(BaseModel):
    device_token: str
    platform: Platform


class DeviceRegistrationRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    device_token: str
    platform: Platform
    created_at: datetime


# ── SQLAlchemy ORM ─────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    devices: Mapped[list["DeviceRegistration"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def get_preferences(self) -> UserPreferences:
        return UserPreferences.model_validate(self.preferences)


class ProductSnapshotRow(Base):
    __tablename__ = "product_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float] = mapped_column(nullable=False)
    original_price: Mapped[float] = mapped_column(nullable=False)
    discount_pct: Mapped[float] = mapped_column(nullable=False)
    available_sizes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    category: Mapped[str] = mapped_column(String(200), nullable=False)
    image_url: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_product_snapshots_locale", "locale"),
        Index("ix_product_snapshots_url", "url"),
    )

    def to_schema(self) -> ProductSnapshot:
        return ProductSnapshot(
            name=self.name,
            url=self.url,
            price=self.price,
            original_price=self.original_price,
            discount_pct=self.discount_pct,
            available_sizes=self.available_sizes,
            category=self.category,
            image_url=self.image_url,
            locale=Locale(self.locale),
            scraped_at=self.scraped_at,
        )


class DeviceRegistration(Base):
    __tablename__ = "device_registrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    device_token: Mapped[str] = mapped_column(String(500), nullable=False)
    platform: Mapped[str] = mapped_column(
        Enum(Platform, name="platform_enum"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="devices")

    __table_args__ = (
        Index("ix_device_registrations_user_id", "user_id"),
    )


class MagicLinkToken(Base):
    __tablename__ = "magic_link_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    token: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
