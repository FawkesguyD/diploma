import { Fragment, useState } from "react";

import { Opportunity } from "../model/types";
import { ScoreBadge } from "./ScoreBadge";
import styles from "./OpportunitiesTable.module.css";
import {
  formatArea,
  formatCurrencyCode,
  formatNumber,
  formatMoney,
  formatPercent,
} from "../../../shared/lib/format";
import { useLanguage } from "../../../shared/i18n/LanguageContext";

type OpportunitiesTableProps = {
  items: Opportunity[];
  view: "opportunities" | "shortlist";
  onToggleSave: (item: Opportunity) => void;
  pendingListingId: number | null;
};

const GENERIC_EXPLANATION_FALLBACK = "model estimate is a proxy valuation based on listing data";
type TFunction = ReturnType<typeof useLanguage>["t"];

function buildDerivedExplanation(item: Opportunity, t: TFunction) {
  const deltaAbs = formatMoney(Math.abs(item.delta_abs), item.comparison_currency);
  const deltaPct = formatPercent(Math.abs(item.delta_pct));

  if (item.delta_pct >= 0.05) {
    return t("table.explanation.positive", { deltaAbs, deltaPct });
  }

  if (item.delta_pct <= -0.05) {
    return t("table.explanation.negative", { deltaAbs, deltaPct });
  }

  return t("table.explanation.close");
}

function getExplanationSummary(item: Opportunity, t: TFunction) {
  const hasSpecificSummary =
    item.explanation_summary.trim().length > 0 &&
    !item.explanation_summary.toLowerCase().includes(GENERIC_EXPLANATION_FALLBACK);

  if (hasSpecificSummary || item.top_factors.length > 0) {
    return item.explanation_summary;
  }

  return buildDerivedExplanation(item, t);
}

function formatLocalizedFloor(item: Opportunity, t: TFunction) {
  return t("table.floorValue", {
    floor: item.floor ?? "—",
    totalFloors: item.total_floors ?? "—",
  });
}

