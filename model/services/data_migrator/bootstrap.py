from __future__ import annotations

import logging
import time
from pathlib import Path
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from model.services.data_migrator.russia2021_control import ControlPipelineStats, run_russia2021_control_pipeline
from model.shared.auth import hash_password
from model.shared.db.models import User
from model.shared.db.session import create_db_engine, get_database_url
from model.shared.db.session import SessionLocal


LOGGER = logging.getLogger("services.data_migrator.bootstrap")
DEFAULT_MAX_RETRIES = 10
DEFAULT_RETRY_DELAY_SECONDS = 3
EXPECTED_TABLES = (
    "users",
    "analytics_control_objects",
    "normalized_listings",
    "listings",
    "valuations",
    "shortlist_items",
    "training_runs",
    "model_versions",
    "validation_reports",
    "segment_metrics",
    "alembic_version",
)
REMOVED_TABLES = ("raw_listings",)
DEFAULT_DEMO_USER_NAME = "Demo Investor"
DEFAULT_DEMO_USER_EMAIL = "investor@example.com"
DEFAULT_DEMO_USER_PASSWORD = "demo12345"


def _build_alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    config.set_main_option("script_location", "alembic")
    return config


def wait_for_database(
    database_url: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_delay_seconds: int = DEFAULT_RETRY_DELAY_SECONDS,
) -> None:
    engine = create_db_engine(database_url)

    for attempt in range(1, max_retries + 1):
        try:
            LOGGER.info("db_connect_attempt attempt=%s/%s", attempt, max_retries)
            with engine.connect() as connection:
                current_database = connection.execute(text("select current_database()")).scalar_one()
                LOGGER.info("db_connect_ok database=%s", current_database)
                return
        except SQLAlchemyError as exc:
            LOGGER.warning(
                "db_connect_retry attempt=%s/%s delay_seconds=%s error=%s",
                attempt,
                max_retries,
                retry_delay_seconds,
                exc,
            )
            if attempt == max_retries:
                LOGGER.exception("db_connect_failed")
                raise
            time.sleep(retry_delay_seconds)
        finally:
            engine.dispose()


def run_migrations(database_url: str) -> None:
    LOGGER.info("migration_start")
    alembic_config = _build_alembic_config(database_url)
    command.upgrade(alembic_config, "head")
    LOGGER.info("migration_done")


def verify_database_state(database_url: str) -> dict[str, int]:
    engine = create_db_engine(database_url)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            existing_tables = set(inspector.get_table_names())
            missing_tables = [table_name for table_name in EXPECTED_TABLES if table_name not in existing_tables]
            if missing_tables:
                raise RuntimeError(f"Missing expected tables after bootstrap: {missing_tables}")
            removed_tables = [table_name for table_name in REMOVED_TABLES if table_name in existing_tables]
            if removed_tables:
                raise RuntimeError(f"Removed tables still exist after bootstrap: {removed_tables}")

            listing_count = connection.execute(text("select count(*) from listings")).scalar_one()
            control_count = connection.execute(text("select count(*) from analytics_control_objects")).scalar_one()
            valuation_count = connection.execute(text("select count(*) from valuations")).scalar_one()
            version_count = connection.execute(text("select count(*) from alembic_version")).scalar_one()
            result = {
                "listing_count": int(listing_count),
                "control_count": int(control_count),
                "valuation_count": int(valuation_count),
                "alembic_version_count": int(version_count),
            }
            LOGGER.info(
                "verification_done listing_count=%s control_count=%s valuation_count=%s alembic_version_count=%s",
                result["listing_count"],
                result["control_count"],
                result["valuation_count"],
                result["alembic_version_count"],
            )
            return result
    finally:
        engine.dispose()


def ensure_demo_user() -> None:
    demo_name = os.getenv("DEMO_USER_NAME", DEFAULT_DEMO_USER_NAME)
    demo_email = os.getenv("DEMO_USER_EMAIL", DEFAULT_DEMO_USER_EMAIL)
    demo_password = os.getenv("DEMO_USER_PASSWORD", DEFAULT_DEMO_USER_PASSWORD)

    with SessionLocal() as session:
        existing_user = session.query(User).filter(User.email == demo_email).one_or_none()
        password_hash = hash_password(demo_password)

        if existing_user is None:
            session.add(
                User(
                    name=demo_name,
                    email=demo_email,
                    password_hash=password_hash,
                )
            )
            LOGGER.info("demo_user_created email=%s", demo_email)
        else:
            existing_user.name = demo_name
            existing_user.password_hash = password_hash
            LOGGER.info("demo_user_updated email=%s", demo_email)

        session.commit()


def bootstrap_database(csv_path: str | Path | None = None) -> ControlPipelineStats:
    database_url = get_database_url()
    LOGGER.info("bootstrap_start")
    wait_for_database(database_url)
    run_migrations(database_url)
    LOGGER.info("russia2021_control_seed_start")
    stats = run_russia2021_control_pipeline()
    LOGGER.info(
        "russia2021_control_seed_done source_rows_read=%s inserted=%s skipped_invalid=%s valuations_saved=%s",
        stats.source_rows_read,
        stats.inserted_rows,
        stats.skipped_invalid_rows,
        stats.valuations_saved,
    )
    ensure_demo_user()
    verify_database_state(database_url)
    LOGGER.info("bootstrap_done")
    return stats
