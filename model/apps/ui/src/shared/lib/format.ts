export function formatMoney(value: number | null, currency: "RUB") {
  if (value === null) {
    return "—";
  }

  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatCurrencyCode(currency: "RUB") {
  return currency;
}

export function formatPercent(value: number | null) {
  if (value === null) {
    return "—";
  }

  return `${(value * 100).toFixed(1)}%`;
}

export function formatArea(value: number | null) {
  if (value === null) {
    return "—";
  }

  return `${new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 1,
  }).format(value)} m²`;
}

export function formatFloor(floor: number | null, totalFloors: number | null) {
  if (floor === null && totalFloors === null) {
    return "floor —";
  }

  return `floor ${floor ?? "—"}/${totalFloors ?? "—"}`;
}

export function formatNumber(value: number | null, fractionDigits: number, suffix = "") {
  if (value === null) {
    return `—${suffix}`;
  }

  return `${new Intl.NumberFormat("en-US", {
    maximumFractionDigits: fractionDigits,
    minimumFractionDigits: fractionDigits,
  }).format(value)}${suffix}`;
}
