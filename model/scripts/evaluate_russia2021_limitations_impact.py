from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model.scripts.russia2021_analysis_common import DEFAULT_REPORTS_DIR, save_json


DEFAULT_ABLATION_PATH = DEFAULT_REPORTS_DIR / "russia2021_feature_ablation_results.csv"
DEFAULT_OUTPUT_PATH = DEFAULT_REPORTS_DIR / "russia2021_limitations_impact_matrix.csv"
DEFAULT_JSON_PATH = DEFAULT_REPORTS_DIR / "russia2021_limitations_impact_matrix.json"


def format_impact(row: pd.Series | None) -> str:
    if row is None:
        return "не рассчитано количественно"
    removed_features = row.get("removed_features") if "removed_features" in row else None
    if removed_features is not None and (pd.isna(removed_features) or not str(removed_features).strip()):
        return "не рассчитано количественно"
    parts: list[str] = []
    if pd.notna(row.get("ΔMAPE, п.п.")):
        parts.append(f"{float(row['ΔMAPE, п.п.']):+.2f} п.п. к MAPE")
    if pd.notna(row.get("ΔR²")):
        parts.append(f"{float(row['ΔR²']):+.4f} к R²")
    return "; ".join(parts) if parts else "не рассчитано количественно"


def ablation_row(ablation: pd.DataFrame, label: str) -> pd.Series | None:
    if ablation.empty:
        return None
    matched = ablation[ablation["Удаленный признак/группа"] == label]
    if matched.empty:
        return None
    return matched.iloc[0]


def build_matrix(ablation_path: Path) -> dict[str, Any]:
    ablation = pd.read_csv(ablation_path) if ablation_path.exists() else pd.DataFrame()
    geography = ablation_row(ablation, "Группа: География")
    other_cat = ablation_row(ablation, "Группа: Остальные категориальные признаки")

    rows = [
        {
            "Ограничение": "Данные объявлений вместо данных сделок",
            "Влияние на точность": "не рассчитано количественно",
            "Способ смягчения": "Сравнивать модель с закрывающими сделками при появлении таких данных; в статье явно трактовать результат как proxy-valuation.",
        },
        {
            "Ограничение": "Пропущенные признаки",
            "Влияние на точность": "не рассчитано количественно",
            "Способ смягчения": "Расширить схему входных данных и контролировать долю пропусков по ключевым признакам перед обучением.",
        },
        {
            "Ограничение": "Дрифт данных",
            "Влияние на точность": "не рассчитано количественно",
            "Способ смягчения": "Проводить повторную validation-оценку на новых периодах и переобучать модель при изменении распределений.",
        },
        {
            "Ограничение": "Географическая неоднородность рынка",
            "Влияние на точность": format_impact(geography),
            "Способ смягчения": "Использовать региональные признаки, координаты и отдельный контроль качества по сегментам рынка.",
        },
        {
            "Ограничение": "Выбросы в ценах",
            "Влияние на точность": "не рассчитано количественно",
            "Способ смягчения": "Сохранять фильтрацию экстремальных значений price_per_m2 и дополнительно проверять ошибки на дорогих сегментах.",
        },
        {
            "Ограничение": "Пропуски в данных",
            "Влияние на точность": "не рассчитано количественно",
            "Способ смягчения": "Отслеживать долю удаленных строк и добавлять устойчивые правила заполнения для признаков, где это допустимо.",
        },
        {
            "Ограничение": "Отсутствие признаков о ремонте, юридическом статусе и инфраструктуре",
            "Влияние на точность": format_impact(other_cat),
            "Способ смягчения": "Добавить признаки ремонта, юридического статуса, инфраструктуры и проверить их вклад через повторный ablation-анализ.",
        },
    ]
    return {
        "metadata": {
            "ablation_path": str(ablation_path),
            "impact_source": "feature ablation where a matching feature group exists; otherwise qualitative limitation only",
        },
        "rows": rows,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Limitations impact matrix for Russia 2021 model.")
    parser.add_argument("--ablation-path", type=Path, default=DEFAULT_ABLATION_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_matrix(args.ablation_path)
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(payload["rows"]).to_csv(args.output_path, index=False)
    save_json(payload, args.json_path)
    print(f"Saved CSV: {args.output_path}")
    print(f"Saved JSON: {args.json_path}")


if __name__ == "__main__":
    main()
