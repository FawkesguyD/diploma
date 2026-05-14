import { PredictionResponse } from "../model/types";
import { formatMoney, formatPercent } from "../../../shared/lib/format";
import { useLanguage } from "../../../shared/i18n/LanguageContext";
import styles from "./PredictionResult.module.css";

type PredictionResultProps = {
  result: PredictionResponse;
};

type TFunction = ReturnType<typeof useLanguage>["t"];

function signalFromDeltaPct(deltaPct: number | null, t: TFunction): {
  label: string;
  tone: "positive" | "negative" | "neutral";
} {
  if (deltaPct === null) {
    return { label: t("prediction.signal.noListingPrice"), tone: "neutral" };
  }

  if (deltaPct >= 0.05) {
    return { label: t("prediction.signal.undervalued"), tone: "positive" };
  }
  if (deltaPct <= -0.05) {
    return { label: t("prediction.signal.overvalued"), tone: "negative" };
  }
  return { label: t("prediction.signal.close"), tone: "neutral" };
}

export function PredictionResult({ result }: PredictionResultProps) {
  const { t } = useLanguage();
  const signal = signalFromDeltaPct(result.delta_pct, t);
  const explanation =
    result.explanation_summary && result.explanation_summary.trim().length > 0
      ? result.explanation_summary
      : result.valuation_note;

  return (
    <div className={styles.root}>
      <div className={styles.headerRow}>
        <div>
          <p className={styles.kicker}>{t("prediction.kicker")}</p>
          <h3 className={styles.title}>{t("prediction.title")}</h3>
        </div>
        <span
          className={`${styles.signalBadge} ${
            signal.tone === "positive"
              ? styles.signalPositive
              : signal.tone === "negative"
                ? styles.signalNegative
                : styles.signalNeutral
          }`}
        >
          {signal.label}
        </span>
      </div>

      <div className={styles.metricsGrid}>
        <div className={styles.metricCard}>
          <p className={styles.metricLabel}>{t("table.listingPrice")}</p>
          <p className={styles.metricValue}>
            {formatMoney(result.listing_price_rub ?? result.listing_price, "RUB")}
          </p>
          <p className={styles.metricHint}>{t("prediction.hints.listingPrice")}</p>
        </div>

        <div className={`${styles.metricCard} ${styles.metricCardAccent}`}>
          <p className={styles.metricLabel}>{t("table.modelEstimate")}</p>
          <p className={styles.metricValue}>
            {formatMoney(result.predicted_price_rub, "RUB")}
          </p>
          <p className={styles.metricHint}>
            {t("prediction.kicker")} · {t("prediction.confidence")}: {result.confidence}
          </p>
        </div>

        <div className={styles.metricCard}>
          <p className={styles.metricLabel}>{t("table.deltaAbs")}</p>
          <p
            className={`${styles.metricValue} ${
              (result.delta_abs_rub ?? 0) >= 0 ? styles.positive : styles.negative
            }`}
          >
            {formatMoney(result.delta_abs_rub, "RUB")}
          </p>
          <p className={styles.metricHint}>{t("prediction.hints.deltaAbs")}</p>
        </div>

        <div className={styles.metricCard}>
          <p className={styles.metricLabel}>{t("table.deltaPct")}</p>
          <p
            className={`${styles.metricValue} ${
              (result.delta_pct ?? 0) >= 0 ? styles.positive : styles.negative
            }`}
          >
            {formatPercent(result.delta_pct)}
          </p>
          <p className={styles.metricHint}>{t("prediction.hints.signal")}</p>
        </div>

        <div className={styles.metricCard}>
          <p className={styles.metricLabel}>{t("prediction.pricePerM2")}</p>
          <p className={styles.metricValue}>
            {formatMoney(result.price_per_m2_rub, "RUB")}
          </p>
          <p className={styles.metricHint}>{t("prediction.hints.pricePerM2")}</p>
        </div>
      </div>

      {result.top_factors.length > 0 ? (
        <section className={styles.panel}>
          <h4>{t("prediction.topFactors")}</h4>
          <div className={styles.factors}>
            {result.top_factors.map((factor) => (
              <span className={styles.factorChip} key={factor}>
                {factor}
              </span>
            ))}
          </div>
        </section>
      ) : null}

      <section className={styles.panel}>
        <h4>{t("prediction.explanation")}</h4>
        <p className={styles.explanation}>{explanation}</p>
      </section>

      {result.warnings.length > 0 ? (
        <section className={styles.panel}>
          <h4>{t("prediction.modelWarnings")}</h4>
          <ul className={styles.warningList}>
            {result.warnings.map((warning, index) => (
              <li key={`${warning}-${index}`}>{warning}</li>
            ))}
          </ul>
        </section>
      ) : null}

      <p className={styles.disclaimer}>{t("prediction.disclaimer")}</p>
    </div>
  );
}
