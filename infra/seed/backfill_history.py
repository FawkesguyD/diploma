"""Backfill ~6 months of synthetic-but-plausible analytics history.

Цель: чтобы дашборды показывали многомесячную динамику до защиты диплома.
Скрипт детерминированный (seed=42) и идемпотентный по диапазону дат — повторный
запуск перезатрёт партиции тех же дней.

Запуск из корня репозитория:
    python3 infra/seed/backfill_history.py [--months 6]

Требуется только стандартная библиотека Python 3.11+ и запущенный compose.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import random
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

SOURCE_TG = "1d3800dd-de64-40fa-b8f8-86be8792d460"
SOURCE_RSS = "454366fe-adaf-45a5-bf3e-765aa47ce20b"
SOURCE_RE = "bd1bd003-3e86-48b4-8c3b-831c0f670088"
MODEL_RUN_NLP = "00000000-0000-0000-0000-000000000001"
MODEL_RUN_RE = "bcb993d7-2a51-4da3-9e99-febefcbbca09"
MODEL_VERSION = "v2_russia2021"

TOPICS = [
    "mortgage_rates",
    "developers",
    "primary_market",
    "secondary_market",
    "commercial_realty",
    "price_trends",
    "districts_msk",
    "districts_spb",
    "badaevsky_complex",
]

DEVELOPERS = ["Capital Group", "ПИК", "Самолёт", "Эталон", "ЛСР"]

# city -> [(slug, lat, lon, base_price_per_m2)]
DISTRICTS: dict[str, list[tuple[str, float, float, float]]] = {
    "Moscow": [
        ("presnenskiy", 55.760, 37.580, 460_000),
        ("gagarinskiy", 55.711, 37.580, 380_000),
        ("ramenki", 55.726, 37.516, 320_000),
        ("begovoy", 55.781, 37.553, 340_000),
        ("khamovniki", 55.732, 37.587, 520_000),
        ("tverskoy", 55.770, 37.605, 540_000),
    ],
    "Saint-Petersburg": [
        ("vyborgskiy", 60.038, 30.343, 220_000),
        ("petrogradskiy", 59.967, 30.310, 280_000),
        ("nevskiy", 59.917, 30.418, 200_000),
    ],
}

CHANNELS = [
    ("tg", "t.me", SOURCE_TG),
    ("rss", "lenta.ru", SOURCE_RSS),
    ("rss", "rbc.ru", SOURCE_RSS),
    ("rss", "vedomosti.ru", SOURCE_RSS),
]

LISTING_SITES = [
    ("cian.ru", SOURCE_RE),
    ("avito.ru", SOURCE_RE),
    ("domclick.ru", SOURCE_RE),
]


def ch(query: str, *, data: bytes | None = None) -> str:
    cmd = [
        "docker", "exec", "-i", "diploma-clickhouse-1",
        "clickhouse-client", "-u", "diploma", "--password", "diploma",
        "--database", "diploma", "--query", query,
    ]
    res = subprocess.run(cmd, input=data, capture_output=True, check=False)
    if res.returncode != 0:
        sys.stderr.write(res.stderr.decode("utf-8", "replace"))
        raise SystemExit(f"ClickHouse query failed: {query[:120]}")
    return res.stdout.decode("utf-8", "replace")


def fmt_dt(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S.") + f"{d.microsecond // 1000:03d}"


def gen_messages(rng: random.Random, start: datetime, end: datetime) -> list[list]:
    """events_messages CSV rows (column order matches DESCRIBE)."""
    rows: list[list] = []
    day = start
    msg_seq = 0
    while day <= end:
        # seasonality: more activity Mon-Fri, dip Aug, peak Mar/Sep
        weekday_factor = 1.2 if day.weekday() < 5 else 0.6
        month = day.month
        season = {1: 0.8, 2: 0.9, 3: 1.3, 4: 1.1, 5: 1.0,
                  6: 0.95, 7: 0.85, 8: 0.7, 9: 1.35,
                  10: 1.15, 11: 1.05, 12: 0.9}[month]
        per_day = max(8, int(rng.gauss(35, 8) * weekday_factor * season))
        for _ in range(per_day):
            ch_kind, ch_site, src = rng.choices(
                CHANNELS, weights=[3, 2, 2, 2], k=1
            )[0]
            topic = rng.choice(TOPICS)
            topic_score = round(rng.uniform(0.45, 0.95), 2)
            topics_all = sorted({topic, *rng.sample(TOPICS, k=rng.randint(0, 2))})
            # sentiment: drift slightly per month so charts move
            base_sent = 0.5 + 0.2 * math.sin(month / 12 * 2 * math.pi)
            score = max(0.05, min(0.95, rng.gauss(base_sent, 0.18)))
            if score > 0.6:
                label = "positive"
            elif score < 0.4:
                label = "negative"
            else:
                label = "neutral"
            is_ad = 1 if rng.random() < 0.04 else 0
            # entities: districts referenced in ~40% of messages
            ent_districts: list[str] = []
            if rng.random() < 0.45:
                city = rng.choices(["Moscow", "Saint-Petersburg"],
                                    weights=[3, 1], k=1)[0]
                ent_districts = [rng.choice(DISTRICTS[city])[0]]
                if rng.random() < 0.2:
                    ent_districts.append(rng.choice(DISTRICTS[city])[0])
            ent_devs: list[str] = []
            if rng.random() < 0.18:
                ent_devs = [rng.choice(DEVELOPERS)]

            published = day + timedelta(
                hours=rng.randint(0, 23),
                minutes=rng.randint(0, 59),
                seconds=rng.randint(0, 59),
            )
            event_t = published + timedelta(seconds=rng.randint(2, 90))
            msg_seq += 1
            mid = f"seed:{day:%Y%m%d}:{msg_seq:05d}"
            rows.append([
                fmt_dt(event_t),
                fmt_dt(published),
                mid,
                src,
                ch_kind,
                ch_site,
                topic,
                topic_score,
                "['" + "','".join(topics_all) + "']",
                label,
                round(score, 3),
                is_ad,
                "ru",
                "['" + "','".join(ent_districts) + "']" if ent_districts else "[]",
                "['" + "','".join(ent_devs) + "']" if ent_devs else "[]",
                MODEL_RUN_NLP,
            ])
        day += timedelta(days=1)
    return rows


@dataclass
class ListingFixture:
    object_id: str
    src: str
    site: str
    city: str
    district: str
    rooms: int
    area: float
    floor: int
    year_built: int
    base_ppm: float


def gen_listings_pool(rng: random.Random, n: int = 350) -> list[ListingFixture]:
    pool: list[ListingFixture] = []
    for i in range(n):
        site, src = rng.choice(LISTING_SITES)
        city = rng.choices(["Moscow", "Saint-Petersburg"],
                            weights=[4, 1], k=1)[0]
        district, _, _, base_ppm = rng.choice(DISTRICTS[city])
        rooms = rng.choices([1, 2, 3, 4], weights=[3, 4, 3, 1], k=1)[0]
        area = round(rng.gauss({1: 38, 2: 55, 3: 78, 4: 105}[rooms], 8), 1)
        area = max(20.0, area)
        floor = rng.randint(1, 25)
        year_built = rng.randint(1965, 2025)
        oid = f"6a{i:022x}"  # 24-hex pseudo-ObjectId
        pool.append(ListingFixture(
            object_id=oid,
            src=src,
            site=site,
            city=city,
            district=district,
            rooms=rooms,
            area=area,
            floor=floor,
            year_built=year_built,
            base_ppm=base_ppm,
        ))
    return pool


def gen_prices(rng: random.Random, start: datetime, end: datetime,
                pool: list[ListingFixture]) -> list[list]:
    """events_prices rows. Each listing emits 1-3 events over the window."""
    rows: list[list] = []
    span_days = (end - start).days
    for fx in pool:
        # 1-3 observations spread across the window
        n_obs = rng.choices([1, 2, 3], weights=[5, 3, 2], k=1)[0]
        offsets = sorted(rng.sample(range(span_days + 1), k=min(n_obs, span_days + 1)))
        for off in offsets:
            ts = start + timedelta(days=off,
                                    hours=rng.randint(8, 22),
                                    minutes=rng.randint(0, 59))
            # price drift: +6% YoY, small random walk per month, district premium
            months_passed = (ts - start).days / 30.0
            yearly_drift = 1.0 + 0.005 * months_passed  # ~0.5%/month → 6%/yr
            seasonal = 1.0 + 0.02 * math.sin((ts.month / 12) * 2 * math.pi)
            noise = rng.gauss(1.0, 0.07)
            ppm_real = fx.base_ppm * yearly_drift * seasonal * noise
            price_real = round(ppm_real * fx.area, 2)
            # model prediction: ground truth-ish + noise; some listings undervalued
            pred_noise = rng.gauss(1.0, 0.09)
            price_pred = round(ppm_real * fx.area * pred_noise, 2)
            dev_abs = price_real - price_pred
            dev_pct = round(dev_abs / price_pred * 100, 4) if price_pred else 0.0
            is_und = 1 if dev_pct < -8.0 else 0
            rows.append([
                fmt_dt(ts + timedelta(seconds=rng.randint(1, 30))),
                fmt_dt(ts),
                fx.object_id,
                fx.src,
                "residential",
                fx.site,
                fx.city,
                fx.district,
                fx.rooms,
                fx.area,
                fx.floor,
                fx.year_built,
                price_real,
                price_pred,
                round(dev_abs, 2),
                dev_pct,
                is_und,
                0,  # rank_in_run filled later per day if needed
                MODEL_VERSION,
                MODEL_RUN_RE,
            ])
    return rows


def csv_bytes(rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    for r in rows:
        w.writerow(r)
    return buf.getvalue().encode("utf-8")


def truncate_range(table: str, start: datetime, end: datetime) -> None:
    day = start
    parts: list[str] = []
    while day <= end:
        parts.append(day.strftime("%Y%m%d"))
        day += timedelta(days=1)
    for p in parts:
        ch(f"ALTER TABLE {table} DROP PARTITION '{p}'")


def insert_chunked(table: str, rows: list[list], event_time_idx: int) -> None:
    by_month: dict[str, list[list]] = {}
    for r in rows:
        key = str(r[event_time_idx])[:7]
        by_month.setdefault(key, []).append(r)
    for month in sorted(by_month):
        chunk = by_month[month]
        ch(f"INSERT INTO {table} FORMAT CSV", data=csv_bytes(chunk))
        print(f"        + {month}: {len(chunk):,} rows")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    end = datetime(2026, 5, 15, tzinfo=timezone.utc).replace(tzinfo=None)
    start = end - timedelta(days=args.months * 30)
    print(f"[seed] window: {start.date()} → {end.date()}")

    print("[seed] generating events_messages …")
    msg_rows = gen_messages(rng, start, end)
    print(f"        {len(msg_rows):,} rows")

    print("[seed] generating events_prices …")
    pool = gen_listings_pool(rng, n=400)
    price_rows = gen_prices(rng, start, end, pool)
    print(f"        {len(price_rows):,} rows over {len(pool)} listings")

    # Idempotency: clear existing data in window first.
    print("[seed] truncating existing partitions in window …")
    truncate_range("events_messages", start, end)
    truncate_range("events_prices", start, end)

    print("[seed] inserting events_messages …")
    insert_chunked("events_messages", msg_rows, event_time_idx=0)
    print("[seed] inserting events_prices …")
    insert_chunked("events_prices", price_rows, event_time_idx=0)

    print("[seed] done.")
    print(ch("SELECT count(), min(event_time), max(event_time) FROM events_messages"))
    print(ch("SELECT count(), min(event_time), max(event_time) FROM events_prices"))


if __name__ == "__main__":
    main()
