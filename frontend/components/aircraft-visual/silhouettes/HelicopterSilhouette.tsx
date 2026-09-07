import type { SVGProps } from "react";
import type { AircraftRegion } from "@/lib/aircraft-visual/config";

interface HelicopterSilhouetteProps extends SVGProps<SVGSVGElement> {
  highlightedRegion?: AircraftRegion;
  faultRegion?: AircraftRegion | null;
}

// Marker anchor points read off this file's own path coordinates above.
// No 'wing' marker: a helicopter has no wing, so that region is honestly
// left unrepresented rather than guessed. 'engine' sits at the rotor mast
// (the turbine/transmission deck), 'tail' at the tail rotor, 'landingGear'
// at the skid midpoint.
const MARKERS: Partial<Record<AircraftRegion, { x: number; y: number }>> = {
  cockpit: { x: 85, y: 50 },
  fuselage: { x: 200, y: 62 },
  engine: { x: 130, y: 37 },
  landingGear: { x: 120, y: 76 },
  tail: { x: 250, y: 52 },
};

/**
 * Simple technical-line-art side-profile silhouette of a helicopter: main
 * rotor disc, cabin/tail boom, tail rotor.
 */
export function HelicopterSilhouette({ highlightedRegion, faultRegion, ...props }: HelicopterSilhouetteProps) {
  return (
    <svg viewBox="0 0 300 110" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" {...props}>
      <line x1="30" y1="34" x2="230" y2="34" />
      <line x1="130" y1="34" x2="130" y2="40" />
      <path d="M100 40 Q160 38 160 40 Q160 62 128 70 Q90 70 78 56 Q76 46 100 40 Z" />
      <path d="M160 55 L250 60 L250 66 L164 64 Z" />
      <path d="M244 44 L250 60 L256 44" />
      <line x1="100" y1="70" x2="94" y2="80" />
      <line x1="140" y1="70" x2="146" y2="80" />
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
