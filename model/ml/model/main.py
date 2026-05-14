from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from model.ml.model.data_loading import (
    DEFAULT_LOCAL_DATASET_PATH,
    HF_DATASET_NAME,
    dataset_fingerprint,
    load_dataset_frame,
    summarize_dataset,
)
from model.ml.model.evaluate import (
    build_validation_report,
    save_feature_importance_plot,
    save_target_distribution_plot,
)
from model.ml.model.db_training_data import export_normalized_training_csv
from model.ml.model.inference import predict_expected_price, rank_by_undervaluation, score_objects
from model.ml.model.russia2021_training import (
    DEFAULT_RUSSIA2021_CHUNK_SIZE,
    DEFAULT_RUSSIA2021_LOCAL_DATASET_PATH,
    DEFAULT_RUSSIA2021_OUTPUT_NAME,
    DEFAULT_RUSSIA2021_VALIDATION_SIZE,
    build_russia2021_config_from_args,
    run_russia2021_pipeline,
)
from model.ml.model.training_preprocessing import prepare_training_frame
from model.ml.model.train import (
    CatBoostRegressor,
    choose_best_model,
    cross_validate_baseline,
    cross_validate_catboost,
    fit_best_model_on_full_data,
    save_model_bundle,
    train_baseline_model,
    train_catboost_model,
    train_validation_split,
)
from model.ml.model.utils import ARTIFACTS_DIR, RANDOM_STATE, REPORTS_DIR, ensure_project_dirs, save_json


