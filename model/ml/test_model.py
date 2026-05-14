#!/usr/bin/env python3
"""
Скрипт для тестирования модели с контрольным объектом.
"""

import json
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from model.ml.model.readiness import load_ready_model_bundle
from model.ml.model.prediction import predict_proxy_valuation_from_bundle

def main():
    # Загрузка модели
    from model.ml.model.utils import ARTIFACTS_DIR
    model_path = ARTIFACTS_DIR / "best_model_russia2021.joblib"
    bundle = load_ready_model_bundle(configured_model_path=model_path)

    # Загрузка контрольного объекта
    test_file = Path(__file__).parent / "test_object.json"
    with open(test_file, "r", encoding="utf-8") as f:
        object_features = json.load(f)

    print("Контрольный объект:")
    print(json.dumps(object_features, indent=2, ensure_ascii=False))

    # Предсказание
    result = predict_proxy_valuation_from_bundle(
        object_features=object_features,
        bundle=bundle,
        output_currency="RUB",
        fx_rate=None,
        default_fx_rate=1.0,
        include_explanation=True
    )

    print("\nРезультат предсказания:")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()