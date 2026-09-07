import type { SVGProps } from "react";
import type { AircraftRegion } from "@/lib/aircraft-visual/config";

interface WidebodySilhouetteProps extends SVGProps<SVGSVGElement> {
  highlightedRegion?: AircraftRegion;
  faultRegion?: AircraftRegion | null;
}

// Marker anchor points read off this file's own path coordinates above.
const MARKERS: Partial<Record<AircraftRegion, { x: number; y: number }>> = {
  cockpit: { x: 25, y: 76 },
  fuselage: { x: 110, y: 78 },
  wing: { x: 196, y: 45 },
  engine: { x: 230, y: 88 },
  landingGear: { x: 310, y: 82 },
  tail: { x: 368, y: 52 },
};

/**
 * Simple technical-line-art side-profile silhouette of a wide-body jet
 * (e.g. 777 / A350 class): longer, deeper fuselage, larger swept wing with
 * underslung engine, twin-aisle proportions implied by fuselage depth.
 */
export function WidebodySilhouette({ highlightedRegion, faultRegion, ...props }: WidebodySilhouetteProps) {
  return (
    <svg viewBox="0 0 460 130" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" {...props}>
      <path d="M14 72 L350 64 Q385 63 415 56 L418 62 Q388 71 350 74 L130 82 Q80 85 30 79 Z" />
      <path d="M170 70 L215 18 L228 18 L204 70 Z" />
      <path d="M170 75 L212 114 L224 114 L200 75 Z" />
      <path d="M350 65 L382 38 L389 40 L364 67 Z" />
      <ellipse cx="230" cy="88" rx="22" ry="10" />
      <line x1="230" y1="78" x2="230" y2="70" />
      <line x1="70" y1="80" x2="70" y2="87" />
      <line x1="310" y1="76" x2="310" y2="85" />

      {/* Structural / technical detail. */}
      <path d="M22 68 Q38 61 54 61 L54 78 Q36 79 20 75 Z" strokeWidth="1" />
      <line x1="48" y1="61" x2="44" y2="78" strokeWidth="0.75" />
      {Array.from({ length: 19 }, (_, i) => 62 + i * 16).map((x) => (
        <line key={`win-${x}`} x1={x} y1="71" x2={x} y2="76" strokeWidth="0.6" opacity="0.7" />
      ))}
      {Array.from({ length: 7 }, (_, i) => 50 + i * 45).map((x) => (
        <line key={`frame-${x}`} x1={x} y1="68" x2={x} y2="82" strokeWidth="0.5" opacity="0.5" />
      ))}
      <line x1="14" y1="76" x2="350" y2="69" strokeWidth="0.5" opacity="0.6" />
      <path d="M186 44 L216 44" strokeWidth="0.6" opacity="0.6" />
      <path d="M190 65 L212 24" strokeWidth="0.6" opacity="0.6" />
      <path d="M186 105 L210 76" strokeWidth="0.6" opacity="0.6" />
      <line x1="220" y1="20" x2="220" y2="68" strokeWidth="0.5" opacity="0.5" />
      <ellipse cx="230" cy="88" rx="10" ry="5" strokeWidth="0.5" opacity="0.6" />
      <line x1="212" y1="88" x2="248" y2="88" strokeWidth="0.5" opacity="0.5" />
      <line x1="365" y1="55" x2="380" y2="42" strokeWidth="0.6" opacity="0.6" />
      <line x1="130" y1="79" x2="130" y2="84" strokeWidth="0.6" opacity="0.6" />
      <line x1="30" y1="79" x2="30" y2="84" strokeWidth="0.6" opacity="0.6" />
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
