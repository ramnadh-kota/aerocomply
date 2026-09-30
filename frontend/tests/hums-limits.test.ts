import { describe, it, expect } from "vitest";
import { limitsLabel, limitsToInput, parseLimits } from "../lib/hums/limits";

describe("sensor limit editor validation", () => {
  it("clears both to return to platform defaults", () => {
    expect(parseLimits({ warning: "", critical: " " })).toEqual({ ok: true, payload: { warning_threshold: null, critical_threshold: null } });
  });
  it("accepts an ordered positive pair", () => {
    expect(parseLimits({ warning: "12.5", critical: "30" })).toEqual({ ok: true, payload: { warning_threshold: 12.5, critical_threshold: 30 } });
  });
  it.each([
    [{ warning: "5", critical: "" }],
    [{ warning: "", critical: "9" }],
    [{ warning: "abc", critical: "9" }],
    [{ warning: "0", critical: "9" }],
    [{ warning: "-1", critical: "9" }],
    [{ warning: "9", critical: "9" }],
    [{ warning: "9", critical: "3" }],
    [{ warning: "Infinity", critical: "9" }],
  ])("rejects %j", (input) => {
    expect(parseLimits(input).ok).toBe(false);
  });
  it("round-trips values into the form", () => {
    expect(limitsToInput(5, 8)).toEqual({ warning: "5", critical: "8" });
    expect(limitsToInput(null, undefined)).toEqual({ warning: "", critical: "" });
    expect(limitsLabel(null, null)).toBe("platform defaults");
    expect(limitsLabel(5, 8)).toBe("warning 5 / critical 8");
  });
});
