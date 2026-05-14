import { FormEvent, useState } from "react";

import { useLanguage } from "../../../shared/i18n/LanguageContext";
import { PredictObjectInput } from "../model/types";
import styles from "./AddObjectForm.module.css";

type FormState = {
  rooms: string;
  area: string;
  kitchen_area_m2: string;
  floor: string;
  total_floors: string;
  building_type: string;
  object_type: string;
  region: string;
  latitude: string;
  longitude: string;
  listing_price: string;
};

const EMPTY_FORM: FormState = {
  rooms: "",
  area: "",
  kitchen_area_m2: "",
  floor: "",
  total_floors: "",
  building_type: "",
  object_type: "",
  region: "",
  latitude: "",
  longitude: "",
  listing_price: "",
};

const BUILDING_TYPES = ["Panel", "Brick", "Monolith", "Block", "Wooden", "Other"];
const OBJECT_TYPES = ["secondary", "primary"];

type AddObjectFormProps = {
  onSubmit: (input: PredictObjectInput) => void;
  onCancel: () => void;
  isPending: boolean;
  submitError: string | null;
};

function parseNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

type FieldErrors = Partial<Record<keyof FormState, string>>;
type TFunction = ReturnType<typeof useLanguage>["t"];

function validate(state: FormState, t: TFunction): FieldErrors {
  const errors: FieldErrors = {};
  const requiredNumeric: (keyof FormState)[] = [
    "rooms",
    "area",
    "floor",
    "total_floors",
    "listing_price",
  ];

  for (const key of requiredNumeric) {
    const parsed = parseNumber(state[key]);
    if (parsed === null) {
      errors[key] = t("addObject.errors.required");
    } else if (parsed < 0) {
      errors[key] = t("addObject.errors.mustBeNonNegative");
    }
  }

  const area = parseNumber(state.area);
  if (area !== null && area <= 0) errors.area = t("addObject.errors.mustBeGreaterThanZero");

  const rooms = parseNumber(state.rooms);
  if (rooms !== null && rooms < 0) errors.rooms = t("addObject.errors.mustBeNonNegative");

  const floor = parseNumber(state.floor);
  const total = parseNumber(state.total_floors);
  if (floor !== null && total !== null && floor > total) {
    errors.floor = t("addObject.errors.floorExceedsTotal");
  }

  const price = parseNumber(state.listing_price);
  if (price !== null && price <= 0) {
    errors.listing_price = t("addObject.errors.mustBeGreaterThanZero");
  }

  const lat = parseNumber(state.latitude);
  if (state.latitude.trim() && lat === null) errors.latitude = t("addObject.errors.invalidNumber");
  const lon = parseNumber(state.longitude);
  if (state.longitude.trim() && lon === null) errors.longitude = t("addObject.errors.invalidNumber");

  return errors;
}

