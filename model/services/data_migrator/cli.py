from __future__ import annotations

import argparse
import logging

from model.services.data_migrator.bootstrap import bootstrap_database


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def main() -> int:
    configure_logging()

    parser = argparse.ArgumentParser(
        description="Initialize PostgreSQL schema, import Russia 2021 control objects, and backfill valuations.",
    )
    parser.add_argument(
        "--csv-path",
        dest="csv_path",
        default=None,
        help="Deprecated legacy option kept for compatibility; Russia 2021 control import is used.",
    )
    args = parser.parse_args()

    stats = bootstrap_database(args.csv_path)

    print(f"Russia 2021 source: {stats.source_description}")
    print(f"Source rows read: {stats.source_rows_read}")
    print(f"Selected rows: {stats.selected_rows}")
    print(f"Inserted control rows: {stats.inserted_rows}")
    print(f"Skipped invalid rows: {stats.skipped_invalid_rows}")
    print(f"Valuations saved: {stats.valuations_saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
