from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", "/tmp/real_estate_analytics_matplotlib")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.exc import SQLAlchemyError

from model.analytics.config import AnalyticsConfig
from model.services.data_migrator.russia2021_control import run_russia2021_control_pipeline


def _parse_args() -> argparse.Namespace:
    defaults = AnalyticsConfig.from_env()
    parser = argparse.ArgumentParser(description="Загрузка контрольной выборки analytics в PostgreSQL.")
    parser.add_argument("--sample-size", type=int, default=defaults.control_sample_size, help="Размер выборки.")
    parser.add_argument("--sample-seed", type=int, default=defaults.control_sample_seed, help="Seed выборки.")
    parser.add_argument(
        "--max-source-rows",
        type=int,
        default=defaults.max_rows,
        help="Deprecated; Russia 2021 streaming import scans the selected source.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    stats = run_russia2021_control_pipeline(
        sample_size=args.sample_size,
        sample_seed=args.sample_seed,
        source="auto",
    )
    print(json.dumps(asdict(stats), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SQLAlchemyError as exc:
        print(
            "Ошибка подключения к БД analytics control sample. Проверьте DATABASE_URL и PostgreSQL. "
            f"Детали: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)
