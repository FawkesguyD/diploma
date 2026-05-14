from __future__ import annotations

import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from model.ml.model.feature_schema import russia2021_feature_config
from model.ml.model.persistence import LoadedModelBundle, TARGET_TRANSFORM_LOG
from model.services.data_migrator.russia2021_control import (
    _build_control_candidate,
    build_control_sample_rows,
)


class _UnusedModel:
    pass


def _bundle() -> LoadedModelBundle:
    return LoadedModelBundle(
        model_name="russia2021_stub",
        model=_UnusedModel(),
        feature_config=russia2021_feature_config(),
        metrics={},
        target_column="price",
        log_target=True,
        target_transform=TARGET_TRANSFORM_LOG,
        base_currency="RUB",
        metadata={"category_values": {"region": ["9654"]}},
    )


def _row(price: float, *, area: float = 50.0, rooms: int = 2, level: int = 3) -> dict[str, float | int]:
    return {
        "target_log_price": math.log(price),
        "rooms": rooms,
        "area": area,
        "kitchen_area": 8.0,
        "level": level,
        "levels": 9,
        "latitude": 55.75,
        "longitude": 37.61,
        "building_type": 2,
        "object_type": 1,
        "region": 9654,
    }


class Russia2021ControlPipelineTests(unittest.TestCase):
    def test_prepared_pool_row_maps_to_control_candidate(self) -> None:
        candidate = _build_control_candidate(
            _row(5_000_000),
            source_label="daniilakk/Russia_Real_Estate_2021:prepared:train_pool",
            row_index=17,
            sample_seed=42,
            bundle=_bundle(),
        )

        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertAlmostEqual(candidate["listing_price"], 5_000_000.0)
        self.assertEqual(candidate["listing_currency"], "RUB")
        self.assertEqual(candidate["target_source"], "russia_2021_listing_price_proxy")
        self.assertEqual(candidate["area"], 50.0)
        self.assertEqual(candidate["floor"], 3)
        self.assertEqual(candidate["total_floors"], 9)
        self.assertEqual(candidate["building_type"], "panel")
        self.assertEqual(candidate["object_type"], "secondary")
        self.assertEqual(candidate["region"], "9654")
        self.assertIn("Russia_Real_Estate_2021", candidate["source_object_id"])

    def test_prepared_pool_sampling_is_deterministic(self) -> None:
        with TemporaryDirectory() as tmpdir:
            prepared_dir = Path(tmpdir)
            pd.DataFrame(
                [
                    _row(5_000_000, area=50),
                    _row(6_000_000, area=60),
                    _row(7_000_000, area=70),
                    _row(8_000_000, area=80),
                ]
            ).to_csv(prepared_dir / "train_pool.csv", index=False)
            pd.DataFrame([_row(4_000_000, area=45)]).to_csv(prepared_dir / "valid_pool.csv", index=False)

            first_rows, first_read, first_valid, first_skipped, _ = build_control_sample_rows(
                sample_size=3,
                sample_seed=7,
                source="prepared",
                data_path=prepared_dir / "missing.csv",
                source_url=None,
                prepared_dir=prepared_dir,
                split="train",
                chunk_size=2,
                bundle=_bundle(),
            )
            second_rows, second_read, second_valid, second_skipped, _ = build_control_sample_rows(
                sample_size=3,
                sample_seed=7,
                source="prepared",
                data_path=prepared_dir / "missing.csv",
                source_url=None,
                prepared_dir=prepared_dir,
                split="train",
                chunk_size=2,
                bundle=_bundle(),
            )

        self.assertEqual(first_read, 5)
        self.assertEqual(first_valid, 5)
        self.assertEqual(first_skipped, 0)
        self.assertEqual(second_read, first_read)
        self.assertEqual(second_valid, first_valid)
        self.assertEqual(second_skipped, first_skipped)
        self.assertEqual(
            [row["source_object_id"] for row in first_rows],
            [row["source_object_id"] for row in second_rows],
        )
        self.assertEqual([row["sample_rank"] for row in first_rows], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
