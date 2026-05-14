from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

from model.apps.api.api import BatchPredictionRequest, SinglePredictionRequest, predict, predict_batch
from model.ml.model.feature_schema import RUSSIA2021_MODEL_FEATURE_COLUMNS, russia2021_feature_config
from model.ml.model.inference import load_model_bundle, predict_proxy_valuation_from_bundle
from model.ml.model.inference_preprocessing import prepare_inference_frame
from model.ml.model.normalization import fill_categorical_features_for_catboost
from model.ml.model.persistence import TARGET_TRANSFORM_LOG, save_model_bundle
from model.ml.model.runtime_adapters import build_listing_model_payload
from model.ml.model.russia2021_training import (
    CatBoostRegressor,
    Russia2021TrainingConfig,
    preprocess_russia2021_chunk,
    run_russia2021_pipeline,
    validate_russia2021_schema,
)


class _LogAreaModel:
    def predict(self, frame):
        price = (frame["area"].astype(float) * 1000.0) + (frame["rooms"].astype(float) * 100.0)
        return np.log(price)


def _sample_rows() -> list[dict[str, float]]:
    return [
        {"rooms": 1, "area": 30.0, "kitchen_area": 6.0, "level": 1, "levels": 5, "price": 3_000_000.0},
        {"rooms": 2, "area": 45.0, "kitchen_area": 8.0, "level": 2, "levels": 9, "price": 4_800_000.0},
        {"rooms": 3, "area": 65.0, "kitchen_area": 10.0, "level": 3, "levels": 12, "price": 7_300_000.0},
        {"rooms": 1, "area": 36.0, "kitchen_area": 7.0, "level": 4, "levels": 10, "price": 3_600_000.0},
        {"rooms": 4, "area": 90.0, "kitchen_area": 14.0, "level": 5, "levels": 16, "price": 10_500_000.0},
        {"rooms": 2, "area": 52.0, "kitchen_area": 9.0, "level": 6, "levels": 17, "price": 6_100_000.0},
        {"rooms": 3, "area": 74.0, "kitchen_area": 12.0, "level": 8, "levels": 20, "price": 8_800_000.0},
        {"rooms": 1, "area": 28.0, "kitchen_area": 5.0, "level": 2, "levels": 5, "price": 2_700_000.0},
        {"rooms": 2, "area": 49.0, "kitchen_area": 8.0, "level": 7, "levels": 14, "price": 5_500_000.0},
        {"rooms": 3, "area": 68.0, "kitchen_area": 11.0, "level": 9, "levels": 19, "price": 8_200_000.0},
    ]


