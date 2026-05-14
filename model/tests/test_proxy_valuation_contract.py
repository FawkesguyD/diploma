from __future__ import annotations

import unittest
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import joblib
import numpy as np

from model.apps.api.api import _build_scoring_payload, _serialize_opportunity
from model.ml.model.inference import LoadedModelBundle, load_model_bundle, predict_proxy_valuation_from_bundle
from model.ml.model.preprocessing import FeatureConfig


class _StubModel:
    def predict(self, frame):
        area = frame["total_area_m2"].fillna(0).astype(float)
        rooms = frame["rooms"].fillna(0).astype(float)
        return np.asarray((area * 1000.0) + (rooms * 5000.0), dtype=float)


def _make_bundle() -> LoadedModelBundle:
    feature_config = FeatureConfig(
        target_column="price",
        numerical_features=[
            "rooms",
            "total_area_m2",
            "floor",
            "total_floors",
            "latitude",
            "longitude",
            "photo_count",
        ],
        categorical_features=[
            "district",
            "building_type",
            "seller_type",
        ],
        derived_numeric_features=[],
        excluded_columns=[],
        log_target=False,
    )
    return LoadedModelBundle(
        model_name="linear_stub",
        model=_StubModel(),
        feature_config=feature_config,
        metrics={},
        target_column="price",
        log_target=False,
        base_currency="RUB",
    )


class ProxyValuationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bundle = _make_bundle()
        self.object_features = {
            "listing_id": 7,
            "listing_price": 9_000_000.0,
            "listing_currency": "RUB",
            "district": "Center",
            "rooms": 3,
            "floor": 4,
            "total_floors": 12,
            "total_area_m2": 110.0,
            "building_type": "brick",
            "seller_type": "owner",
            "latitude": 55.75,
            "longitude": 37.61,
            "photo_count": 12,
        }

    def test_rub_output_keeps_raw_listing_price_and_returns_rub_only_metrics(self) -> None:
        result = predict_proxy_valuation_from_bundle(
            object_features=self.object_features,
            bundle=self.bundle,
            include_explanation=False,
        )

        rub_output = result["price_outputs"]["RUB"]

        self.assertEqual(set(result["price_outputs"]), {"RUB"})
        self.assertEqual(result["base_currency"], "RUB")
        self.assertEqual(result["output_currency"], "RUB")
        self.assertIsNone(result["fx_rate_used"])
        self.assertEqual(result["listing_price"], 9_000_000.0)
        self.assertEqual(result["listing_currency"], "RUB")
        self.assertEqual(rub_output["listing_price_in_comparison_currency"], 9_000_000.0)
        self.assertEqual(result["predicted_price_rub"], rub_output["expected_price_proxy"])
        self.assertEqual(result["delta_abs_rub"], rub_output["delta_abs"])

    def test_usd_output_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "RUB"):
            predict_proxy_valuation_from_bundle(
                object_features=self.object_features,
                bundle=self.bundle,
                output_currency="USD",
                fx_rate=100.0,
                include_explanation=False,
            )

    def test_direct_prediction_accepts_new_dataset_aliases_for_old_feature_config(self) -> None:
        aliased_features = {
            "listing_id": 8,
            "listing_price": 9_000_000.0,
            "listing_currency": "RUB",
            "district": "Center",
            "rooms": 3,
            "area": 110.0,
            "level": 4,
            "levels": 12,
            "building_type": "brick",
            "seller_type": "owner",
            "latitude": 55.75,
            "longitude": 37.61,
            "photo_count": 12,
        }

        result = predict_proxy_valuation_from_bundle(
            object_features=aliased_features,
            bundle=self.bundle,
            include_explanation=False,
        )

        rub_output = result["price_outputs"]["RUB"]
        self.assertAlmostEqual(rub_output["expected_price_proxy"], 125_000.0)

    def test_listing_payload_mapping_uses_available_informative_fields(self) -> None:
        row = {
            "listing_id": 11,
            "listing_price": 12_500_000.0,
            "listing_currency": "RUB",
            "district": "Airport",
            "rooms": 2,
            "floor": 8,
            "total_floors": 16,
            "area": 78.5,
            "building_type": "monolith",
            "seller_type": "agent",
            "latitude": 42.85,
            "longitude": 74.61,
            "photo_count": 9,
            "source_url": "https://example.test/listing/11",
        }

        payload = _build_scoring_payload(row, self.bundle)

        self.assertEqual(payload["listing_price"], 12_500_000.0)
        self.assertEqual(payload["listing_currency"], "RUB")
        self.assertEqual(payload["total_area_m2"], 78.5)
        self.assertEqual(payload["building_type"], "monolith")
        self.assertEqual(payload["seller_type"], "agent")
        self.assertEqual(payload["latitude"], 42.85)
        self.assertEqual(payload["longitude"], 74.61)
        self.assertEqual(payload["photo_count"], 9)
        self.assertNotIn("price_usd", payload)

    def test_flat_opportunity_dto_exposes_source_url_and_explanation_fallback(self) -> None:
        item = _serialize_opportunity(
            {
                "listing_id": 21,
                "title": "Prime asset",
                "city": "Moscow",
                "district": "Center",
                "area": 95.0,
                "rooms": 3,
                "floor": 7,
                "total_floors": 12,
                "building_type": "brick",
                "condition": "renovated",
                "year_built": 2021,
                "seller_type": "owner",
                "listing_price": 9_000_000.0,
                "listing_currency": "RUB",
                "predicted_price": 100_000.0,
                "score": 0.91,
                "top_factors": ["Area helped", "District helped"],
                "explanation_summary": None,
                "source_url": "https://example.test/listing/21",
                "is_saved": True,
                "rank_position": 1,
            },
            comparison_currency="RUB",
            fx_rate_used=None,
        )

        self.assertEqual(item.listing_currency, "RUB")
        self.assertEqual(item.predicted_price_currency, "RUB")
        self.assertEqual(item.comparison_currency, "RUB")
        self.assertEqual(item.source_url, "https://example.test/listing/21")
        self.assertEqual(item.top_factors, ["Area helped", "District helped"])
        self.assertIn("proxy-оценка", item.explanation_summary.lower())

    def test_legacy_unversioned_artifact_loads_with_log1p_transform(self) -> None:
        payload = {
            "model_name": "linear_stub",
            "model": _StubModel(),
            "feature_config": asdict(self.bundle.feature_config),
            "metrics": {},
            "target_column": "price_usd",
            "log_target": True,
        }

        with TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "legacy.joblib"
            joblib.dump(payload, artifact_path)

            loaded = load_model_bundle(artifact_path)

        self.assertEqual(loaded.model_name, "linear_stub")
        self.assertEqual(loaded.target_column, "price_usd")
        self.assertTrue(loaded.log_target)
        self.assertEqual(loaded.target_transform, "log1p")
        self.assertEqual(loaded.artifact_schema_version, 1)


if __name__ == "__main__":
    unittest.main()