def run_pipeline(data_path: Path, artifacts_dir: Path, reports_dir: Path, force_download: bool) -> None:
    ensure_project_dirs()
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    raw_df = load_dataset_frame(data_path, force_download=force_download)
    dataset_summary = summarize_dataset(raw_df)
    dataset_summary["dataset_name"] = HF_DATASET_NAME
    dataset_summary["dataset_path"] = str(data_path)
    dataset_summary["dataset_sha256"] = dataset_fingerprint(data_path)

    save_json(dataset_summary, reports_dir / "dataset_summary.json")

    X, y, feature_config, qc_summary = prepare_training_frame(raw_df)
    save_json(qc_summary, reports_dir / "qc_summary.json")
    save_target_distribution_plot(y, reports_dir / "target_distribution.png")

    X_train, X_valid, y_train, y_valid = train_validation_split(X, y)

    baseline_result = train_baseline_model(X_train, y_train, X_valid, y_valid, feature_config)
    baseline_result["cross_validation"] = cross_validate_baseline(X, y, feature_config)

    model_results = [baseline_result]

    if CatBoostRegressor is not None:
        catboost_result = train_catboost_model(X_train, y_train, X_valid, y_valid, feature_config)
        catboost_result["cross_validation"] = cross_validate_catboost(X, y, feature_config)
        model_results.append(catboost_result)

        catboost_importance = catboost_result["feature_importance"]
        catboost_importance.to_csv(
            reports_dir / "catboost_feature_importance.csv",
            index=False,
        )
        save_feature_importance_plot(
            catboost_importance,
            reports_dir / "catboost_feature_importance.png",
        )

    model_comparison = pd.DataFrame(
        [
            {
                "model_name": result["model_name"],
                **result["metrics"],
            }
            for result in model_results
        ]
    ).sort_values(["rmse", "mae"], ascending=[True, True], ignore_index=True)
    model_comparison.to_csv(reports_dir / "model_comparison.csv", index=False)

    best_result = choose_best_model(model_results)
    best_full_model = fit_best_model_on_full_data(
        best_result["model_name"],
        X,
        y,
        feature_config,
    )

    best_model_path = save_model_bundle(
        model=best_full_model,
        model_name=best_result["model_name"],
        feature_config=feature_config,
        metrics=best_result["metrics"],
        output_path=artifacts_dir / "best_model.joblib",
    )

    for result in model_results:
        save_model_bundle(
            model=result["model"],
            model_name=result["model_name"],
            feature_config=feature_config,
            metrics=result["metrics"],
            output_path=artifacts_dir / f"{result['model_name']}.joblib",
        )
        validation_report = build_validation_report(
            result["model_name"],
            result["metrics"],
            result.get("cross_validation"),
            notes={"selected_as_best_model": result["model_name"] == best_result["model_name"]},
        )
        save_json(validation_report, reports_dir / f"{result['model_name']}_validation_report.json")

    cleaned_with_target = raw_df.loc[X.index].copy()
    scored_df = score_objects(cleaned_with_target, best_model_path, listing_price_column="price_usd")
    ranked_df = rank_by_undervaluation(scored_df)
    ranked_df.to_csv(reports_dir / "ranked_undervalued_listings.csv", index=False)
    ranked_df.head(100).to_csv(reports_dir / "shortlist_top_100.csv", index=False)

    example_payload = raw_df.iloc[0].to_dict()
    example_prediction = predict_expected_price(example_payload, best_model_path)
    save_json({"object_features": example_payload, "prediction": example_prediction}, reports_dir / "inference_example.json")

    print("Dataset columns:")
    for column in raw_df.columns:
        print(f" - {column}")

    print("\nSelected numerical features:")
    for feature in feature_config.numerical_features:
        print(f" - {feature}")

    print("\nSelected categorical features:")
    for feature in feature_config.categorical_features:
        print(f" - {feature}")

    print("\nModel comparison:")
    print(model_comparison.to_string(index=False))

    print(f"\nBest model: {best_result['model_name']}")
    print(f"Saved model bundle: {best_model_path}")
    print(f"Shortlist path: {reports_dir / 'shortlist_top_100.csv'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Обучение MVP proxy-valuation модели недвижимости.")
    parser.add_argument(
        "--pipeline",
        choices=["legacy", "russia2021", "db_russia2021"],
        default="legacy",
        help="Выбор пайплайна обучения: legacy сохраняет старое поведение, russia2021 обучает новую модель, db_russia2021 берёт нормализованные данные из БД.",
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=DEFAULT_LOCAL_DATASET_PATH,
        help="Локальный путь к CSV исходного датасета.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=ARTIFACTS_DIR,
        help="Директория для сохранения артефактов модели.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=REPORTS_DIR,
        help="Директория для сохранения отчётов обучения.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Повторно скачать датасет, даже если локальный файл уже существует.",
    )
    parser.add_argument(
        "--russia-data-path",
        type=Path,
        default=DEFAULT_RUSSIA2021_LOCAL_DATASET_PATH,
        help="Локальный CSV-файл датасета daniilakk/Russia_Real_Estate_2021.",
    )
    parser.add_argument(
        "--db-training-export-path",
        type=Path,
        default=DEFAULT_RUSSIA2021_LOCAL_DATASET_PATH,
        help="CSV-файл, куда db_russia2021 экспортирует normalized_listings перед обучением.",
    )
    parser.add_argument(
        "--db-training-limit",
        type=int,
        default=None,
        help="Ограничение строк для отладочного обучения из normalized_listings.",
    )
    parser.add_argument(
        "--russia-data-url",
        type=str,
        default=None,
        help="URL для скачивания CSV датасета Russia_Real_Estate_2021.",
    )
    parser.add_argument(
        "--russia-source-dataset",
        type=str,
        default="daniilakk/Russia_Real_Estate_2021",
        help="Имя датасета Hugging Face для потокового обучения, если локальный CSV не найден.",
    )
    parser.add_argument(
        "--russia-source-split",
        type=str,
        default="train",
        help="Split датасета Hugging Face для потокового обучения.",
    )
    parser.add_argument(
        "--russia-force-download",
        action="store_true",
        help="Повторно скачать CSV датасета Russia_Real_Estate_2021.",
    )
    parser.add_argument(
        "--russia-output-model-name",
        type=str,
        default=DEFAULT_RUSSIA2021_OUTPUT_NAME,
        help="Имя нового joblib-артефакта в директории artifacts.",
    )
    parser.add_argument(
        "--russia-chunk-size",
        type=int,
        default=DEFAULT_RUSSIA2021_CHUNK_SIZE,
        help="Размер чанка для потоковой предобработки CSV.",
    )
    parser.add_argument(
        "--russia-max-rows",
        type=int,
        default=None,
        help="Ограничение количества валидных строк после предобработки для отладочного запуска.",
    )
    parser.add_argument(
        "--russia-validation-size",
        type=float,
        default=DEFAULT_RUSSIA2021_VALIDATION_SIZE,
        help="Доля валидационной выборки для нового пайплайна.",
    )
    parser.add_argument(
        "--russia-random-state",
        type=int,
        default=RANDOM_STATE,
        help="Seed для воспроизводимого split нового пайплайна.",
    )
    parser.add_argument(
        "--russia-target-currency",
        type=str,
        default="RUB",
        help="Валюта целевой цены нового артефакта.",
    )
    parser.add_argument(
        "--russia-iterations",
        type=int,
        default=1000,
        help="Количество итераций CatBoost для нового пайплайна.",
    )
    parser.add_argument(
        "--russia-learning-rate",
        type=float,
        default=0.05,
        help="Learning rate CatBoost для нового пайплайна.",
    )
    parser.add_argument(
        "--russia-depth",
        type=int,
        default=8,
        help="Глубина деревьев CatBoost для нового пайплайна.",
    )
    parser.add_argument(
        "--russia-l2-leaf-reg",
        type=float,
        default=5.0,
        help="L2-регуляризация CatBoost для нового пайплайна.",
    )
    parser.add_argument(
        "--russia-early-stopping-rounds",
        type=int,
        default=50,
        help="Early stopping rounds для нового пайплайна.",
    )
    return parser.parse_args()


def run_from_args(args: argparse.Namespace) -> None:
    if args.pipeline == "db_russia2021":
        export_result = export_normalized_training_csv(
            args.db_training_export_path,
            limit=args.db_training_limit,
        )
        args.russia_data_path = args.db_training_export_path
        output_path = run_russia2021_pipeline(build_russia2021_config_from_args(args))
        print(f"Exported normalized DB rows: {export_result['rows_exported']}")
        print(f"Saved DB-backed Russia 2021 model bundle: {output_path}")
        return

    if args.pipeline == "russia2021":
        output_path = run_russia2021_pipeline(build_russia2021_config_from_args(args))
        print(f"Saved Russia 2021 model bundle: {output_path}")
        return

    run_pipeline(
        data_path=args.data_path,
        artifacts_dir=args.artifacts_dir,
        reports_dir=args.reports_dir,
        force_download=args.force_download,
    )


if __name__ == "__main__":
    args = parse_args()
    run_from_args(args)
