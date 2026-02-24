"""Initial schema - users, product_snapshots, device_registrations, magic_link_tokens.

Revision ID: 001_initial
Revises:
Create Date: 2026-02-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), unique=True, nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    # Product snapshots
    op.create_table(
        "product_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("original_price", sa.Float(), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=False),
        sa.Column("available_sizes", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("category", sa.String(200), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("locale", sa.String(10), nullable=False),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_product_snapshots_locale", "product_snapshots", ["locale"])
    op.create_index("ix_product_snapshots_url", "product_snapshots", ["url"])

    # Device registrations
    op.create_table(
        "device_registrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_token", sa.String(500), nullable=False),
        sa.Column(
            "platform",
            sa.Enum("web", "ios", name="platform_enum"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_device_registrations_user_id",
        "device_registrations",
        ["user_id"],
    )

    # Magic link tokens
    op.create_table(
        "magic_link_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("token", sa.String(200), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("magic_link_tokens")
    op.drop_table("device_registrations")
    op.drop_table("product_snapshots")
    op.drop_table("users")
    sa.Enum(name="platform_enum").drop(op.get_bind())  # type: ignore[arg-type]
