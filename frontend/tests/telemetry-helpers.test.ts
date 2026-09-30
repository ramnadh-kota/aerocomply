import { describe, it, expect } from "vitest";
import { formatDuration, readingTone, stateBadge } from "../lib/telemetry/helpers";

describe("telemetry state badge", () => {
  it("never presents missing telemetry as healthy", () => {
    expect(stateBadge("NO_TELEMETRY_RECORDED")).toEqual({ kind: "UNKNOWN", label: "No telemetry" });
    expect(stateBadge("ACTIVE").kind).toBe("COMPLIANT");
    expect(stateBadge("STALE").kind).toBe("REVIEW_REQUIRED");
    expect(stateBadge("SOMETHING_NEW")).toEqual({ kind: "UNKNOWN", label: "SOMETHING_NEW" });
  });
});

describe("reading tone", () => {
  const week = 7 * 86400;

  it("bad quality dominates freshness", () => {
    expect(readingTone("INVALID", 1, week).kind).toBe("NON_COMPLIANT");
    expect(readingTone("OUT_OF_RANGE", 1, week).kind).toBe("NON_COMPLIANT");
    expect(readingTone("SUSPECT", 1, week).kind).toBe("REVIEW_REQUIRED");
  });

  it("a valid reading older than the freshness policy is flagged stale", () => {
    expect(readingTone("VALID", 60, week)).toEqual({ kind: "COMPLIANT", label: "valid" });
    expect(readingTone("VALID", week + 1, week)).toEqual({ kind: "REVIEW_REQUIRED", label: "stale" });
  });

  it("a zero freshness threshold disables staleness instead of flagging everything", () => {
    expect(readingTone("VALID", 10 ** 9, 0).kind).toBe("COMPLIANT");
  });
});

describe("duration formatting", () => {
  it("uses the coarsest sensible unit", () => {
    expect(formatDuration(5)).toBe("5s");
    expect(formatDuration(125)).toBe("2m");
    expect(formatDuration(7300)).toBe("2h");
    expect(formatDuration(200000)).toBe("2d");
    expect(formatDuration(-3)).toBe("0s");
  });
});