export function OpportunitiesTable({
  items,
  view,
  onToggleSave,
  pendingListingId,
}: OpportunitiesTableProps) {
  const [expandedListingIds, setExpandedListingIds] = useState<number[]>([]);
  const { t } = useLanguage();

  function toggleExpanded(listingId: number) {
    setExpandedListingIds((current) =>
      current.includes(listingId)
        ? current.filter((item) => item !== listingId)
        : [...current, listingId],
    );
  }

  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>{t("table.listing")}</th>
            <th>{t("table.assetFacts")}</th>
            <th>{t("table.listingPrice")}</th>
            <th>{t("table.modelEstimate")}</th>
            <th>{t("table.delta")}</th>
            <th>{t("table.deltaPct")}</th>
            <th>{t("table.score")}</th>
            <th>{t("table.actions")}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const isLeadingRow = index < 3;
            const isPending = pendingListingId === item.listing_id;
            const isExpanded = expandedListingIds.includes(item.listing_id);
            const derivedExplanation = buildDerivedExplanation(item, t);
            const explanationSummary = getExplanationSummary(item, t);
            const usesDerivedExplanation = explanationSummary === derivedExplanation;

            return (
              <Fragment key={`${view}-${item.listing_id}`}>
                <tr
                  className={isLeadingRow ? styles.leadingRow : undefined}
                >
                  <td>
                    <div className={styles.listingHeader}>
                      <div className={styles.primaryText}>{item.title}</div>
                      {item.is_saved ? (
                        <span className={styles.savedBadge}>{t("table.saved")}</span>
                      ) : null}
                    </div>
                    <div className={styles.secondaryText}>
                      ID {item.listing_id} · {item.city || t("table.unknownCity")} ·{" "}
                      {item.district || t("table.districtNotSet")}
                    </div>
                    {view === "shortlist" && item.rank_position !== null ? (
                      <div className={styles.secondaryText}>
                        {t("table.savedOrder", { rank: item.rank_position })}
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <div className={styles.primaryText}>{formatArea(item.area)}</div>
                    <div className={styles.secondaryText}>
                      {formatNumber(item.rooms, 0, t("table.roomsSuffix"))} ·{" "}
                      {formatLocalizedFloor(item, t)}
                    </div>
                    <div className={styles.secondaryText}>
                      {item.building_type || t("table.buildingTypeNA")} ·{" "}
                      {item.condition || t("table.conditionNA")}
                    </div>
                  </td>
                  <td className={styles.numberCell}>
                    <div className={styles.primaryText}>
                      {formatMoney(item.listing_price, item.listing_currency)}
                    </div>
                    <div className={styles.secondaryText}>
                      {t("table.rawListingPrice")} · {formatCurrencyCode(item.listing_currency)}
                    </div>
                  </td>
                  <td className={styles.numberCell}>
                    <div className={styles.primaryText}>
                      {formatMoney(item.predicted_price, item.predicted_price_currency)}
                    </div>
                    <div className={styles.secondaryText}>
                      {t("table.modelEstimate")} · {formatCurrencyCode(item.predicted_price_currency)}
                    </div>
                  </td>
                  <td className={styles.deltaCell}>
                    {formatMoney(item.delta_abs, item.comparison_currency)}
                  </td>
                  <td className={styles.percentCell}>{formatPercent(item.delta_pct)}</td>
                  <td>
                    <ScoreBadge score={item.score} deltaPct={item.delta_pct} />
                  </td>
                  <td className={styles.actionCell}>
                    <div className={styles.actionStack}>
                      <button
                        aria-expanded={isExpanded}
                        className={styles.detailsButton}
                        onClick={() => toggleExpanded(item.listing_id)}
                        type="button"
                      >
                        {isExpanded ? t("table.details.hide") : t("table.details")}
                      </button>
                      <button
                        className={item.is_saved ? styles.removeButton : styles.saveButton}
                        disabled={isPending}
                        onClick={() => onToggleSave(item)}
                        type="button"
                      >
                        {isPending
                          ? t("table.updating")
                          : item.is_saved
                            ? t("table.remove")
                            : t("table.save")}
                      </button>
                    </div>
                  </td>
                </tr>
                {isExpanded ? (
                  <tr className={styles.detailsRow}>
                    <td className={styles.detailsCell} colSpan={8}>
                      <div className={styles.detailsGrid}>
                        <section className={styles.detailsPanel}>
                          <h3>{t("table.details.property")}</h3>
                          <dl className={styles.detailList}>
                            <div>
                              <dt>{t("common.location")}</dt>
                              <dd>
                                {[item.city, item.district].filter(Boolean).join(", ") ||
                                  t("common.notAvailable")}
                              </dd>
                            </div>
                            <div>
                              <dt>{t("common.area")}</dt>
                              <dd>{formatArea(item.area)}</dd>
                            </div>
                            <div>
                              <dt>{t("common.rooms")}</dt>
                              <dd>{formatNumber(item.rooms, 0)}</dd>
                            </div>
                            <div>
                              <dt>{t("common.floor")}</dt>
                              <dd>{formatLocalizedFloor(item, t)}</dd>
                            </div>
                            <div>
                              <dt>{t("common.building")}</dt>
                              <dd>{item.building_type || t("common.notAvailable")}</dd>
                            </div>
                            <div>
                              <dt>{t("common.condition")}</dt>
                              <dd>{item.condition || t("common.notAvailable")}</dd>
                            </div>
                            <div>
                              <dt>{t("common.yearBuilt")}</dt>
                              <dd>{item.year_built ?? t("common.notAvailable")}</dd>
                            </div>
                            <div>
                              <dt>{t("common.seller")}</dt>
                              <dd>{item.seller_type || t("common.notAvailable")}</dd>
                            </div>
                          </dl>
                          {item.source_url ? (
                            <a
                              className={styles.sourceLink}
                              href={item.source_url}
                              rel="noreferrer"
                              target="_blank"
                            >
                              {t("table.details.source")}
                            </a>
                          ) : null}
                        </section>

                        <section className={styles.detailsPanel}>
                          <h3>{t("table.details.valuation")}</h3>
                          <dl className={styles.detailList}>
                            <div>
                              <dt>{t("table.listingPrice")}</dt>
                              <dd>{formatMoney(item.listing_price, item.listing_currency)}</dd>
                            </div>
                            <div>
                              <dt>{t("table.modelEstimate")}</dt>
                              <dd>{formatMoney(item.predicted_price, item.predicted_price_currency)}</dd>
                            </div>
                            <div>
                              <dt>{t("table.deltaAbs")}</dt>
                              <dd>{formatMoney(item.delta_abs, item.comparison_currency)}</dd>
                            </div>
                            <div>
                              <dt>{t("table.deltaPct")}</dt>
                              <dd>{formatPercent(item.delta_pct)}</dd>
                            </div>
                            <div>
                              <dt>{t("table.score")}</dt>
                              <dd>{item.score.toFixed(2)}</dd>
                            </div>
                            <div>
                              <dt>{t("common.currency")}</dt>
                              <dd>{item.comparison_currency}</dd>
                            </div>
                            {item.listing_price_in_comparison_currency !== null ? (
                              <div>
                                <dt>{t("table.listingPriceInRub")}</dt>
                                <dd>
                                  {formatMoney(
                                    item.listing_price_in_comparison_currency,
                                    item.comparison_currency,
                                  )}
                                </dd>
                              </div>
                            ) : null}
                          </dl>
                        </section>

                        <section className={styles.detailsPanel}>
                          <h3>{t("table.details.modelExplanation")}</h3>
                          <p className={styles.explanationText}>{explanationSummary}</p>
                          {item.top_factors.length > 0 ? (
                            <div className={styles.factors}>
                              {item.top_factors.map((factor) => (
                                <span className={styles.factorChip} key={factor}>
                                  {factor}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <p className={styles.secondaryText}>
                              {usesDerivedExplanation
                                ? t("table.details.noDerivedFactors")
                                : t("table.details.noFactors")}
                            </p>
                          )}
                        </section>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
