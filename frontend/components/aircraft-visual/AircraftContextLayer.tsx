"use client";

import type { CSSProperties } from "react";
import Image from "next/image";
import {
  resolveAircraftCategory,
  getAircraftVisualConfig,
  resolveHeroPhoto,
  type AircraftRegion,
} from "@/lib/aircraft-visual/config";
import { getSilhouetteComponent } from "./silhouettes";

/**
 * Approximate screen-space anchor points (as % of the photo layer's box)
 * for each region, used only when a real photo is the active background
 * (no per-component photo coordinates exist the way they do for the
 * hand-drawn SVG silhouettes). These are eyeballed against the two source
 * photos' actual composition (737: three-quarter front-right, nose at
 * left-center; A320: side profile, nose at left) and are NOT pixel-precise
 * — they are a reasonable approximation, not a claim of exact component
 * location.
 */
const PHOTO_REGION_ANCHORS: Record<AircraftRegion, { top: string; left: string }> = {
  cockpit: { top: "42%", left: "18%" },
  engine: { top: "62%", left: "42%" },
  wing: { top: "58%", left: "50%" },
  landingGear: { top: "78%", left: "48%" },
  fuselage: { top: "50%", left: "55%" },
  tail: { top: "38%", left: "82%" },
};

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

export function AircraftContextLayer({ aircraftTypeId, opacity, highlightedRegion, faultRegion, showGrid }: AircraftContextLayerProps) {
  if (!aircraftTypeId) {
    return <FleetContextLayer showGrid={showGrid} />;
  }

  const heroPhoto = resolveHeroPhoto(aircraftTypeId);
  if (heroPhoto) {
    return (
      <PhotoContextLayer
        photo={heroPhoto}
        showGrid={showGrid}
        highlightedRegion={highlightedRegion}
        faultRegion={faultRegion}
      />
    );
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
 * Primary visual for the two real aircraft types with a verified, licensed
 * source photo (737-800, A320-200). The photo is the primary aircraft
 * representation here, per the product requirement — a dark gradient
 * overlay (not a flat opacity reduction) keeps text readable while leaving
 * the photo itself crisp. The blueprint grid, when requested, is kept as a
 * faint secondary decorative accent over the photo, never competing with it.
 */
function PhotoContextLayer({
  photo,
  showGrid,
  highlightedRegion,
  faultRegion,
}: {
  photo: NonNullable<ReturnType<typeof resolveHeroPhoto>>;
  showGrid?: boolean;
  highlightedRegion?: AircraftRegion;
  faultRegion?: AircraftRegion | null;
}) {
  const activeRegion = faultRegion ?? highlightedRegion ?? null;
  const anchor = activeRegion ? PHOTO_REGION_ANCHORS[activeRegion] : null;
  const isFault = !!faultRegion;

  return (
    <div className="ac-aircraft-context-layer ac-aircraft-context-layer--photo" aria-hidden="true" role="presentation">
      <div className="ac-aircraft-context-photo-wrap">
        <Image
          src={photo.src}
          alt={photo.alt}
          width={photo.width}
          height={photo.height}
          className="ac-aircraft-context-photo"
          sizes="100vw"
          priority
        />
        <div className="ac-aircraft-context-photo-overlay" />
        {showGrid && <div className="ac-aircraft-context-grid ac-aircraft-context-grid--photo" />}
        {anchor && (
          <div
            className={`ac-context-photo-marker${isFault ? " ac-context-photo-marker--fault" : " ac-context-photo-marker--highlighted"}`}
            style={{ top: anchor.top, left: anchor.left }}
          >
            {isFault && <span className="ac-context-photo-marker-glyph">!</span>}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Fleet-wide treatment (dashboard, aircraft list, fleet health — any page
 * with no single aircraftTypeId): renders NO aircraft shape at all. This
 * used to layer two generic aircraft silhouettes at low opacity; that was
 * exactly the kind of line-art/wireframe aircraft that must never appear
 * outside an explicit single-aircraft hero (see product direction — no
 * SVG/silhouette/wireframe/blueprint aircraft on any page that isn't a
 * dedicated aircraft-detail view). A fleet-wide page has no single
 * aircraft to depict anyway, so the honest treatment is no aircraft
 * imagery here — only the optional grid, same as the dense-data
 * background.
 */
function FleetContextLayer({ showGrid }: { showGrid?: boolean }) {
  if (!showGrid) return null;
  return (
    <div className="ac-aircraft-context-layer ac-aircraft-context-layer--fleet" aria-hidden="true" role="presentation">
      <div className="ac-aircraft-context-grid" />
    </div>
  );
}
