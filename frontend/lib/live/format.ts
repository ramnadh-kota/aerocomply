// Formatting helpers for the generic live list/detail views (pure, unit-tested).

const HIDDEN_KEYS = new Set(["organization_id", "hashed_password", "provenance", "event_metadata"]);
const ACRONYMS = new Set(["id", "po", "url", "kwh", "mtow", "hv", "rul", "tat", "aog"]);

export function humanizeKey(key: string): string {
  return key
    .split("_")
    .filter(Boolean)
    .map((w) => (ACRONYMS.has(w.toLowerCase()) ? w.toUpperCase() : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

export function isIsoDateTime(value: unknown): value is string {
  return typeof value === "string" && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value) && !Number.isNaN(Date.parse(value));
}

export function formatScalar(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (isIsoDateTime(value)) return new Date(value).toLocaleString();
  if (typeof value === "number") {
    if (key.endsWith("_cents")) return (value / 100).toLocaleString(undefined, { style: "currency", currency: "USD" });
    return Number.isInteger(value) ? String(value) : String(Math.round(value * 1000) / 1000);
  }
  return String(value);
}

/** Key/value pairs for display: scalars only, tenant plumbing and nested structures omitted, stable order. */
export function scalarEntries(obj: Record<string, unknown>): [string, unknown][] {
  return Object.entries(obj).filter(
    ([k, v]) => !HIDDEN_KEYS.has(k) && (v === null || ["string", "number", "boolean"].includes(typeof v))
  );
}
