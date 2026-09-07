"use client";

import type { CSSProperties } from "react";
import { resolveAircraftCategory, getAircraftVisualConfig, type AircraftCategory } from "@/lib/aircraft-visual/config";
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
  /** Opacity override, 0.05–0.30 per the product's stated range. Defaults to a subtle 0.09. */
  opacity?: number;
}

const DEFAULT_OPACITY = 0.09;
const FLEET_OPACITY = 0.07;

export function AircraftContextLayer({ aircraftTypeId, opacity }: AircraftContextLayerProps) {
  if (!aircraftTypeId) {
    return <FleetContextLayer opacity={opacity ?? FLEET_OPACITY} />;
  }

  const category = resolveAircraftCategory(aircraftTypeId);
  const config = getAircraftVisualConfig(category);
  const Silhouette = getSilhouetteComponent(config.silhouetteId);

  return (
    <div className="ac-aircraft-context-layer" aria-hidden="true" role="presentation">
      <Silhouette
        className="ac-aircraft-context-svg"
        style={{ "--ac-context-opacity": opacity ?? DEFAULT_OPACITY } as CSSProperties}
      />
    </div>
  );
}

/**
 * Fleet-wide treatment: two generic silhouettes layered at low opacity, per
 * Section 12's "Fleet: Multiple aircraft silhouettes" — never claims one
 * specific aircraft type represents the whole fleet.
 */
function FleetContextLayer({ opacity }: { opacity: number }) {
  const category: AircraftCategory = "narrowbody";
  const Primary = getSilhouetteComponent(getAircraftVisualConfig(category).silhouetteId);
  const Secondary = getSilhouetteComponent("generic");

  return (
    <div className="ac-aircraft-context-layer ac-aircraft-context-layer--fleet" aria-hidden="true" role="presentation">
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
