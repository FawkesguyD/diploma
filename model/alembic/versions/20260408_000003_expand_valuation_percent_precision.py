from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260408_000003"
down_revision = "20260408_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "valuations",
        "undervaluation_percent",
        existing_type=sa.Numeric(7, 4),
        type_=sa.Numeric(12, 4),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "valuations",
        "undervaluation_percent",
        existing_type=sa.Numeric(12, 4),
        type_=sa.Numeric(7, 4),
        existing_nullable=False,
    )
