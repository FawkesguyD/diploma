from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from model.shared.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    shortlist_items: Mapped[list["ShortlistItem"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (Index("ix_listings_city_district", "city", "district"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    district: Mapped[str | None] = mapped_column(String(255), nullable=True)
    area: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    living_area_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    kitchen_area_m2: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ceiling_height: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    building_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    building_series: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    heating: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gas_supply: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bathroom: Mapped[str | None] = mapped_column(String(255), nullable=True)
    balcony: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parking: Mapped[str | None] = mapped_column(String(255), nullable=True)
    furniture: Mapped[str | None] = mapped_column(String(255), nullable=True)
    flooring: Mapped[str | None] = mapped_column(String(255), nullable=True)
    door_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    has_landline_phone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    internet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mortgage: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    photo_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    listing_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    listing_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="RUB")
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    valuation: Mapped["Valuation | None"] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        uselist=False,
    )
    shortlist_items: Mapped[list["ShortlistItem"]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
    )


class Valuation(Base):
    __tablename__ = "valuations"
    __table_args__ = (
        Index("ix_valuations_score", "score"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    predicted_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    undervaluation_delta: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    undervaluation_percent: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(7, 4), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium", server_default="medium")
    warnings: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
    )
    sanity_checks: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'::json"),
    )
    explanation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_factors: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
    )

    listing: Mapped[Listing] = relationship(back_populates="valuation")


class AnalyticsControlObject(Base):
    __tablename__ = "analytics_control_objects"
    __table_args__ = (
        UniqueConstraint("sample_seed", "source_object_id", name="uq_analytics_control_objects_seed_source"),
        Index("ix_analytics_control_objects_seed_rank", "sample_seed", "sample_rank"),
        Index("ix_analytics_control_objects_listing_id", "listing_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    source_object_id: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_listing_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    raw_listing_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    listing_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    listing_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    listing_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="RUB")
    target_proxy_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    target_source: Mapped[str] = mapped_column(String(64), nullable=False, server_default="listing_price_proxy")
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    district: Mapped[str | None] = mapped_column(String(255), nullable=True)
    area: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    rooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kitchen_area: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    levels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    floor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_floors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    building_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(255), nullable=True)
    year_built: Mapped[int | None] = mapped_column(Integer, nullable=True)
    seller_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 6), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    source_payload: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    sample_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class NormalizedListing(Base):
    __tablename__ = "normalized_listings"
    __table_args__ = (
        Index("ix_normalized_listings_raw_listing_id", "raw_listing_id"),
        Index("ix_normalized_listings_source_object_id", "source_object_id", unique=True),
        Index("ix_normalized_listings_listing_id", "listing_id"),
        Index("ix_normalized_listings_train_eligible", "is_train_eligible"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    raw_listing_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_object_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("listings.id", ondelete="SET NULL"),
        nullable=True,
    )
    normalized_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="accepted")
    validation_errors: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
    )
    validation_warnings: Mapped[list[str]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        server_default=text("'[]'::json"),
    )
    is_train_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    normalized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TrainingRun(Base):
    __tablename__ = "training_runs"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="training")
    artifact_path: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'::json"))
    metadata_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'::json"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelVersion(Base):
    __tablename__ = "model_versions"
    __table_args__ = (
        Index("ix_model_versions_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_path: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="validated")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    base_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="RUB")
    readiness_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'::json"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ValidationReport(Base):
    __tablename__ = "validation_reports"
    __table_args__ = (
        Index("ix_validation_reports_model_version_id", "model_version_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    report_type: Mapped[str] = mapped_column(String(255), nullable=False)
    report_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SegmentMetric(Base):
    __tablename__ = "segment_metrics"
    __table_args__ = (
        Index("ix_segment_metrics_model_segment", "model_version_id", "segment_name"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    model_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("model_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    segment_name: Mapped[str] = mapped_column(String(255), nullable=False)
    segment_value: Mapped[str] = mapped_column(String(255), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ShortlistItem(Base):
    __tablename__ = "shortlist_items"
    __table_args__ = (
        Index("ix_shortlist_items_user_id", "user_id"),
        Index("ix_shortlist_items_listing_id", "listing_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
    )
    rank_position: Mapped[int] = mapped_column(Integer, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    user: Mapped[User] = relationship(back_populates="shortlist_items")
    listing: Mapped[Listing] = relationship(back_populates="shortlist_items")