export function AddObjectForm({
  onSubmit,
  onCancel,
  isPending,
  submitError,
}: AddObjectFormProps) {
  const { t } = useLanguage();
  const [state, setState] = useState<FormState>(EMPTY_FORM);
  const [touched, setTouched] = useState<Partial<Record<keyof FormState, boolean>>>({});
  const errors = validate(state, t);
  const hasErrors = Object.keys(errors).length > 0;

  function update<K extends keyof FormState>(key: K, value: string) {
    setState((current) => ({ ...current, [key]: value }));
  }

  function markTouched(key: keyof FormState) {
    setTouched((current) => ({ ...current, [key]: true }));
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const allTouched: Partial<Record<keyof FormState, boolean>> = {};
    (Object.keys(state) as (keyof FormState)[]).forEach((k) => {
      allTouched[k] = true;
    });
    setTouched(allTouched);

    if (hasErrors) return;

    const input: PredictObjectInput = {
      rooms: parseNumber(state.rooms),
      area: parseNumber(state.area),
      kitchen_area_m2: parseNumber(state.kitchen_area_m2),
      floor: parseNumber(state.floor),
      total_floors: parseNumber(state.total_floors),
      building_type: state.building_type || null,
      object_type: state.object_type || null,
      region: state.region.trim() || null,
      latitude: parseNumber(state.latitude),
      longitude: parseNumber(state.longitude),
      listing_price: parseNumber(state.listing_price),
      listing_currency: "RUB",
    };
    onSubmit(input);
  }

  function fieldError(key: keyof FormState) {
    return touched[key] ? errors[key] : undefined;
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <p className={styles.intro}>
        {t("addObject.intro")}
      </p>

      <div className={styles.grid}>
        <label className={styles.field}>
          <span>{t("addObject.fields.rooms")}</span>
          <input
            type="number"
            min="0"
            step="1"
            value={state.rooms}
            onChange={(e) => update("rooms", e.target.value)}
            onBlur={() => markTouched("rooms")}
          />
          {fieldError("rooms") ? <em className={styles.error}>{fieldError("rooms")}</em> : null}
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.area")}</span>
          <input
            type="number"
            min="0"
            step="0.1"
            value={state.area}
            onChange={(e) => update("area", e.target.value)}
            onBlur={() => markTouched("area")}
          />
          {fieldError("area") ? <em className={styles.error}>{fieldError("area")}</em> : null}
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.kitchenArea")}</span>
          <input
            type="number"
            min="0"
            step="0.1"
            value={state.kitchen_area_m2}
            onChange={(e) => update("kitchen_area_m2", e.target.value)}
          />
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.floor")}</span>
          <input
            type="number"
            min="0"
            step="1"
            value={state.floor}
            onChange={(e) => update("floor", e.target.value)}
            onBlur={() => markTouched("floor")}
          />
          {fieldError("floor") ? <em className={styles.error}>{fieldError("floor")}</em> : null}
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.totalFloors")}</span>
          <input
            type="number"
            min="0"
            step="1"
            value={state.total_floors}
            onChange={(e) => update("total_floors", e.target.value)}
            onBlur={() => markTouched("total_floors")}
          />
          {fieldError("total_floors") ? (
            <em className={styles.error}>{fieldError("total_floors")}</em>
          ) : null}
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.listingPrice")}</span>
          <input
            type="number"
            min="0"
            step="1000"
            value={state.listing_price}
            onChange={(e) => update("listing_price", e.target.value)}
            onBlur={() => markTouched("listing_price")}
          />
          {fieldError("listing_price") ? (
            <em className={styles.error}>{fieldError("listing_price")}</em>
          ) : null}
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.buildingType")}</span>
          <select
            value={state.building_type}
            onChange={(e) => update("building_type", e.target.value)}
          >
            <option value="">—</option>
            {BUILDING_TYPES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.objectType")}</span>
          <select
            value={state.object_type}
            onChange={(e) => update("object_type", e.target.value)}
          >
            <option value="">—</option>
            {OBJECT_TYPES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.region")}</span>
          <input
            type="text"
            value={state.region}
            onChange={(e) => update("region", e.target.value)}
            placeholder={t("addObject.placeholders.region")}
          />
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.latitude")}</span>
          <input
            type="number"
            step="0.000001"
            value={state.latitude}
            onChange={(e) => update("latitude", e.target.value)}
            onBlur={() => markTouched("latitude")}
          />
          {fieldError("latitude") ? (
            <em className={styles.error}>{fieldError("latitude")}</em>
          ) : null}
        </label>

        <label className={styles.field}>
          <span>{t("addObject.fields.longitude")}</span>
          <input
            type="number"
            step="0.000001"
            value={state.longitude}
            onChange={(e) => update("longitude", e.target.value)}
            onBlur={() => markTouched("longitude")}
          />
          {fieldError("longitude") ? (
            <em className={styles.error}>{fieldError("longitude")}</em>
          ) : null}
        </label>
      </div>

      {submitError ? <div className={styles.submitError}>{submitError}</div> : null}

      <div className={styles.actions}>
        <button
          type="button"
          onClick={onCancel}
          className={styles.cancelButton}
          disabled={isPending}
        >
          {t("addObject.actions.cancel")}
        </button>
        <button type="submit" className={styles.submitButton} disabled={isPending}>
          {isPending ? t("addObject.actions.submitting") : t("addObject.actions.submit")}
        </button>
      </div>
    </form>
  );
}
