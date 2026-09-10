"use client";

import type { CSSProperties } from "react";
import { usePathname } from "next/navigation";

/**
 * Purely decorative background layer for the application shell. Never
 * conveys information — aria-hidden and pointer-events: none, sits behind
 * all real content (see .ac-shell's z-index in globals.css).
 *
 * CONTEXT-AWARE BY DESIGN — this is an explicit allowlist, not an opacity
 * dial. /images/aerocomply-mro-background.svg contains a recognizable
 * aircraft/fuselage silhouette, so it is only rendered on routes where
 * aircraft imagery genuinely helps the user understand the aircraft/fleet
 * they're looking at (dashboard hero, aircraft list/detail, fleet
 * overview, maintenance/inspection context). Every other route — dense
 * tables, notifications, admin/RBAC screens, audit logs, reports — gets a
 * plain dark gradient with NO aircraft imagery, so the background never
 * competes with rows of operational data. See CONTEXT_RULES below to add
 * a route to either list; do not add a silhouette/wireframe/blueprint
 * aircraft anywhere in DENSE_ROUTE territory.
 */

type Zone = "aircraftContext" | "denseData";

const AIRCRAFT_CONTEXT_RULES: { test: (path: string) => boolean; opacity: number }[] = [
  { test: (p) => p === "/dashboard", opacity: 0.19 },
  { test: (p) => p.startsWith("/aircraft"), opacity: 0.12 },
  { test: (p) => p.startsWith("/fleet"), opacity: 0.12 },
  { test: (p) => p.startsWith("/engines"), opacity: 0.12 },
  { test: (p) => p.startsWith("/components"), opacity: 0.12 },
  { test: (p) => p.startsWith("/maintenance/control-tower"), opacity: 0.1 },
  { test: (p) => p.startsWith("/maintenance/aog-recovery"), opacity: 0.1 },
  { test: (p) => /^\/aircraft\/[^/]+\/configuration/.test(p), opacity: 0.1 },
  { test: (p) => p.startsWith("/inspections"), opacity: 0.1 },
  { test: (p) => p.startsWith("/maintenance/inspections"), opacity: 0.1 },
];

function zoneForPath(pathname: string): { zone: Zone; opacity: number } {
  const match = AIRCRAFT_CONTEXT_RULES.find((rule) => rule.test(pathname));
  if (match) return { zone: "aircraftContext", opacity: match.opacity };
  return { zone: "denseData", opacity: 0 };
}

export function AviationBackground() {
  const pathname = usePathname();
  const { zone, opacity } = zoneForPath(pathname ?? "");

  if (zone === "denseData") {
    // No aircraft imagery — a plain dark gradient only, so tables, alert
    // rows, and admin lists always sit on a clean, uncluttered background.
    return (
      <div className="ac-aviation-bg" aria-hidden="true" role="presentation">
        <div className="ac-aviation-bg-overlay ac-aviation-bg-overlay--plain" />
      </div>
    );
  }

  return (
    <div className="ac-aviation-bg" aria-hidden="true" role="presentation">
      <div className="ac-aviation-bg-image" style={{ "--ac-bg-opacity": opacity } as CSSProperties} />
      <div className="ac-aviation-bg-overlay" />
    </div>
  );
}
