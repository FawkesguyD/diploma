import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AppShell } from "../../app/layout/AppShell";
import { useCurrentUser } from "../../features/auth/model/useCurrentUser";
import { getOpportunities } from "../../features/opportunities/api/opportunitiesApi";
import {
  Opportunity,
  OpportunityBackendSortBy,
  OpportunitySortBy,
} from "../../features/opportunities/model/types";
import { OpportunitiesTable } from "../../features/opportunities/ui/OpportunitiesTable";
import {
  deleteShortlistItem,
  getShortlist,
  saveShortlistItem,
} from "../../features/shortlist/api/shortlistApi";
import { AddObjectModal } from "../../features/prediction/ui/AddObjectModal";
import { isApiError } from "../../shared/api/client";
import { useLanguage } from "../../shared/i18n/LanguageContext";
import { EmptyState } from "../../shared/ui/EmptyState";
import { StatusCard } from "../../shared/ui/StatusCard";
import styles from "./ShortlistPage.module.css";

type ViewMode = "opportunities" | "shortlist";

type FilterState = {
  city: string;
  district: string;
  minPrice: string;
  maxPrice: string;
  minArea: string;
  maxArea: string;
  rooms: string;
};

const EMPTY_FILTERS: FilterState = {
  city: "",
  district: "",
  minPrice: "",
  maxPrice: "",
  minArea: "",
  maxArea: "",
  rooms: "",
};

