from __future__ import annotations

import unittest

import numpy as np
from pydantic import ValidationError

from model.apps.analytics_service.schemas import RealEstateScoreRequest
from model.apps.analytics_service.service import calculate_formula, calculate_price_per_meter, calculate_regression
from model.ml.model.persistence import LoadedModelBundle
from model.ml.model.preprocessing import FeatureConfig


class _StubModel:
    def predict(self, frame):
        area = frame["area"].fillna(0).astype(float)
        return np.asarray(area * 100_000.0, dtype=float)


def _make_bundle() -> LoadedModelBundle:
    feature_config = FeatureConfig(
        target_column="price",
        numerical_features=["rooms", "area", "level", "levels"],
        categorical_features=[],
        derived_numeric_features=[],
        excluded_columns=[],
        log_target=False,
    )
    return LoadedModelBundle(
        model_name="analytics_stub",
        model=_StubModel(),
        feature_config=feature_config,
        metrics={},
        target_column="price",
        log_target=False,
        base_currency="RUB",
        metadata={"prediction_target": "total_price"},
    )


class AnalyticsServiceContractTests(unittest.TestCase):
    def test_price_per_meter_accepts_aliases_and_returns_analytical_score(self) -> None:
        request = RealEstateScoreRequest.model_validate(
            {
                "total_area_m2": 50,
                "floor": 4,
                "total_floors": 12,
                "listing_price": 10_000_000,
                "listing_currency": "RUB",
            }
        )

        result = calculate_price_per_meter(request)

        self.assertEqual(result.method, "price_per_meter")
        self.assertEqual(result.area, 50)
        self.assertEqual(result.price_per_m2, 200_000)
        self.assertEqual(result.analytical_score, 200_000)

    def test_formula_returns_proxy_delta_when_listing_price_exists(self) -> None:
        request = RealEstateScoreRequest.model_validate(
            {
                "rooms": 2,
                "area": 50,
                "kitchen_area": 8,
                "level": 4,
                "levels": 12,
                "listing_price": 9_000_000,
            }
        )

        result = calculate_formula(request)

        self.assertEqual(result.method, "formula")
        self.assertIsNotNone(result.delta_abs)
        self.assertIsNotNone(result.delta_pct)
        self.assertIn("area", result.coefficients_used)

    def test_derived_feature_override_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "derived features"):
            RealEstateScoreRequest.model_validate(
                {
                    "area": 50,
                    "area_per_room": 25,
                }
            )

    def test_regression_uses_existing_bundle_contract_and_allows_missing_listing_price(self) -> None:
        payload = RealEstateScoreRequest(
            rooms=2,
            area=54,
            level=5,
            levels=12,
            listing_currency="RUB",
        )

        result = calculate_regression(payload, _make_bundle())

        self.assertEqual(result.method, "regression")
        self.assertEqual(result.expected_price_proxy, 5_400_000)
        self.assertIsNone(result.listing_price)
        self.assertIsNone(result.delta_abs)
        self.assertIsNone(result.delta_pct)

    def test_non_rub_currency_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "listing_currency=RUB"):
            RealEstateScoreRequest.model_validate(
                {
                    "area": 50,
                    "listing_currency": "USD",
                }
            )


if __name__ == "__main__":
    unittest.main()
