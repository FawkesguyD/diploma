from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260417_000004"
down_revision = "20260408_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "valuations",
        sa.Column("confidence", sa.String(length=16), nullable=False, server_default="medium"),
    )
    op.add_column(
        "valuations",
        sa.Column("warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    op.add_column(
        "valuations",
        sa.Column("sanity_checks", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )

    op.create_table(
        "raw_listings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_raw_listings_source_external",
        "raw_listings",
        ["source_name", "external_id"],
        unique=True,
    )

    op.create_table(
        "normalized_listings",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("raw_listing_id", sa.BigInteger(), nullable=False),
        sa.Column("listing_id", sa.BigInteger(), nullable=True),
        sa.Column("normalized_payload", sa.JSON(), nullable=False),
        sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="accepted"),
        sa.Column("validation_errors", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("validation_warnings", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("is_train_eligible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "normalized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["raw_listing_id"], ["raw_listings.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_normalized_listings_raw_listing_id",
        "normalized_listings",
        ["raw_listing_id"],
        unique=True,
    )
    op.create_index("ix_normalized_listings_listing_id", "normalized_listings", ["listing_id"])
    op.create_index("ix_normalized_listings_train_eligible", "normalized_listings", ["is_train_eligible"])

    op.create_table(
        "training_runs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("run_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="training"),
        sa.Column("artifact_path", sa.String(length=2048), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", name="uq_training_runs_run_id"),
    )

    op.create_table(
        "model_versions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("artifact_path", sa.String(length=2048), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="validated"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("base_currency", sa.String(length=3), nullable=False, server_default="RUB"),
        sa.Column("readiness_payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("artifact_path", name="uq_model_versions_artifact_path"),
    )
    op.create_index("ix_model_versions_active", "model_versions", ["is_active"])

    op.create_table(
        "validation_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("model_version_id", sa.BigInteger(), nullable=True),
        sa.Column("report_type", sa.String(length=255), nullable=False),
        sa.Column("report_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_validation_reports_model_version_id", "validation_reports", ["model_version_id"])

    op.create_table(
        "segment_metrics",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("model_version_id", sa.BigInteger(), nullable=True),
        sa.Column("segment_name", sa.String(length=255), nullable=False),
        sa.Column("segment_value", sa.String(length=255), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_segment_metrics_model_segment",
        "segment_metrics",
        ["model_version_id", "segment_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_segment_metrics_model_segment", table_name="segment_metrics")
    op.drop_table("segment_metrics")
    op.drop_index("ix_validation_reports_model_version_id", table_name="validation_reports")
    op.drop_table("validation_reports")
    op.drop_index("ix_model_versions_active", table_name="model_versions")
    op.drop_table("model_versions")
    op.drop_table("training_runs")
    op.drop_index("ix_normalized_listings_train_eligible", table_name="normalized_listings")
    op.drop_index("ix_normalized_listings_listing_id", table_name="normalized_listings")
    op.drop_index("ix_normalized_listings_raw_listing_id", table_name="normalized_listings")
    op.drop_table("normalized_listings")
    op.drop_index("ix_raw_listings_source_external", table_name="raw_listings")
    op.drop_table("raw_listings")

    op.drop_column("valuations", "sanity_checks")
    op.drop_column("valuations", "warnings")
    op.drop_column("valuations", "confidence")
