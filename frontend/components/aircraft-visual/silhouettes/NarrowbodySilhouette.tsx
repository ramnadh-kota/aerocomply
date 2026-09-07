import type { SVGProps } from "react";
import type { AircraftRegion } from "@/lib/aircraft-visual/config";

interface NarrowbodySilhouetteProps extends SVGProps<SVGSVGElement> {
  /** Region to draw in an emphasized state (e.g. active tab). */
  highlightedRegion?: AircraftRegion;
  /** Region to draw with a fault indicator (from a real open defect). */
  faultRegion?: AircraftRegion | null;
}

// Marker anchor points read off this file's own path coordinates above.
const MARKERS: Partial<Record<AircraftRegion, { x: number; y: number }>> = {
  cockpit: { x: 35, y: 71 },
  fuselage: { x: 110, y: 73 },
  wing: { x: 170, y: 68 },
  engine: { x: 299, y: 46 },
  landingGear: { x: 270, y: 79 },
  tail: { x: 315, y: 50 },
};

/**
 * Simple, technical-line-art side-profile silhouette of a narrow-body jet
 * (e.g. 737 / A320 class): low, swept wing, single aisle fuselage, swept
 * tail. Single-color, uses currentColor so it themes with the page.
 */
export function NarrowbodySilhouette({ highlightedRegion, faultRegion, ...props }: NarrowbodySilhouetteProps) {
  return (
    <svg viewBox="0 0 400 120" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" {...props}>
      <path d="M20 68 L300 62 Q330 61 355 55 L358 60 Q332 68 300 70 L120 76 Q80 78 40 74 Z" />
      <path d="M150 66 L190 20 L200 20 L182 66 Z" />
      <path d="M150 70 L188 108 L198 108 L180 70 Z" />
      <path d="M300 63 L330 40 L336 41 L316 65 Z" />
      <path d="M296 62 Q292 45 296 30 L302 30 Q304 46 302 62 Z" />
      <line x1="60" y1="76" x2="60" y2="82" />
      <line x1="270" y1="72" x2="270" y2="80" />
      {(Object.entries(MARKERS) as [AircraftRegion, { x: number; y: number }][]).map(([region, pt]) => {
        const isHighlighted = highlightedRegion === region;
        const isFault = faultRegion === region;
        return (
          <g key={region}>
            <circle
              cx={pt.x}
              cy={pt.y}
              r={isHighlighted || isFault ? 4 : 2.5}
              className={
                isFault
                  ? "ac-context-marker ac-context-marker--fault"
                  : isHighlighted
                    ? "ac-context-marker ac-context-marker--highlighted"
                    : "ac-context-marker"
              }
            />
            {isFault && (
              <text x={pt.x + 6} y={pt.y - 4} className="ac-context-marker-fault-glyph">
                !
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
