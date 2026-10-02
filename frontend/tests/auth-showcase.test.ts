import { describe, expect, it } from "vitest";
import { SHOWCASE_SLIDES, easeToward, wrapOffset } from "@/components/auth-showcase/slides";

describe("auth showcase content", () => {
  it("covers the five approved categories with headline, description and CTA", () => {
    expect(SHOWCASE_SLIDES.map((s) => s.id)).toEqual(["drone", "aircraft", "helicopter", "evtol", "intelligence"]);
    for (const s of SHOWCASE_SLIDES) {
      expect(s.headline.length).toBeGreaterThan(0);
      expect(s.description.length).toBeGreaterThan(0);
      expect(s.cta.length).toBeGreaterThan(0);
      expect(s.capabilities.length).toBeGreaterThan(0);
    }
  });

  it("uses the approved headlines", () => {
    const byId = Object.fromEntries(SHOWCASE_SLIDES.map((s) => [s.id, s.headline]));
    expect(byId.drone).toBe("Beyond Flight. Into Intelligence.");
    expect(byId.aircraft).toBe("Precision Engineered. Intelligence Driven.");
    expect(byId.helicopter).toBe("Mission Ready. Always Connected.");
    expect(byId.evtol).toBe("A New Dimension of Aerial Mobility.");
    expect(byId.intelligence).toBe("One Intelligence Layer. Every Asset.");
  });

  it("ships no unlicensed photo references by default", () => {
    expect(SHOWCASE_SLIDES.every((s) => s.photo === undefined)).toBe(true);
  });
});

describe("carousel math", () => {
  it("wraps positive, negative and oversized offsets into [0, loop)", () => {
    expect(wrapOffset(10, 100)).toBe(10);
    expect(wrapOffset(110, 100)).toBe(10);
    expect(wrapOffset(-10, 100)).toBe(90);
    expect(wrapOffset(-210, 100)).toBe(90);
    expect(wrapOffset(100, 100)).toBe(0);
  });

  it("returns 0 when the loop width is not yet measurable", () => {
    expect(wrapOffset(50, 0)).toBe(0);
    expect(wrapOffset(50, Number.NaN)).toBe(0);
  });

  it("eases toward a target without overshooting", () => {
    const next = easeToward(0, 26, 0.016, 3.2);
    expect(next).toBeGreaterThan(0);
    expect(next).toBeLessThan(26);
    expect(easeToward(5, 5, 0.016, 3)).toBe(5);
    expect(easeToward(0, 10, 10, 3)).toBe(10); // large dt clamps to the target
  });
});
