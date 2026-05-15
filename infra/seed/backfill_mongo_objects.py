"""Mirror CH backfill into Mongo: objects + annotated_objects.

Каждой синтетической записи из events_prices даём документ в objects (по
последнему наблюдению) и annotated_object с предсказанием. Это нужно чтобы
страницы /objects и /objects/top-undervalued показывали ту же историю,
что и дашборды.

Запуск: python3 infra/seed/backfill_mongo_objects.py
"""
from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

SOURCE_RE = "bd1bd003-3e86-48b4-8c3b-831c0f670088"
MODEL_VERSION = "v2_russia2021"
MODEL_RUN_RE = "bcb993d7-2a51-4da3-9e99-febefcbbca09"

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
LISTING_SITES = [("cian.ru", SOURCE_RE), ("avito.ru", SOURCE_RE), ("domclick.ru", SOURCE_RE)]


def mongo(js: str, *, stdin: str | None = None) -> str:
    cmd = [
        "docker", "exec", "-i", "diploma-mongo-1",
        "mongosh", "mongodb://diploma:diploma@localhost:27017/?authSource=admin",
        "--quiet", "--eval", js,
    ]
    res = subprocess.run(cmd, input=stdin, capture_output=True, check=False, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        raise SystemExit("mongosh failed")
    return res.stdout


def insert_chunked(collection: str, docs: list[dict], chunk: int = 100) -> None:
    for i in range(0, len(docs), chunk):
        batch = docs[i:i + chunk]
        payload = json.dumps(batch, ensure_ascii=False)
        mongo(
            f'db = db.getSiblingDB("diploma"); '
            f'db.{collection}.insertMany(EJSON.deserialize({payload}));'
        )
        print(f"        + {collection}: {i + len(batch)}/{len(docs)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n", type=int, default=400)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    end = datetime(2026, 5, 15, tzinfo=timezone.utc)
    start = end - timedelta(days=args.months * 30)

    objects: list[dict] = []
    annotated: list[dict] = []
    for i in range(args.n):
        site, src = rng.choice(LISTING_SITES)
        city = rng.choices(["Moscow", "Saint-Petersburg"], weights=[4, 1], k=1)[0]
        district, lat, lon, base_ppm = rng.choice(DISTRICTS[city])
        rooms = rng.choices([1, 2, 3, 4], weights=[3, 4, 3, 1], k=1)[0]
        area = max(20.0, round(rng.gauss({1: 38, 2: 55, 3: 78, 4: 105}[rooms], 8), 1))
        floor = rng.randint(1, 25)
        year_built = rng.randint(1965, 2025)
        oid_hex = f"6a{i:022x}"

        ts = start + timedelta(days=rng.randint(0, args.months * 30 - 1),
                                hours=rng.randint(0, 23))
        months_passed = (ts - start).days / 30.0
        ppm = base_ppm * (1.0 + 0.005 * months_passed) * \
              (1.0 + 0.02 * math.sin((ts.month / 12) * 2 * math.pi)) * rng.gauss(1.0, 0.07)
        price_real = round(ppm * area, 2)
        price_pred = round(price_real * rng.gauss(1.0, 0.09), 2)
        dev_abs = price_real - price_pred
        dev_pct = round(dev_abs / price_pred * 100, 4) if price_pred else 0.0
        is_und = bool(dev_pct < -8.0)
        ann_oid_hex = f"7b{i:022x}"

        objects.append({
            "_id": {"$oid": oid_hex},
            "external_id": f"seed:{site.split('.')[0]}:{i:05d}",
            "source_id": src,
            "channel_site": site,
            "object_kind": "residential",
            "url": f"https://{site}/object/{i}",
            "status": "active",
            "history": [],
            "published_at": {"$date": ts.isoformat().replace("+00:00", "Z")},
            "fetched_at": {"$date": ts.isoformat().replace("+00:00", "Z")},
            "created_at": {"$date": ts.isoformat().replace("+00:00", "Z")},
            "updated_at": {"$date": ts.isoformat().replace("+00:00", "Z")},
            "listing": {
                "price": price_real,
                "currency": "RUB",
                "area": area,
                "rooms": rooms,
                "floor": floor,
                "total_floors": floor + rng.randint(0, 10),
                "year_built": year_built,
                "address": {
                    "raw": f"{city}, район {district}",
                    "city": city,
                    "district_slug": district,
                    "lat": lat + rng.uniform(-0.01, 0.01),
                    "lon": lon + rng.uniform(-0.01, 0.01),
                },
                "features": [],
            },
        })
        annotated.append({
            "_id": {"$oid": ann_oid_hex},
            "object_id": {"$oid": oid_hex},
            "model_run_id": MODEL_RUN_RE,
            "model_version": MODEL_VERSION,
            "module": "realestate",
            "predicted_price": price_pred,
            "deviation_abs": round(dev_abs, 2),
            "deviation_pct": dev_pct,
            "is_undervalued": is_und,
            "rank_in_run": None,
            "features_used": {
                "area": area, "rooms": rooms, "floor": floor,
                "year_built": year_built, "district": district,
            },
            "is_active": True,
            "computed_at": {"$date": ts.isoformat().replace("+00:00", "Z")},
            "created_at": {"$date": ts.isoformat().replace("+00:00", "Z")},
            "updated_at": {"$date": ts.isoformat().replace("+00:00", "Z")},
        })

    obj_json = json.dumps(objects, ensure_ascii=False)
    ann_json = json.dumps(annotated, ensure_ascii=False)

    print(f"[seed-mongo] {len(objects)} objects, {len(annotated)} annotated")
    print("[seed-mongo] removing previous seed:* …")
    mongo('db = db.getSiblingDB("diploma"); '
          'r1 = db.objects.deleteMany({external_id: {$regex: "^seed:"}}); '
          'r2 = db.annotated_objects.deleteMany({model_run_id: "' + MODEL_RUN_RE + '"}); '
          'print("deleted objects:", r1.deletedCount, "annotations:", r2.deletedCount);')

    print("[seed-mongo] inserting objects …")
    insert_chunked("objects", objects, chunk=80)

    print("[seed-mongo] inserting annotated_objects …")
    insert_chunked("annotated_objects", annotated, chunk=80)

    print(mongo('db = db.getSiblingDB("diploma"); '
                'print("objects total:", db.objects.countDocuments({})); '
                'print("annotated total:", db.annotated_objects.countDocuments({})); '
                'print("undervalued:", db.annotated_objects.countDocuments({is_undervalued: true}));'))


if __name__ == "__main__":
    main()