function parseOptionalNumber(value: string) {
  if (!value.trim()) {
    return null;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function compareNullableNumbers(
  left: number | null,
  right: number | null,
  direction: "asc" | "desc",
) {
  if (left === null && right === null) {
    return 0;
  }
  if (left === null) {
    return 1;
  }
  if (right === null) {
    return -1;
  }

  return direction === "asc" ? left - right : right - left;
}

function getComparableListingPrice(item: Opportunity) {
  return item.listing_price_in_comparison_currency ?? item.listing_price;
}

export function ShortlistPage() {
  const queryClient = useQueryClient();
  const currentUserQuery = useCurrentUser();
  const { t } = useLanguage();
  const [viewMode, setViewMode] = useState<ViewMode>("opportunities");
  const [sortBy, setSortBy] = useState<OpportunitySortBy>("score");
  const [searchTerm, setSearchTerm] = useState("");
  const [filters, setFilters] = useState<FilterState>(EMPTY_FILTERS);
  const [pendingListingId, setPendingListingId] = useState<number | null>(null);
  const [isAddObjectOpen, setAddObjectOpen] = useState(false);
  const backendSortBy: OpportunityBackendSortBy =
    sortBy === "undervaluation_percent" ? "undervaluation_percent" : "score";

  const opportunitiesQuery = useQuery({
    queryKey: ["opportunities", backendSortBy],
    queryFn: () => getOpportunities(backendSortBy),
    staleTime: 30 * 1000,
  });

  const shortlistQuery = useQuery({
    queryKey: ["shortlist"],
    queryFn: getShortlist,
    enabled: viewMode === "shortlist",
    staleTime: 30 * 1000,
  });

  const toggleShortlistMutation = useMutation({
    mutationFn: async (item: Opportunity) => {
      setPendingListingId(item.listing_id);
      if (item.is_saved) {
        return deleteShortlistItem(item.listing_id);
      }
      return saveShortlistItem(item.listing_id, item.rank_position);
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["opportunities"] }),
        queryClient.invalidateQueries({ queryKey: ["shortlist"] }),
      ]);
    },
    onSettled: () => {
      setPendingListingId(null);
    },
  });

  if (currentUserQuery.isLoading) {
    return (
      <StatusCard
        title={t("status.loadingWorkspaceTitle")}
        description={t("status.loadingWorkspaceDescription")}
      />
    );
  }

  if (currentUserQuery.isError || !currentUserQuery.data) {
    return (
      <StatusCard
        tone="error"
        title={t("status.workspaceUnavailableTitle")}
        description={t("status.workspaceUnavailableDescription")}
        actionLabel={t("common.retry")}
        onAction={() => void currentUserQuery.refetch()}
      />
    );
  }

  const activeQuery = viewMode === "opportunities" ? opportunitiesQuery : shortlistQuery;
  const activeItems = activeQuery.data?.items ?? [];
  const activeError = activeQuery.error;
  const normalizedSearch = searchTerm.trim().toLowerCase();
  const minPrice = parseOptionalNumber(filters.minPrice);
  const maxPrice = parseOptionalNumber(filters.maxPrice);
  const minArea = parseOptionalNumber(filters.minArea);
  const maxArea = parseOptionalNumber(filters.maxArea);
  const selectedRooms = parseOptionalNumber(filters.rooms);
  const hasActiveFilters =
    normalizedSearch.length > 0 ||
    Object.values(filters).some((value) => value.trim().length > 0) ||
    sortBy !== "score";
  const cityOptions = Array.from(
    new Set(activeItems.map((item) => item.city).filter((value): value is string => Boolean(value))),
  ).sort((left, right) => left.localeCompare(right));
  const districtOptions = Array.from(
    new Set(
      activeItems
        .filter((item) => !filters.city || item.city === filters.city)
        .map((item) => item.district)
        .filter((value): value is string => Boolean(value)),
    ),
  ).sort((left, right) => left.localeCompare(right));
  const roomOptions = Array.from(
    new Set(activeItems.map((item) => item.rooms).filter((value): value is number => value !== null)),
  ).sort((left, right) => left - right);
  const visibleItems = [...activeItems]
    .filter((item) => {
      if (normalizedSearch.length > 0) {
        const searchableText = [
          item.title,
          item.city,
          item.district,
          item.building_type,
          item.condition,
        ]
          .filter((value): value is string => Boolean(value))
          .join(" ")
          .toLowerCase();

        if (!searchableText.includes(normalizedSearch)) {
          return false;
        }
      }

      if (filters.city && item.city !== filters.city) {
        return false;
      }

      if (filters.district && item.district !== filters.district) {
        return false;
      }

      const comparableListingPrice = getComparableListingPrice(item);

      if (minPrice !== null && (comparableListingPrice === null || comparableListingPrice < minPrice)) {
        return false;
      }

      if (maxPrice !== null && (comparableListingPrice === null || comparableListingPrice > maxPrice)) {
        return false;
      }

      if (minArea !== null && (item.area === null || item.area < minArea)) {
        return false;
      }

      if (maxArea !== null && (item.area === null || item.area > maxArea)) {
        return false;
      }

      if (selectedRooms !== null && item.rooms !== selectedRooms) {
        return false;
      }

      return true;
    })
    .sort((left, right) => {
      if (sortBy === "undervaluation_percent") {
        return (
          right.delta_pct - left.delta_pct ||
          right.score - left.score ||
          left.listing_id - right.listing_id
        );
      }

      if (sortBy === "listing_price") {
        return (
          compareNullableNumbers(
            getComparableListingPrice(left),
            getComparableListingPrice(right),
            "asc",
          ) ||
          right.score - left.score ||
          left.listing_id - right.listing_id
        );
      }

      if (sortBy === "predicted_price") {
        return (
          compareNullableNumbers(left.predicted_price, right.predicted_price, "desc") ||
          right.delta_pct - left.delta_pct ||
          left.listing_id - right.listing_id
        );
      }

      if (viewMode === "shortlist") {
        return (
          compareNullableNumbers(left.rank_position, right.rank_position, "asc") ||
          right.score - left.score ||
          left.listing_id - right.listing_id
        );
      }

      return right.score - left.score || right.delta_pct - left.delta_pct || left.listing_id - right.listing_id;
    });

  function updateFilter<Key extends keyof FilterState>(key: Key, value: FilterState[Key]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function resetControls() {
    setSearchTerm("");
    setSortBy("score");
    setFilters(EMPTY_FILTERS);
  }

  return (
    <AppShell user={currentUserQuery.data}>
      <section className={styles.hero}>
        <div>
          <p className={styles.kicker}>{t("opportunities.hero.kicker")}</p>
          <h2 className={styles.heading}>{t("opportunities.hero.heading")}</h2>
          <p className={styles.description}>{t("opportunities.hero.description")}</p>
        </div>
        <div className={styles.controls}>
          <button
            className={styles.addObjectButton}
            onClick={() => setAddObjectOpen(true)}
            type="button"
          >
            {t("opportunities.hero.addObject")}
          </button>
          <div className={styles.segmentedControl}>
            <button
              className={viewMode === "opportunities" ? styles.segmentActive : styles.segment}
              onClick={() => setViewMode("opportunities")}
              type="button"
            >
              {t("opportunities.tabs.opportunities")}
            </button>
            <button
              className={viewMode === "shortlist" ? styles.segmentActive : styles.segment}
              onClick={() => setViewMode("shortlist")}
              type="button"
            >
              {t("opportunities.tabs.shortlist")}
            </button>
          </div>
          <div className={styles.sortControl}>
            <span>{t("opportunities.sort.label")}</span>
            <select
              className={styles.select}
              onChange={(event) => setSortBy(event.target.value as OpportunitySortBy)}
              value={sortBy}
            >
              <option value="score">{t("opportunities.sort.score")}</option>
              <option value="undervaluation_percent">
                {t("opportunities.sort.undervaluation")}
              </option>
              <option value="listing_price">{t("opportunities.sort.listingPrice")}</option>
              <option value="predicted_price">{t("opportunities.sort.predictedPrice")}</option>
            </select>
          </div>
        </div>
      </section>

      <section className={styles.toolbar}>
        <label className={styles.searchField}>
          <span className={styles.fieldLabel}>{t("filters.search")}</span>
          <input
            className={styles.textInput}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder={t("filters.searchPlaceholder")}
            type="search"
            value={searchTerm}
          />
        </label>

        <label className={styles.filterField}>
          <span className={styles.fieldLabel}>{t("filters.city")}</span>
          <select
            className={styles.selectInput}
            onChange={(event) => {
              const nextCity = event.target.value;
              setFilters((current) => ({
                ...current,
                city: nextCity,
                district: current.city !== nextCity ? "" : current.district,
              }));
            }}
            value={filters.city}
          >
            <option value="">{t("filters.allCities")}</option>
            {cityOptions.map((city) => (
              <option key={city} value={city}>
                {city}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.filterField}>
          <span className={styles.fieldLabel}>{t("filters.district")}</span>
          <select
            className={styles.selectInput}
            onChange={(event) => updateFilter("district", event.target.value)}
            value={filters.district}
          >
            <option value="">{t("filters.allDistricts")}</option>
            {districtOptions.map((district) => (
              <option key={district} value={district}>
                {district}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.filterField}>
          <span className={styles.fieldLabel}>{t("filters.priceFrom")}</span>
          <input
            className={styles.textInput}
            inputMode="numeric"
            min="0"
            onChange={(event) => updateFilter("minPrice", event.target.value)}
            placeholder={t("filters.any")}
            type="number"
            value={filters.minPrice}
          />
        </label>

        <label className={styles.filterField}>
          <span className={styles.fieldLabel}>{t("filters.priceTo")}</span>
          <input
            className={styles.textInput}
            inputMode="numeric"
            min="0"
            onChange={(event) => updateFilter("maxPrice", event.target.value)}
            placeholder={t("filters.any")}
            type="number"
            value={filters.maxPrice}
          />
        </label>

        <label className={styles.filterField}>
          <span className={styles.fieldLabel}>{t("filters.areaFrom")}</span>
          <input
            className={styles.textInput}
            inputMode="decimal"
            min="0"
            onChange={(event) => updateFilter("minArea", event.target.value)}
            placeholder={t("filters.any")}
            type="number"
            value={filters.minArea}
          />
        </label>

        <label className={styles.filterField}>
          <span className={styles.fieldLabel}>{t("filters.areaTo")}</span>
          <input
            className={styles.textInput}
            inputMode="decimal"
            min="0"
            onChange={(event) => updateFilter("maxArea", event.target.value)}
            placeholder={t("filters.any")}
            type="number"
            value={filters.maxArea}
          />
        </label>

        <label className={styles.filterField}>
          <span className={styles.fieldLabel}>{t("filters.rooms")}</span>
          <select
            className={styles.selectInput}
            onChange={(event) => updateFilter("rooms", event.target.value)}
            value={filters.rooms}
          >
            <option value="">{t("filters.any")}</option>
            {roomOptions.map((rooms) => (
              <option key={rooms} value={String(rooms)}>
                {rooms}
              </option>
            ))}
          </select>
        </label>

        <button
          className={styles.resetButton}
          disabled={!hasActiveFilters}
          onClick={resetControls}
          type="button"
        >
          {t("filters.reset")}
        </button>
      </section>

      <section className={styles.helpGrid}>
        <article className={styles.helpCard}>
          <h3>{t("opportunities.help.modelEstimateTitle")}</h3>
          <p>{t("opportunities.help.modelEstimateBody")}</p>
        </article>
        <article className={styles.helpCard}>
          <h3>{t("opportunities.help.deltaAbsTitle")}</h3>
          <p>{t("opportunities.help.deltaAbsBody")}</p>
        </article>
        <article className={styles.helpCard}>
          <h3>{t("opportunities.help.deltaPctTitle")}</h3>
          <p>{t("opportunities.help.deltaPctBody")}</p>
        </article>
        <article className={styles.helpCard}>
          <h3>{t("opportunities.help.usageTitle")}</h3>
          <p>{t("opportunities.help.usageBody")}</p>
        </article>
      </section>

      {toggleShortlistMutation.isError ? (
        <div className={styles.inlineBanner}>
          {isApiError(toggleShortlistMutation.error)
            ? toggleShortlistMutation.error.message
            : t("errors.shortlistUpdateFailed")}
        </div>
      ) : null}

      {activeQuery.isLoading ? (
        <StatusCard
          title={
            viewMode === "opportunities"
              ? t("opportunities.loading.opportunities")
              : t("opportunities.loading.shortlist")
          }
          description={t("opportunities.loading.description")}
        />
      ) : null}

      {activeQuery.isError ? (
        <StatusCard
          tone="error"
          title={t("opportunities.error.title")}
          description={
            isApiError(activeError) ? activeError.message : t("opportunities.error.description")
          }
          actionLabel={t("common.retry")}
          onAction={() => void activeQuery.refetch()}
        />
      ) : null}

      {!activeQuery.isLoading && !activeQuery.isError && activeItems.length === 0 ? (
        <EmptyState
          title={
            viewMode === "opportunities"
              ? t("opportunities.empty.opportunitiesTitle")
              : t("opportunities.empty.shortlistTitle")
          }
          description={
            viewMode === "opportunities"
              ? t("opportunities.empty.opportunitiesDescription")
              : t("opportunities.empty.shortlistDescription")
          }
        />
      ) : null}

      {!activeQuery.isLoading && !activeQuery.isError && activeItems.length > 0 ? (
        <div className={styles.resultsSection}>
          <div className={styles.resultsMeta}>
            {t("opportunities.resultsMeta", {
              visible: visibleItems.length,
              total: activeItems.length,
            })}
          </div>

          {visibleItems.length > 0 ? (
            <OpportunitiesTable
              items={visibleItems}
              onToggleSave={(item) => toggleShortlistMutation.mutate(item)}
              pendingListingId={pendingListingId}
              view={viewMode}
            />
          ) : (
            <EmptyState
              title={t("opportunities.empty.filteredTitle")}
              description={t("opportunities.empty.filteredDescription")}
            />
          )}
        </div>
      ) : null}
      <AddObjectModal open={isAddObjectOpen} onClose={() => setAddObjectOpen(false)} />
    </AppShell>
  );
}
