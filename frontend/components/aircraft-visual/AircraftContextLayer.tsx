"use client";

import type { CSSProperties } from "react";
import { resolveAircraftCategory, getAircraftVisualConfig, type AircraftCategory, type AircraftRegion } from "@/lib/aircraft-visual/config";
import { getSilhouetteComponent } from "./silhouettes";

/**
 * Contextual, aircraft-type-aware decorative background layer.
 *
 * Extends the route-based AviationBackground (components/layout/AviationBackground.tsx)
 * with a per-page silhouette that reflects the specific aircraft (or fleet)
 * being viewed. Purely decorative: aria-hidden, pointer-events: none, sits
 * strictly behind real content using the same layering conventions as
 * .ac-aviation-bg (position: fixed, z-index: 0, below .ac-shell's z-index: 1).
 *
 * Pass `aircraftTypeId` for a single-aircraft page (e.g. aircraft detail) to
 * render that type's silhouette. Omit it (fleet-wide pages) to render the
 * generic multi-aircraft treatment — never guess a specific type for a list
 * of many aircraft.
 */

interface AircraftContextLayerProps {
  aircraftTypeId?: string;
  /**
   * Opacity override, 0.05–0.30 per the product's stated range. Defaults to
   * the "hero" tier (prominent, single-aircraft or fleet-hero contexts).
   * Pass a lower value explicitly for data-dense/background contexts
   * (settings, reports, audit) — see HERO_OPACITY / MUTED_OPACITY below.
   */
  opacity?: number;
  /** Region to draw in an emphasized state, e.g. reflecting the active tab. Ignored for the fleet-wide (no aircraftTypeId) treatment. */
  highlightedRegion?: AircraftRegion;
  /** Region to draw with a fault indicator, derived from a real open defect. Ignored for the fleet-wide (no aircraftTypeId) treatment. */
  faultRegion?: AircraftRegion | null;
  /** Renders a faint blueprint/graph-paper grid behind the silhouette. Reserved for hero contexts (dashboard, aircraft detail). */
  showGrid?: boolean;
}

/** Prominent contexts: dashboard, aircraft detail — the hero treatment. */
export const HERO_OPACITY = 0.22;
/** Data-dense/background contexts: settings, reports, audit. */
export const MUTED_OPACITY = 0.12;
const FLEET_OPACITY = 0.16;

export function AircraftContextLayer({ aircraftTypeId, opacity, highlightedRegion, faultRegion, showGrid }: AircraftContextLayerProps) {
  if (!aircraftTypeId) {
    return <FleetContextLayer opacity={opacity ?? FLEET_OPACITY} showGrid={showGrid} />;
  }

  const category = resolveAircraftCategory(aircraftTypeId);
  const config = getAircraftVisualConfig(category);
  const Silhouette = getSilhouetteComponent(config.silhouetteId);

  return (
    <div className="ac-aircraft-context-layer" aria-hidden="true" role="presentation">
      {showGrid && <div className="ac-aircraft-context-grid" />}
      <Silhouette
        className="ac-aircraft-context-svg"
        style={{ "--ac-context-opacity": opacity ?? HERO_OPACITY } as CSSProperties}
        highlightedRegion={highlightedRegion}
        faultRegion={faultRegion}
      />
    </div>
  );
}

/**
 * Fleet-wide treatment: two generic silhouettes layered at low opacity, per
 * Section 12's "Fleet: Multiple aircraft silhouettes" — never claims one
 * specific aircraft type represents the whole fleet.
 */
function FleetContextLayer({ opacity, showGrid }: { opacity: number; showGrid?: boolean }) {
  const category: AircraftCategory = "narrowbody";
  const Primary = getSilhouetteComponent(getAircraftVisualConfig(category).silhouetteId);
  const Secondary = getSilhouetteComponent("generic");

  return (
    <div className="ac-aircraft-context-layer ac-aircraft-context-layer--fleet" aria-hidden="true" role="presentation">
      {showGrid && <div className="ac-aircraft-context-grid" />}
      <Primary
        className="ac-aircraft-context-svg ac-aircraft-context-svg--fleet-a"
        style={{ "--ac-context-opacity": opacity } as CSSProperties}
      />
      <Secondary
        className="ac-aircraft-context-svg ac-aircraft-context-svg--fleet-b"
        style={{ "--ac-context-opacity": opacity * 0.8 } as CSSProperties}
      />
    </div>
  );
}
