// Validation for the per-sensor vibration limit editor (mirrors the backend rules: both limits or neither, both > 0,
// critical strictly greater than warning). Pure and unit-tested; the backend remains the authority.

export interface LimitsInput {
  warning: string;
  critical: string;
}

export type LimitsResult =
  | { ok: true; payload: { warning_threshold: number | null; critical_threshold: number | null } }
  | { ok: false; error: string };

export function parseLimits({ warning, critical }: LimitsInput): LimitsResult {
  const w = warning.trim();
  const c = critical.trim();
  if (w === "" && c === "") return { ok: true, payload: { warning_threshold: null, critical_threshold: null } };
  if (w === "" || c === "") return { ok: false, error: "Set both limits, or clear both to use the platform defaults." };
  const wn = Number(w);
  const cn = Number(c);
  if (!Number.isFinite(wn) || !Number.isFinite(cn)) return { ok: false, error: "Limits must be numbers." };
  if (wn <= 0 || cn <= 0) return { ok: false, error: "Limits must be greater than zero." };
  if (cn <= wn) return { ok: false, error: "The critical limit must be greater than the warning limit." };
  return { ok: true, payload: { warning_threshold: wn, critical_threshold: cn } };
}

export function limitsToInput(warning: number | null | undefined, critical: number | null | undefined): LimitsInput {
  return { warning: warning == null ? "" : String(warning), critical: critical == null ? "" : String(critical) };
}

export function limitsLabel(warning: number | null | undefined, critical: number | null | undefined): string {
  return warning == null || critical == null ? "platform defaults" : `warning ${warning} / critical ${critical}`;
}
