// Pure helpers for the helicopter / eVTOL fleet pages (no React, unit-tested).

export type AirframeFamily = "helicopter" | "evtol";

export interface FieldSpec {
  key: string;
  label: string;
  kind: "number" | "int" | "enum";
  options?: readonly string[];
  min?: number;
  max?: number;
}

export const FAMILY_CONFIG = {
  helicopter: {
    title: "Helicopters",
    singular: "Helicopter",
    basePath: "/helicopters",
    apiPath: "/helicopters",
    suite: "HELICOPTER",
    feature: "helicopter_fleet_management",
    fields: [
      { key: "rotor_system", label: "Rotor system", kind: "enum", options: ["SINGLE_MAIN_TAIL", "TANDEM", "COAXIAL", "NOTAR", "TILTROTOR", "OTHER"] },
      { key: "main_rotor_blade_count", label: "Main rotor blades", kind: "int", min: 2, max: 12 },
      { key: "engine_count", label: "Engines", kind: "int", min: 1, max: 4 },
      { key: "max_takeoff_weight_kg", label: "MTOW (kg)", kind: "number", min: 0 },
    ] as FieldSpec[],
  },
  evtol: {
    title: "eVTOL / AAM",
    singular: "eVTOL",
    basePath: "/evtols",
    apiPath: "/evtols",
    suite: "EVTOL_AAM",
    feature: "evtol_fleet_management",
    fields: [
      { key: "configuration", label: "Configuration", kind: "enum", options: ["MULTICOPTER", "LIFT_CRUISE", "VECTORED_THRUST", "TILTROTOR", "OTHER"] },
      { key: "propulsor_count", label: "Propulsors", kind: "int", min: 1, max: 64 },
      { key: "battery_nominal_energy_kwh", label: "Battery energy (kWh)", kind: "number", min: 0 },
      { key: "hv_bus_nominal_voltage_v", label: "HV bus (V)", kind: "number", min: 0 },
      { key: "max_takeoff_weight_kg", label: "MTOW (kg)", kind: "number", min: 0 },
      { key: "passenger_capacity", label: "Passengers", kind: "int", min: 0 },
    ] as FieldSpec[],
  },
} as const;

export type DetailFormValues = Record<string, string>;

/** Form text -> API `detail` object. Empty strings are omitted; invalid values yield `errors` (never a silent coerce). */
export function buildDetailPayload(
  fields: readonly FieldSpec[],
  values: DetailFormValues
): { detail: Record<string, string | number>; errors: Record<string, string> } {
  const detail: Record<string, string | number> = {};
  const errors: Record<string, string> = {};
  for (const f of fields) {
    const raw = (values[f.key] ?? "").trim();
    if (raw === "") continue;
    if (f.kind === "enum") {
      if (!f.options?.includes(raw)) errors[f.key] = `${f.label} must be one of ${f.options?.join(", ")}`;
      else detail[f.key] = raw;
      continue;
    }
    const n = Number(raw);
    if (!Number.isFinite(n)) {
      errors[f.key] = `${f.label} must be a number`;
    } else if (f.kind === "int" && !Number.isInteger(n)) {
      errors[f.key] = `${f.label} must be a whole number`;
    } else if ((f.min !== undefined && n < f.min) || (f.max !== undefined && n > f.max) || (f.min === 0 && n === 0 && f.kind === "number")) {
      errors[f.key] = `${f.label} is out of range`;
    } else {
      detail[f.key] = n;
    }
  }
  return { detail, errors };
}

/** API detail -> form text, for editing. */
export function detailToForm(fields: readonly FieldSpec[], detail: Record<string, unknown> | null | undefined): DetailFormValues {
  const out: DetailFormValues = {};
  for (const f of fields) {
    const v = detail?.[f.key];
    out[f.key] = v === null || v === undefined ? "" : String(v);
  }
  return out;
}

export function formatHours(totalMinutes: number): string {
  if (!Number.isFinite(totalMinutes) || totalMinutes <= 0) return "0.0 h";
  return `${(totalMinutes / 60).toFixed(1)} h`;
}

export function humanizeEnum(value: string | null | undefined): string {
  if (!value) return "—";
  return value.toLowerCase().split("_").map((w) => w.charAt(0).toUpperCase() + w.slice(1)).join(" ");
}
