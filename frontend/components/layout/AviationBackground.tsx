"use client";

import type { CSSProperties } from "react";
import { usePathname } from "next/navigation";

/**
 * Purely decorative MRO/hangar background layer for the application shell.
 * Never conveys information — aria-hidden and pointer-events: none, sits
 * behind all real content (see .ac-shell's z-index in globals.css).
 *
 * Intensity (opacity) varies per route: data-dense screens (configuration
 * timeline, assessment detail, audit trail) stay more restrained than the
 * dashboard, per the product requirement that the imagery never compete with
 * tables, rule trees, or status badges.
 */

const INTENSITY_RULES: { test: (path: string) => boolean; opacity: number }[] = [
  { test: (p) => p === "/dashboard", opacity: 0.19 },
  { test: (p) => /^\/aircraft\/[^/]+\/configuration/.test(p), opacity: 0.1 },
  { test: (p) => /^\/assessments\/[^/]+/.test(p), opacity: 0.1 },
  { test: (p) => p === "/audit", opacity: 0.1 },
  { test: (p) => p.startsWith("/aircraft"), opacity: 0.12 },
  { test: (p) => p.startsWith("/engines"), opacity: 0.12 },
  { test: (p) => p.startsWith("/components"), opacity: 0.12 },
  { test: (p) => p.startsWith("/regulations"), opacity: 0.12 },
  { test: (p) => p.startsWith("/assessments"), opacity: 0.12 },
  { test: (p) => p.startsWith("/evidence"), opacity: 0.12 },
];

const DEFAULT_OPACITY = 0.12;

function intensityForPath(pathname: string): number {
  const match = INTENSITY_RULES.find((rule) => rule.test(pathname));
  return match?.opacity ?? DEFAULT_OPACITY;
}

export function AviationBackground() {
  const pathname = usePathname();
  const opacity = intensityForPath(pathname ?? "");

  return (
    <div className="ac-aviation-bg" aria-hidden="true" role="presentation">
      <div className="ac-aviation-bg-image" style={{ "--ac-bg-opacity": opacity } as CSSProperties} />
      <div className="ac-aviation-bg-overlay" />
    </div>
  );
}
