import type { SVGProps } from "react";
import type { AircraftRegion } from "@/lib/aircraft-visual/config";

interface RegionalTurbopropSilhouetteProps extends SVGProps<SVGSVGElement> {
  highlightedRegion?: AircraftRegion;
  faultRegion?: AircraftRegion | null;
}

// Marker anchor points read off this file's own path coordinates above.
// The engine marker sits on the top-mounted nacelle/prop disc, distinct
// from the high, straight wing it's mounted on.
const MARKERS: Partial<Record<AircraftRegion, { x: number; y: number }>> = {
  cockpit: { x: 27, y: 68 },
  fuselage: { x: 90, y: 68 },
  wing: { x: 195, y: 33 },
  engine: { x: 165, y: 39 },
  landingGear: { x: 225, y: 73 },
  tail: { x: 260, y: 52 },
};

/**
 * Simple technical-line-art side-profile silhouette of a regional
 * turboprop (e.g. ATR / Q400 class): high, straight wing, visible engine
 * nacelle with propeller disc, shorter fuselage.
 */
export function RegionalTurbopropSilhouette({ highlightedRegion, faultRegion, ...props }: RegionalTurbopropSilhouetteProps) {
  return (
    <svg viewBox="0 0 340 120" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" {...props}>
      <path d="M20 66 L250 62 Q275 61 296 56 L298 61 Q276 68 250 70 L100 74 Q65 76 34 72 Z" />
      <path d="M130 44 L200 30 L204 34 L138 48 Z" />
      <path d="M140 48 L178 92 L188 90 L156 50 Z" />
      <path d="M248 62 L272 42 L278 43 L258 64 Z" />
      <rect x="150" y="34" width="30" height="10" rx="3" />
      <circle cx="152" cy="39" r="20" strokeDasharray="2 3" />
      <line x1="55" y1="72" x2="55" y2="78" />
      <line x1="225" y1="70" x2="225" y2="76" />
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
