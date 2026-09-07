import type { SVGProps } from "react";
import type { AircraftRegion } from "@/lib/aircraft-visual/config";

interface GenericAircraftSilhouetteProps extends SVGProps<SVGSVGElement> {
  highlightedRegion?: AircraftRegion;
  faultRegion?: AircraftRegion | null;
}

// Marker anchor points read off this file's own path coordinates above.
// No 'engine' marker: this fallback outline has no engine shape drawn (it
// deliberately doesn't claim a specific real aircraft type), so an engine
// position would be a guess rather than a read of real geometry.
const MARKERS: Partial<Record<AircraftRegion, { x: number; y: number }>> = {
  cockpit: { x: 27, y: 63 },
  fuselage: { x: 100, y: 65 },
  wing: { x: 163, y: 60 },
  landingGear: { x: 240, y: 67 },
  tail: { x: 280, y: 48 },
};

/**
 * Fallback technical-line-art side-profile silhouette used when the
 * aircraft category can't be confidently classified. Deliberately generic
 * (simple fixed-wing outline) — never claims a specific real aircraft type.
 */
export function GenericAircraftSilhouette({ highlightedRegion, faultRegion, ...props }: GenericAircraftSilhouetteProps) {
  return (
    <svg viewBox="0 0 360 110" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" {...props}>
      <path d="M18 60 L270 56 Q296 55 316 50 L318 55 Q298 62 270 64 L110 68 Q72 70 36 66 Z" />
      <path d="M140 58 L176 22 L186 22 L166 58 Z" />
      <path d="M140 62 L174 96 L184 96 L164 62 Z" />
      <path d="M268 57 L292 38 L298 39 L280 59 Z" />
      <line x1="55" y1="66" x2="55" y2="72" />
      <line x1="240" y1="63" x2="240" y2="70" />

      {/* Structural / technical detail. */}
      <path d="M26 58 Q38 53 50 53 L50 65 Q36 66 24 63 Z" strokeWidth="1" />
      <line x1="46" y1="53" x2="43" y2="65" strokeWidth="0.75" />
      {Array.from({ length: 13 }, (_, i) => 58 + i * 14).map((x) => (
        <line key={`win-${x}`} x1={x} y1="58" x2={x} y2="62" strokeWidth="0.6" opacity="0.7" />
      ))}
      {Array.from({ length: 5 }, (_, i) => 40 + i * 38).map((x) => (
        <line key={`frame-${x}`} x1={x} y1="56" x2={x} y2="68" strokeWidth="0.5" opacity="0.5" />
      ))}
      <line x1="18" y1="63" x2="270" y2="58" strokeWidth="0.5" opacity="0.6" />
      <path d="M154 34 L172 34" strokeWidth="0.6" opacity="0.6" />
      <path d="M157 54 L170 22" strokeWidth="0.5" opacity="0.5" />
      <path d="M154 82 L170 65" strokeWidth="0.5" opacity="0.5" />
      <line x1="110" y1="68" x2="110" y2="73" strokeWidth="0.6" opacity="0.6" />
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
