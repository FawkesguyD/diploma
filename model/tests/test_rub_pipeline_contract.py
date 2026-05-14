from __future__ import annotations

import unittest
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import joblib
import numpy as np
from fastapi import HTTPException

from model.apps.api.api import SinglePredictionRequest, predict, predict_batch, BatchPredictionRequest
from model.apps.geocode.service import _address_quality, _extract_address_fields
from model.apps.normalization.service import normalize_raw_listing
from model.ml.model.feature_schema import russia2021_feature_config
from model.ml.model.inference_validation import validate_inference_record
from model.ml.model.market_bounds import apply_market_bounds, compute_market_bounds
from model.ml.model.persistence import TARGET_TRANSFORM_LOG, load_model_bundle, save_model_bundle
from model.ml.model.readiness import load_ready_model_bundle, save_readiness_manifest


class _LogPriceModel:
    def predict(self, frame):
        return np.log(frame["area"].astype(float) * 100_000.0)


def _make_ready_bundle():
    with TemporaryDirectory() as tmpdir:
        artifact_path = Path(tmpdir) / "stub.joblib"
        save_model_bundle(
            model=_LogPriceModel(),
            model_name="log_price_stub",
            feature_config=russia2021_feature_config(),
            metrics={"rmse_log": 0.0, "mae_price": 0.0},
            output_path=artifact_path,
            target_transform=TARGET_TRANSFORM_LOG,
            base_currency="RUB",
            metadata={"prediction_target": "total_price"},
        )
        return load_model_bundle(artifact_path)


class RubPipelineContractTests(unittest.TestCase):
    def test_validation_rejects_physically_impossible_inputs(self) -> None:
        cases = [
            {"area": 0, "kitchen_area": 0, "level": 1, "levels": 5, "rooms": 1},
            {"area": 50, "kitchen_area": 60, "level": 1, "levels": 5, "rooms": 1},
            {"area": 50, "kitchen_area": 8, "level": 6, "levels": 5, "rooms": 1},
            {"area": 10.7, "kitchen_area": 2, "level": 1, "levels": 5, "rooms": 9},
            {"area": 50, "kitchen_area": 8, "level": 1, "levels": 5, "rooms": 2, "building_type": "bad-code"},
        ]

        for case in cases:
            payload = {
                "object_type": 1,
                "region": 9654,
                "latitude": 55.75,
                "longitude": 37.61,
                "building_type": 2,
                **case,
            }
            result = validate_inference_record(payload, russia2021_feature_config())
            self.assertFalse(result.is_valid, payload)

    def test_normalization_maps_categories_and_keeps_unknown_explicit(self) -> None:
        result = normalize_raw_listing(
            {
                "price": 5_000_000,
                "rooms": 2,
                "area": 50,
                "kitchen_area": 8,
                "level": 3,
                "levels": 9,
                "building_type": 0,
                "object_type": 11,
                "region": 9654,
                "geo_lat": 55.75,
                "geo_lon": 37.61,
            }
        )

        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.normalized_payload["building_type"], "unknown")
        self.assertEqual(result.normalized_payload["object_type"], "new")
        self.assertTrue(result.is_train_eligible)

    def test_market_bounds_clamp_price_per_m2(self) -> None:
        bounds = {
            "global": {"p05": 50_000.0, "p95": 120_000.0},
            "segments": {},
        }

        result = apply_market_bounds(
            price_per_m2=200_000.0,
            object_features={"region": "9654"},
            market_bounds=bounds,
        )

        self.assertTrue(result.clamped)
        self.assertEqual(result.price_per_m2_clamped, 120_000.0)

    def test_compute_market_bounds_uses_price_per_m2_quantiles(self) -> None:
        import pandas as pd

        bounds = compute_market_bounds(
            pd.DataFrame(
                {
                    "price": [1_000_000, 2_000_000, 3_000_000, 4_000_000],
                    "area": [10, 20, 30, 40],
                    "region": ["9654"] * 4,
                }
            ),
            price_column="price",
        )

        self.assertEqual(bounds["global"]["median"], 100_000.0)

    def test_geocode_reverse_extracts_normalized_address_with_quality(self) -> None:
        address = _extract_address_fields(
            {
                "display_name": "Тверская улица, 1, Москва, Россия",
                "address": {
                    "road": "Тверская улица",
                    "house_number": "1",
                    "city": "Москва",
                    "state": "Москва",
                },
            }
        )

        self.assertEqual(address["street"], "Тверская улица")
        self.assertEqual(address["house"], "1")
        self.assertEqual(_address_quality(address), "street_house")

    def test_predict_api_rejects_unrealistic_input(self) -> None:
        with patch("apps.api.api.get_model_bundle", return_value=_make_ready_bundle()):
            with self.assertRaises(HTTPException) as exc:
                predict(
                    SinglePredictionRequest(
                        object_features={
                            "rooms": 9,
                            "area": 10.7,
                            "kitchen_area": 2,
                            "level": 1,
                            "levels": 5,
                            "building_type": 2,
                            "object_type": 1,
                            "region": 9654,
                            "latitude": 55.75,
                            "longitude": 37.61,
                        }
                    )
                )

        self.assertEqual(exc.exception.status_code, 400)

    def test_predict_api_returns_low_confidence_for_missing_context(self) -> None:
        with patch("apps.api.api.get_model_bundle", return_value=_make_ready_bundle()):
            response = predict(
                SinglePredictionRequest(
                    object_features={
                        "rooms": 2,
                        "area": 50,
                        "kitchen_area": 8,
                        "level": 3,
                        "levels": 9,
                    },
                    include_explanation=False,
                )
            )

        self.assertEqual(response.confidence, "low")
        self.assertGreater(response.predicted_price_rub, 0)
        self.assertGreaterEqual(len(response.warnings), 3)

    def test_batch_predict_rejects_invalid_object(self) -> None:
        with patch("apps.api.api.get_model_bundle", return_value=_make_ready_bundle()):
            with self.assertRaises(HTTPException) as exc:
                predict_batch(
                    BatchPredictionRequest(
                        objects=[
                            {
                                "rooms": 2,
                                "area": 50,
                                "kitchen_area": 60,
                                "level": 3,
                                "levels": 9,
                            }
                        ]
                    )
                )

        self.assertEqual(exc.exception.status_code, 400)

    def test_readiness_manifest_loads_only_active_rub_model(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            artifact_path = tmp_path / "ready.joblib"
            bundle = _make_ready_bundle()
            joblib.dump(
                {
                    "model_name": bundle.model_name,
                    "model": bundle.model,
                    "feature_config": asdict(bundle.feature_config),
                    "metrics": bundle.metrics,
                    "target_column": bundle.target_column,
                    "log_target": bundle.log_target,
                    "target_transform": bundle.target_transform,
                    "base_currency": "RUB",
                    "metadata": bundle.metadata,
                },
                artifact_path,
            )
            manifest_path = save_readiness_manifest(
                artifact_path=artifact_path,
                model_name="ready",
                metrics={},
                metadata={"prediction_target": "total_price"},
                output_path=tmp_path / "model_readiness.json",
            )

            loaded = load_ready_model_bundle(
                configured_model_path=artifact_path,
                manifest_path=manifest_path,
                model_path_is_explicit=True,
            )

        self.assertEqual(loaded.base_currency, "RUB")
        self.assertEqual(loaded.metadata["readiness"]["status"], "active")


if __name__ == "__main__":
    unittest.main()
