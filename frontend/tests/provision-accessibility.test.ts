import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const SRC = readFileSync("app/(app)/platform/organizations/provision/page.tsx", "utf8");

describe("provision page selection controls", () => {
  it("has no clickable non-semantic elements (div/span with onClick)", () => {
    expect(SRC).not.toMatch(/<(div|span)\b[^>]*\bonClick=/s);
  });

  it("renders suite and plan choices as native radio buttons inside labelled radiogroups", () => {
    expect(SRC.match(/role="radiogroup"/g)?.length).toBe(2);
    expect(SRC).toMatch(/aria-label="Product suite"/);
    expect(SRC).toMatch(/aria-label="Commercial plan"/);
    expect(SRC.match(/<button\s+key=\{[sp]\.id\}\s+type="button"\s+role="radio"\s+aria-checked=\{isSelected\}/g)?.length).toBe(2);
  });

  it("does not suppress the global :focus-visible indicator on the choice buttons", () => {
    const css = readFileSync("app/globals.css", "utf8");
    expect(css).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid/);
    expect(SRC).not.toMatch(/outline:\s*["']?(none|0)/);
  });
});
