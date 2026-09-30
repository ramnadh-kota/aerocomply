// Pure presentation helpers for the telemetry panel (unit-tested in tests/telemetry-helpers.test.ts).
// They only label values the backend already computed.

type Kind = "COMPLIANT" | "REVIEW_REQUIRED" | "NON_COMPLIANT" | "UNKNOWN";

export function stateBadge(state: string): { kind: Kind; label: string } {
  switch (state) {
    case "ACTIVE":
      return { kind: "COMPLIANT", label: "Receiving data" };
    case "STALE":
      return { kind: "REVIEW_REQUIRED", label: "Stale" };
    case "NO_TELEMETRY_RECORDED":
      return { kind: "UNKNOWN", label: "No telemetry" };
    default:
      return { kind: "UNKNOWN", label: state };
  }
}

/** Tone of one sensor reading: bad data quality dominates, then age beyond the freshness policy. */
export function readingTone(
  dataQuality: string,
  ageSeconds: number,
  warnAfterSeconds: number
): { kind: Kind; label: string } {
  if (dataQuality === "INVALID" || dataQuality === "OUT_OF_RANGE") {
    return { kind: "NON_COMPLIANT", label: dataQuality.replace("_", " ").toLowerCase() };
  }
  if (dataQuality !== "VALID") {
    return { kind: "REVIEW_REQUIRED", label: dataQuality.toLowerCase() };
  }
  if (warnAfterSeconds > 0 && ageSeconds > warnAfterSeconds) {
    return { kind: "REVIEW_REQUIRED", label: "stale" };
  }
  return { kind: "COMPLIANT", label: "valid" };
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}