class Russia2021TrainingPipelineTests(unittest.TestCase):
    def test_db_listing_payload_maps_old_db_columns_to_new_canonical_schema(self) -> None:
        bundle = load_model_bundle_from_stub()
        row = {
            "listing_id": 101,
            "listing_price": 6_500_000.0,
            "listing_currency": "RUB",
            "rooms": 2,
            "area": 48.5,
            "kitchen_area_m2": 9.2,
            "floor": 4,
            "total_floors": 12,
            "building_type": 2,
            "object_type": 2,
            "region": 77,
            "latitude": 55.75,
            "longitude": 37.61,
        }

        payload = build_listing_model_payload(row, bundle, listing_currency="RUB")

        self.assertEqual(payload["area"], 48.5)
        self.assertEqual(payload["kitchen_area"], 9.2)
        self.assertEqual(payload["level"], 4)
        self.assertEqual(payload["levels"], 12)

    def test_schema_validation_rejects_missing_required_columns(self) -> None:
        with self.assertRaisesRegex(ValueError, "Отсутствуют колонки"):
            validate_russia2021_schema(["rooms", "area", "price"])

    def test_preprocessing_filters_invalid_rows_and_uses_exact_log_price(self) -> None:
        raw = pd.DataFrame(
            [
                {"rooms": 2, "area": 50, "kitchen_area": 8, "level": 3, "levels": 9, "price": 5_000_000},
                {"rooms": 2, "area": 50, "kitchen_area": 8, "level": 3, "levels": 9, "price": 0},
                {"rooms": 2, "area": 50, "kitchen_area": 80, "level": 3, "levels": 9, "price": 5_000_000},
                {"rooms": 2, "area": 50, "kitchen_area": 8, "level": 10, "levels": 9, "price": 5_000_000},
            ]
        )

        prepared = preprocess_russia2021_chunk(raw)

        self.assertEqual(len(prepared), 1)
        self.assertAlmostEqual(prepared.iloc[0]["target_log_price"], np.log(5_000_000))
        self.assertAlmostEqual(prepared.iloc[0]["target_log_price_per_m2"], np.log(100_000))

    def test_train_and_inference_preprocessing_share_alias_schema(self) -> None:
        feature_config = russia2021_feature_config()
        canonical = prepare_inference_frame(
            {"rooms": 2, "area": 50, "kitchen_area": 8, "level": 3, "levels": 9},
            feature_config,
        )
        aliases = prepare_inference_frame(
            {
                "rooms": 2,
                "total_area_m2": 50,
                "kitchen_area_m2": 8,
                "floor": 3,
                "total_floors": 9,
            },
            feature_config,
        )

        pd.testing.assert_frame_equal(canonical, aliases)
        self.assertEqual(list(canonical.columns), RUSSIA2021_MODEL_FEATURE_COLUMNS)

    def test_russia2021_feature_config_contains_extended_features(self) -> None:
        feature_config = russia2021_feature_config()

        for feature_name in [
            "rooms",
            "area",
            "kitchen_area",
            "level",
            "levels",
            "area_per_room",
            "floor_ratio",
            "kitchen_ratio",
            "rooms_density",
            "is_top_floor",
            "is_first_floor",
            "building_type",
            "object_type",
            "region",
        ]:
            self.assertIn(feature_name, feature_config.feature_columns)

        self.assertEqual(feature_config.categorical_features, ["building_type", "object_type", "region"])

    def test_dataset_coordinate_aliases_populate_canonical_coordinates(self) -> None:
        frame = prepare_inference_frame(
            {
                "rooms": 2,
                "area": 50,
                "kitchen_area": 8,
                "level": 3,
                "levels": 9,
                "geo_lat": 59.8058084,
                "geo_lon": 30.376141,
            },
            russia2021_feature_config(),
        )

        self.assertAlmostEqual(frame.iloc[0]["latitude"], 59.8058084)
        self.assertAlmostEqual(frame.iloc[0]["longitude"], 30.376141)
        self.assertEqual(frame.iloc[0]["has_coordinates"], 1)

    def test_derived_features_are_created_in_shared_preprocessing(self) -> None:
        frame = prepare_inference_frame(
            {"rooms": 2, "area": 50, "kitchen_area": 10, "level": 3, "levels": 9},
            russia2021_feature_config(),
        )

        self.assertAlmostEqual(frame.iloc[0]["area_per_room"], 25.0)
        self.assertAlmostEqual(frame.iloc[0]["floor_ratio"], 3 / 9)
        self.assertAlmostEqual(frame.iloc[0]["kitchen_ratio"], 0.2)

    def test_studio_marker_converts_negative_one_rooms(self) -> None:
        frame = prepare_inference_frame(
            {"rooms": -1, "area": 32, "kitchen_area": 6, "level": 2, "levels": 10},
            russia2021_feature_config(),
        )

        self.assertEqual(frame.iloc[0]["rooms"], 1)
        self.assertEqual(frame.iloc[0]["is_studio"], 1)
        self.assertAlmostEqual(frame.iloc[0]["area_per_room"], 32.0)

    def test_russia2021_training_chunk_and_inference_frame_use_same_features(self) -> None:
        raw = pd.DataFrame(
            [
                {
                    "rooms": 2,
                    "area": 50,
                    "kitchen_area": 8,
                    "level": 3,
                    "levels": 9,
                    "building_type": 1,
                    "object_type": 2,
                    "region": 77,
                    "latitude": 55.75,
                    "longitude": 37.61,
                    "price": 5_000_000,
                }
            ]
        )

        training_frame = preprocess_russia2021_chunk(raw)
        inference_frame = prepare_inference_frame(raw.drop(columns=["price"]), russia2021_feature_config())
        inference_frame = fill_categorical_features_for_catboost(
            inference_frame,
            russia2021_feature_config().categorical_features,
        )

        self.assertEqual(list(training_frame.columns[2:]), list(inference_frame.columns))
        pd.testing.assert_series_equal(
            training_frame.iloc[0, 2:],
            inference_frame.iloc[0],
            check_names=False,
        )

    def test_log_artifact_returns_original_scale_price_from_saved_bundle(self) -> None:
        with TemporaryDirectory() as tmpdir:
            artifact_path = Path(tmpdir) / "model.joblib"
            save_model_bundle(
                model=_LogAreaModel(),
                model_name="log_area_stub",
                feature_config=russia2021_feature_config(),
                metrics={"rmse_log": 0.0, "mae_price": 0.0, "rmse_price": 0.0},
                output_path=artifact_path,
                target_transform=TARGET_TRANSFORM_LOG,
                base_currency="RUB",
                metadata={"target_formula": "F(x)=log(price)"},
            )
            bundle = load_model_bundle(artifact_path)

        result = predict_proxy_valuation_from_bundle(
            {
                "rooms": 2,
                "total_area_m2": 50,
                "kitchen_area_m2": 8,
                "floor": 3,
                "total_floors": 9,
                "listing_price": 45_000,
                "listing_currency": "RUB",
            },
            bundle,
            output_currency="RUB",
            include_explanation=False,
        )

        self.assertEqual(bundle.target_transform, "log")
        self.assertEqual(bundle.base_currency, "RUB")
        self.assertAlmostEqual(result["price_outputs"]["RUB"]["expected_price_proxy"], 50_200.0)
        self.assertEqual(set(result["price_outputs"]), {"RUB"})

    @unittest.skipIf(CatBoostRegressor is None, "catboost is not installed")
    def test_russia2021_pipeline_trains_catboost_and_saves_loadable_artifact(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            data_path = tmp_path / "russia.csv"
            pd.DataFrame(_sample_rows()).to_csv(data_path, index=False)
            artifact_dir = tmp_path / "artifacts"
            reports_dir = tmp_path / "reports"

            artifact_path = run_russia2021_pipeline(
                Russia2021TrainingConfig(
                    data_path=data_path,
                    artifacts_dir=artifact_dir,
                    reports_dir=reports_dir,
                    output_model_name="tiny.joblib",
                    chunk_size=3,
                    validation_size=0.3,
                    random_state=7,
                    iterations=10,
                    early_stopping_rounds=3,
                )
            )
            bundle = load_model_bundle(artifact_path)
            self.assertTrue((artifact_dir / "model_readiness.json").exists())
            self.assertTrue((reports_dir / "russia2021_market_bounds.json").exists())
            self.assertTrue((reports_dir / "russia2021_segment_metrics_report.json").exists())

        self.assertIn(bundle.model_name, {"catboost_regressor_russia2021_total_price", "catboost_regressor_russia2021_price_per_m2"})
        self.assertEqual(bundle.target_column, "price")
        self.assertEqual(bundle.target_transform, "log")
        self.assertEqual(bundle.base_currency, "RUB")
        self.assertIn("rmse_log", bundle.metrics)
        self.assertIn(bundle.metadata["prediction_target"], {"total_price", "price_per_m2"})

    def test_predict_endpoints_keep_contract_with_log_artifact(self) -> None:
        bundle = load_model_bundle_from_stub()
        with patch("apps.api.api.get_model_bundle", return_value=bundle):
            single = predict(
                SinglePredictionRequest(
                    object_features={
                        "rooms": 2,
                        "total_area_m2": 50,
                        "kitchen_area_m2": 8,
                        "floor": 3,
                        "total_floors": 9,
                        "listing_price": 45_000,
                        "listing_currency": "RUB",
                    },
                    output_currency="RUB",
                    include_explanation=False,
                )
            )
            batch = predict_batch(
                BatchPredictionRequest(
                    objects=[
                        {
                            "listing_id": "1",
                            "rooms": 2,
                            "area": 50,
                            "kitchen_area": 8,
                            "level": 3,
                            "levels": 9,
                            "listing_price": 45_000,
                            "listing_currency": "RUB",
                        }
                    ],
                    output_currency="RUB",
                    include_explanations=False,
                )
            )

        self.assertIn("RUB", single.price_outputs)
        self.assertGreater(single.predicted_price_rub, 0)
        self.assertEqual(len(batch.results), 1)
        self.assertIn("RUB", batch.results[0].price_outputs)
        self.assertGreater(batch.results[0].predicted_price_rub, 0)


def load_model_bundle_from_stub():
    return load_model_bundle_from_payload(
        _LogAreaModel(),
        russia2021_feature_config(),
        {"rmse_log": 0.0, "mae_price": 0.0, "rmse_price": 0.0},
    )


def load_model_bundle_from_payload(model, feature_config, metrics):
    with TemporaryDirectory() as tmpdir:
        artifact_path = Path(tmpdir) / "stub.joblib"
        save_model_bundle(
            model=model,
            model_name="log_area_stub",
            feature_config=feature_config,
            metrics=metrics,
            output_path=artifact_path,
            target_transform=TARGET_TRANSFORM_LOG,
            base_currency="RUB",
            metadata={"target_formula": "F(x)=log(price)"},
        )
        return load_model_bundle(artifact_path)


if __name__ == "__main__":
    unittest.main()
