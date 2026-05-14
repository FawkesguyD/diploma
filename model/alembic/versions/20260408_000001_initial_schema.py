from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "listings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("city", sa.String(length=255), nullable=True),
        sa.Column("district", sa.String(length=255), nullable=True),
        sa.Column("area", sa.Numeric(12, 2), nullable=True),
        sa.Column("rooms", sa.Integer(), nullable=True),
        sa.Column("floor", sa.Integer(), nullable=True),
        sa.Column("total_floors", sa.Integer(), nullable=True),
        sa.Column("listing_price", sa.Numeric(14, 2), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
    )

    op.create_table(
        "valuations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("predicted_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("undervaluation_delta", sa.Numeric(14, 2), nullable=False),
        sa.Column("undervaluation_percent", sa.Numeric(7, 4), nullable=False),
        sa.Column("score", sa.Numeric(7, 4), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("listing_id", name="uq_valuations_listing_id"),
    )

    op.create_table(
        "shortlist_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_listings_city_district", "listings", ["city", "district"])
    op.create_index("ix_shortlist_items_listing_id", "shortlist_items", ["listing_id"])
    op.create_index("ix_shortlist_items_user_id", "shortlist_items", ["user_id"])
    op.create_index("ix_valuations_score", "valuations", ["score"])


def downgrade() -> None:
    op.drop_index("ix_valuations_score", table_name="valuations")
    op.drop_index("ix_shortlist_items_user_id", table_name="shortlist_items")
    op.drop_index("ix_shortlist_items_listing_id", table_name="shortlist_items")
    op.drop_index("ix_listings_city_district", table_name="listings")
    op.drop_table("shortlist_items")
    op.drop_table("valuations")
    op.drop_table("listings")
    op.drop_table("users")
