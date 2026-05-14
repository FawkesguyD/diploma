from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_000002"
down_revision = "20260408_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("living_area_m2", sa.Numeric(12, 2), nullable=True))
    op.add_column("listings", sa.Column("kitchen_area_m2", sa.Numeric(12, 2), nullable=True))
    op.add_column("listings", sa.Column("ceiling_height", sa.Numeric(5, 2), nullable=True))
    op.add_column("listings", sa.Column("building_type", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("building_series", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("year_built", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("condition", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("heating", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("gas_supply", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("bathroom", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("balcony", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("parking", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("furniture", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("flooring", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("door_type", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("has_landline_phone", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("internet", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("mortgage", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("seller_type", sa.String(length=255), nullable=True))
    op.add_column("listings", sa.Column("latitude", sa.Numeric(10, 6), nullable=True))
    op.add_column("listings", sa.Column("longitude", sa.Numeric(10, 6), nullable=True))
    op.add_column("listings", sa.Column("photo_count", sa.Integer(), nullable=True))
    op.add_column(
        "listings",
        sa.Column("listing_currency", sa.String(length=3), nullable=False, server_default="RUB"),
    )

    op.add_column("valuations", sa.Column("explanation_summary", sa.Text(), nullable=True))
    op.add_column(
        "valuations",
        sa.Column(
            "top_factors",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )


def downgrade() -> None:
    op.drop_column("valuations", "top_factors")
    op.drop_column("valuations", "explanation_summary")

    op.drop_column("listings", "listing_currency")
    op.drop_column("listings", "photo_count")
    op.drop_column("listings", "longitude")
    op.drop_column("listings", "latitude")
    op.drop_column("listings", "seller_type")
    op.drop_column("listings", "mortgage")
    op.drop_column("listings", "internet")
    op.drop_column("listings", "has_landline_phone")
    op.drop_column("listings", "door_type")
    op.drop_column("listings", "flooring")
    op.drop_column("listings", "furniture")
    op.drop_column("listings", "parking")
    op.drop_column("listings", "balcony")
    op.drop_column("listings", "bathroom")
    op.drop_column("listings", "gas_supply")
    op.drop_column("listings", "heating")
    op.drop_column("listings", "condition")
    op.drop_column("listings", "year_built")
    op.drop_column("listings", "building_series")
    op.drop_column("listings", "building_type")
    op.drop_column("listings", "ceiling_height")
    op.drop_column("listings", "kitchen_area_m2")
    op.drop_column("listings", "living_area_m2")
