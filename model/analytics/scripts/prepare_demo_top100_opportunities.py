from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import pandas as pd
from sqlalchemy import func, select, text


ROOT_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT_DIR / "analytics" / "reports"
TOP100_REPORT_PATH = REPORTS_DIR / "demo_top100_opportunities.csv"
TOP10_REPORT_PATH = REPORTS_DIR / "demo_top10_opportunities.csv"
COMMON_TRAITS_PATH = REPORTS_DIR / "demo_top10_common_traits.md"

DEMO_BATCH = "demo_top100"
DEMO_SAMPLE_SEED = 42
ARCHIVE_SAMPLE_SEED_START = 1042
DEMO_SIZE = 100
RANDOM_STATE = 42


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def configure_runtime_environment() -> None:
    load_dotenv(ROOT_DIR / ".env")
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        parts = urlsplit(database_url)
        if parts.hostname == "postgres":
            username = quote(unquote(parts.username or os.getenv("POSTGRES_USER", "realestate")))
            password_value = parts.password or os.getenv("POSTGRES_PASSWORD", "realestate")
            password = quote(unquote(password_value))
            port = os.getenv("POSTGRES_PORT") or str(parts.port or 5432)
            database = parts.path.lstrip("/") or os.getenv("POSTGRES_DB", "realestate")
            os.environ["DATABASE_URL"] = f"{parts.scheme}://{username}:{password}@localhost:{port}/{database}"

    for env_name in ("MODEL_PATH", "MODEL_READINESS_PATH"):
        value = os.getenv(env_name)
        if value and value.startswith("/app/"):
            os.environ[env_name] = str(ROOT_DIR / value.removeprefix("/app/"))

    readiness_path = Path(os.getenv("MODEL_READINESS_PATH", ROOT_DIR / "ml/artifacts/model_readiness.json"))
    if not readiness_path.is_absolute():
        readiness_path = ROOT_DIR / readiness_path
    if readiness_path.exists():
        readiness_payload = json.loads(readiness_path.read_text(encoding="utf-8"))
        active_model_path = readiness_payload.get("active_model_path")
        if active_model_path:
            model_path = Path(str(active_model_path))
            if not model_path.is_absolute():
                model_path = readiness_path.parent / model_path
            os.environ["MODEL_PATH"] = str(model_path)
            os.environ["MODEL_READINESS_PATH"] = str(readiness_path)

    os.environ.setdefault("CONTROL_OBJECT_SAMPLE_SEED", str(DEMO_SAMPLE_SEED))


configure_runtime_environment()

from model.apps.api.api import _build_scoring_payload, ensure_listing_valuations, get_model_bundle  # noqa: E402
from model.ml.model.inference_validation import validate_inference_record  # noqa: E402
from model.shared.db.models import AnalyticsControlObject, Valuation  # noqa: E402
from model.shared.db.session import SessionLocal  # noqa: E402


@dataclass(frozen=True)
class PreparationSummary:
    selected_count: int
    archived_count: int
    valuation_rows_upserted: int
    valuations_before: int
    valuations_after: int
    active_model_name: str
    active_model_path: str | None


