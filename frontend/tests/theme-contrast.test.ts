import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Guards the shared theme tokens in app/globals.css: body-size text must reach WCAG AA (4.5:1) on every surface it is
// used on, in BOTH themes, including status colours on their own tinted badge backgrounds.

const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  const open = css.indexOf("{", start);
  const close = css.indexOf("\n}", open);
  const vars: Record<string, string> = {};
  for (const m of css.slice(open, close).matchAll(/(--ac-[a-z-]+):\s*([^;]+);/g)) vars[m[1]] = m[2].trim();
  return vars;
}

const light = block(":root {");
const dark = { ...light, ...block(':root[data-theme="dark"]') };

type RGB = [number, number, number];
const hex = (h: string): RGB => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB;
const lum = ([r, g, b]: RGB) => {
  const f = (c: number) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const ratio = (a: RGB, b: RGB) => {
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const tint = (fg: RGB, alpha: number, bg: RGB): RGB => fg.map((c, i) => alpha * c + (1 - alpha) * bg[i]) as RGB;
const alphaOf = (v: string) => parseFloat(v.match(/rgba\([^)]*,\s*([\d.]+)\)/)![1]);

describe.each([
  ["light", light],
  ["dark", dark],
])("%s theme contrast", (_name, t) => {
  const surfaces = ["--ac-bg", "--ac-bg-elevated", "--ac-bg-surface", "--ac-bg-surface-hover"].map((k) => hex(t[k]));

  it.each(["--ac-text-primary", "--ac-text-secondary", "--ac-text-muted", "--ac-accent"])("%s is AA on all surfaces", (k) => {
    for (const bg of surfaces) expect(ratio(hex(t[k]), bg)).toBeGreaterThanOrEqual(4.5);
  });

  const val = (k: string): string => {
    let v = t[k];
    while (v.startsWith("var(")) v = t[v.slice(4, -1)];
    return v;
  };

  it("white text on the primary button and dark text on --ac-on-primary fills are AA", () => {
    expect(ratio([255, 255, 255], hex(val("--ac-btn-primary-bg")))).toBeGreaterThanOrEqual(4.5);
    expect(ratio([255, 255, 255], hex(val("--ac-btn-primary-bg-hover")))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(hex(val("--ac-on-primary")), hex(t["--ac-accent"]))).toBeGreaterThanOrEqual(4.5);
  });

  it("accent text is AA on its own muted tint (badges)", () => {
    const fg = hex(t["--ac-accent"]);
    const a = alphaOf(t["--ac-accent-muted"]);
    for (const bg of surfaces) expect(ratio(fg, tint(fg, a, bg))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(["compliant", "non-compliant", "insufficient", "review", "unknown"])("status %s text is AA on its tinted badge", (s) => {
    const fg = hex(t[`--ac-status-${s}`]);
    const a = alphaOf(t[`--ac-status-${s}-bg`]);
    for (const bg of surfaces) expect(ratio(fg, tint(fg, a, bg))).toBeGreaterThanOrEqual(4.5);
  });
});
