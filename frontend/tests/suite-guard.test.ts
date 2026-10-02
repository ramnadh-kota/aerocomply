import { describe, expect, it } from "vitest";
import { isSuiteAllowed } from "../components/auth/SuiteGuard";

describe("isSuiteAllowed", () => {
  it("allows a multi-suite org on any suite it actively holds (regression: MULTI_SUITE blocked /drones)", () => {
    expect(isSuiteAllowed(["DRONE_UAV"], "MULTI_SUITE", ["AIRCRAFT", "DRONE_UAV"])).toBe(true);
    expect(isSuiteAllowed(["AIRCRAFT"], "MULTI_SUITE", ["AIRCRAFT", "DRONE_UAV"])).toBe(true);
  });
  it("blocks a suite the org does not hold", () => {
    expect(isSuiteAllowed(["HELICOPTER"], "MULTI_SUITE", ["AIRCRAFT", "DRONE_UAV"])).toBe(false);
    expect(isSuiteAllowed(["DRONE_UAV"], "AIRCRAFT", ["AIRCRAFT"])).toBe(false);
  });
  it("single-suite and unknown-suite behaviour is unchanged", () => {
    expect(isSuiteAllowed(["AIRCRAFT"], "AIRCRAFT", [])).toBe(true);
    expect(isSuiteAllowed(["DRONE_UAV"], null, [])).toBe(true);
  });
});