def _json_copy(payload: dict[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


def _source_priority_label() -> str:
    return "analytics_control_objects"


def fetch_control_candidates() -> pd.DataFrame:
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                select
                  id,
                  coalesce(listing_id, id) as effective_listing_id,
                  source_object_id,
                  listing_id,
                  title,
                  city,
                  district,
                  region,
                  area::float as area,
                  rooms,
                  floor,
                  total_floors,
                  level,
                  levels,
                  building_type,
                  condition,
                  year_built,
                  seller_type,
                  object_type,
                  latitude::float as latitude,
                  longitude::float as longitude,
                  listing_price::float as listing_price,
                  listing_currency,
                  source_url,
                  source_payload,
                  sample_seed,
                  sample_rank
                from analytics_control_objects
                where listing_price is not null
                  and listing_price > 0
                  and area is not null
                  and area > 0
                  and coalesce(listing_currency, 'RUB') = 'RUB'
                order by sample_seed, sample_rank, id
                """
            )
        ).mappings().all()

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = frame.drop_duplicates(subset=["effective_listing_id"], keep="first")
    return frame.reset_index(drop=True)


def _none_if_missing(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    return value


def filter_pipeline_valid_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    bundle = get_model_bundle()
    valid_ids: list[int] = []
    for record in candidates.to_dict(orient="records"):
        row = {key: _none_if_missing(value) for key, value in record.items()}
        try:
            payload = _build_scoring_payload(row, bundle)
            validation = validate_inference_record(payload, bundle.feature_config, bundle.metadata)
        except Exception:
            continue
        if validation.is_valid:
            valid_ids.append(int(row["id"]))

    return candidates[candidates["id"].isin(valid_ids)].reset_index(drop=True)


def select_demo_rows(candidates: pd.DataFrame) -> pd.DataFrame:
    valid_candidates = filter_pipeline_valid_candidates(candidates)
    if len(valid_candidates) < DEMO_SIZE:
        raise RuntimeError(
            f"Need {DEMO_SIZE} pipeline-valid objects from analytics_control_objects, "
            f"found {len(valid_candidates)}."
        )
    selected = valid_candidates.sample(n=DEMO_SIZE, random_state=RANDOM_STATE).reset_index(drop=True)
    selected["demo_rank"] = selected.index + 1
    return selected


def choose_archive_seed(session) -> int:
    seed = ARCHIVE_SAMPLE_SEED_START
    while True:
        exists = session.execute(
            select(func.count()).select_from(AnalyticsControlObject).where(
                AnalyticsControlObject.sample_seed == seed
            )
        ).scalar_one()
        if not exists:
            return seed
        seed += 1


def activate_demo_rows(selected: pd.DataFrame) -> int:
    selected_ids = {int(item) for item in selected["id"].tolist()}
    rank_by_id = {int(row.id): int(row.demo_rank) for row in selected.itertuples(index=False)}

    with SessionLocal() as session:
        active_non_demo = session.execute(
            select(AnalyticsControlObject).where(
                AnalyticsControlObject.sample_seed == DEMO_SAMPLE_SEED,
                AnalyticsControlObject.id.not_in(selected_ids),
            )
        ).scalars().all()

        archived_count = 0
        if active_non_demo:
            archive_seed = choose_archive_seed(session)
            for index, row in enumerate(active_non_demo, start=1):
                payload = _json_copy(row.source_payload)
                payload.setdefault("archived_from_sample_seed", DEMO_SAMPLE_SEED)
                payload["archived_for_demo_batch"] = DEMO_BATCH
                row.sample_seed = archive_seed
                row.sample_rank = index
                row.source_payload = payload
            archived_count = len(active_non_demo)
            session.flush()

        selected_rows = session.execute(
            select(AnalyticsControlObject).where(AnalyticsControlObject.id.in_(selected_ids))
        ).scalars().all()
        for row in selected_rows:
            demo_rank = rank_by_id[int(row.id)]
            payload = _json_copy(row.source_payload)
            payload.setdefault("original_source_object_id", row.source_object_id)
            payload["demo_batch"] = DEMO_BATCH
            payload["demo_random_state"] = RANDOM_STATE
            payload["demo_source"] = _source_priority_label()
            payload["demo_rank"] = demo_rank
            row.sample_seed = DEMO_SAMPLE_SEED
            row.sample_rank = demo_rank
            row.title = row.title or f"Demo top100 #{demo_rank}: {row.source_object_id}"
            row.source_payload = payload

        session.commit()
        return archived_count


def run_valuation_backfill() -> tuple[int, int, int, str, str | None]:
    bundle = get_model_bundle()
    readiness = (bundle.metadata or {}).get("readiness") or {}
    active_model_name = str(readiness.get("active_model_name") or bundle.model_name)
    active_model_path = readiness.get("active_model_path")

    with SessionLocal() as session:
        valuations_before = session.execute(select(func.count()).select_from(Valuation)).scalar_one()
        upserted = ensure_listing_valuations(
            session,
            only_missing=False,
            include_explanations=False,
        )

    with SessionLocal() as session:
        valuations_after = session.execute(select(func.count()).select_from(Valuation)).scalar_one()

    return int(upserted), int(valuations_before), int(valuations_after), active_model_name, active_model_path


def fetch_ranked_demo_frame() -> pd.DataFrame:
    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                select
                  row_number() over (
                    order by v.undervaluation_percent desc, v.score desc, coalesce(a.listing_id, a.id) asc
                  ) as rank,
                  coalesce(a.listing_id, a.id) as listing_id,
                  a.title,
                  a.region,
                  a.city,
                  coalesce(a.district, a.region) as district,
                  a.area::float as area,
                  a.area::float as total_area_m2,
                  a.rooms,
                  coalesce(a.floor, a.level) as floor,
                  coalesce(a.total_floors, a.levels) as total_floors,
                  a.building_type,
                  a.condition,
                  a.listing_price::float as listing_price,
                  v.predicted_price::float as predicted_price,
                  v.undervaluation_delta::float as delta_abs,
                  v.undervaluation_percent::float as delta_pct,
                  (v.undervaluation_percent::float * 100.0) as delta_pct_percent,
                  v.score::float as score,
                  a.source_url
                from analytics_control_objects a
                join valuations v on v.listing_id = coalesce(a.listing_id, a.id)
                where a.sample_seed = :sample_seed
                order by v.undervaluation_percent desc, v.score desc, coalesce(a.listing_id, a.id) asc
                """
            ),
            {"sample_seed": DEMO_SAMPLE_SEED},
        ).mappings().all()

    frame = pd.DataFrame(rows)
    if len(frame) != DEMO_SIZE:
        raise RuntimeError(f"Expected {DEMO_SIZE} ranked demo rows, got {len(frame)}.")
    if frame["predicted_price"].isna().any() or (frame["predicted_price"] <= 0).any():
        raise RuntimeError("Invalid predicted_price values found in demo valuation output.")
    if frame["delta_pct"].isna().any():
        raise RuntimeError("Invalid delta_pct values found in demo valuation output.")
    return frame


def _fmt_number(value: Any, digits: int = 2) -> str:
    if pd.isna(value):
        return ""
    return f"{float(value):,.{digits}f}"


def _mode_list(series: pd.Series, limit: int = 5) -> str:
    values = series.dropna().astype(str)
    values = values[values.str.strip() != ""]
    if values.empty:
        return "n/a"
    return ", ".join(values.value_counts().head(limit).index.tolist())


def dataframe_to_markdown(frame: pd.DataFrame) -> str:
    columns = [str(column) for column in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in frame.itertuples(index=False):
        values = []
        for value in row:
            if pd.isna(value):
                values.append("")
            elif isinstance(value, float):
                values.append(f"{value:.2f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_reports(frame: pd.DataFrame) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_columns = [
        "rank",
        "listing_id",
        "title",
        "region",
        "city",
        "district",
        "area",
        "total_area_m2",
        "rooms",
        "floor",
        "total_floors",
        "building_type",
        "condition",
        "listing_price",
        "predicted_price",
        "delta_abs",
        "delta_pct",
        "delta_pct_percent",
        "score",
        "source_url",
    ]
    frame[output_columns].to_csv(TOP100_REPORT_PATH, index=False)
    frame.head(10)[output_columns].to_csv(TOP10_REPORT_PATH, index=False)
    write_common_traits_markdown(frame)


def write_common_traits_markdown(frame: pd.DataFrame) -> None:
    top10 = frame.head(10).copy()
    rest = frame.iloc[10:].copy()

    def stats_block(label: str, data: pd.DataFrame) -> dict[str, str]:
        return {
            "group": label,
            "count": str(len(data)),
            "mean_area": _fmt_number(data["area"].mean()),
            "median_area": _fmt_number(data["area"].median()),
            "mean_rooms": _fmt_number(data["rooms"].mean()),
            "mean_listing_price": _fmt_number(data["listing_price"].mean()),
            "mean_predicted_price": _fmt_number(data["predicted_price"].mean()),
            "mean_delta_pct": _fmt_number(data["delta_pct"].mean() * 100.0),
            "top_regions": _mode_list(data["region"].fillna(data["city"]).fillna(data["district"])),
            "top_building_types": _mode_list(data["building_type"]),
            "top_conditions": _mode_list(data["condition"]),
        }

    comparison = pd.DataFrame([stats_block("top-10", top10), stats_block("other-90", rest)])
    top10_table = top10[
        [
            "rank",
            "listing_id",
            "district",
            "area",
            "rooms",
            "floor",
            "total_floors",
            "listing_price",
            "predicted_price",
            "delta_abs",
            "delta_pct_percent",
        ]
    ].copy()
    top10_table["delta_pct_percent"] = top10_table["delta_pct_percent"].map(lambda value: round(value, 2))

    common_traits = [
        "# Demo top-10 common traits",
        "",
        "## Top-10",
        "",
        dataframe_to_markdown(top10_table),
        "",
        "## Top-10 vs other 90",
        "",
        dataframe_to_markdown(comparison),
        "",
        "## Summary",
        "",
        (
            f"Top-10 objects have mean area {_fmt_number(top10['area'].mean())} m2 versus "
            f"{_fmt_number(rest['area'].mean())} m2 for the remaining 90."
        ),
        (
            f"Their average listing price is {_fmt_number(top10['listing_price'].mean())} RUB, "
            f"while the average model estimate is {_fmt_number(top10['predicted_price'].mean())} RUB."
        ),
        (
            f"The average delta_pct in top-10 is {_fmt_number(top10['delta_pct'].mean() * 100.0)}%, "
            f"which is higher than {_fmt_number(rest['delta_pct'].mean() * 100.0)}% for the rest."
        ),
        (
            f"Frequent regions or districts in top-10: "
            f"{_mode_list(top10['region'].fillna(top10['city']).fillna(top10['district']))}."
        ),
        (
            f"Common building or condition labels in top-10: "
            f"{_mode_list(top10['building_type'])}; {_mode_list(top10['condition'])}."
        ),
        "",
    ]
    COMMON_TRAITS_PATH.write_text("\n".join(common_traits), encoding="utf-8")


def print_top10(frame: pd.DataFrame, summary: PreparationSummary) -> None:
    columns = [
        "rank",
        "listing_id",
        "area",
        "rooms",
        "floor",
        "total_floors",
        "listing_price",
        "predicted_price",
        "delta_abs",
        "delta_pct_percent",
        "district",
    ]
    print("Demo top-100 preparation complete")
    print(json.dumps(summary.__dict__, ensure_ascii=False, indent=2))
    print(frame.head(10)[columns].to_string(index=False))
    print(f"Saved: {TOP100_REPORT_PATH}")
    print(f"Saved: {TOP10_REPORT_PATH}")
    print(f"Saved: {COMMON_TRAITS_PATH}")


def main() -> None:
    candidates = fetch_control_candidates()
    selected = select_demo_rows(candidates)
    archived_count = activate_demo_rows(selected)
    upserted, before, after, model_name, model_path = run_valuation_backfill()
    frame = fetch_ranked_demo_frame()
    write_reports(frame)
    summary = PreparationSummary(
        selected_count=len(selected),
        archived_count=archived_count,
        valuation_rows_upserted=upserted,
        valuations_before=before,
        valuations_after=after,
        active_model_name=model_name,
        active_model_path=model_path,
    )
    print_top10(frame, summary)


if __name__ == "__main__":
    main()
