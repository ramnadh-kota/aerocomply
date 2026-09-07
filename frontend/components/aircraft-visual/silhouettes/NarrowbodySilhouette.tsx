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

      {/* Structural / technical detail — fuselage frame stations, cabin
          windows, panel lines, cockpit glazing, spars — a CAD/blueprint
          register of detail, not decoration. */}
      <path d="M28 64 Q42 58 56 58 L56 72 Q40 73 26 70 Z" strokeWidth="1" />
      <line x1="50" y1="58" x2="46" y2="72" strokeWidth="0.75" />
      {Array.from({ length: 15 }, (_, i) => 66 + i * 14).map((x) => (
        <line key={`win-${x}`} x1={x} y1="66" x2={x} y2="70" strokeWidth="0.6" opacity="0.7" />
      ))}
      {Array.from({ length: 6 }, (_, i) => 45 + i * 40).map((x) => (
        <line key={`frame-${x}`} x1={x} y1="64" x2={x} y2="76" strokeWidth="0.5" opacity="0.5" />
      ))}
      <line x1="20" y1="71" x2="300" y2="65" strokeWidth="0.5" opacity="0.6" />
      <path d="M164 40 L182 40" strokeWidth="0.75" />
      <path d="M167 60 L180 24" strokeWidth="0.6" opacity="0.6" />
      <path d="M164 88 L182 74" strokeWidth="0.6" opacity="0.6" />
      <path d="M188 25 L188 63" strokeWidth="0.5" opacity="0.5" />
      <path d="M184 100 L184 72" strokeWidth="0.5" opacity="0.5" />
      <line x1="322" y1="48" x2="330" y2="56" strokeWidth="0.6" opacity="0.6" />
      <circle cx="297" cy="46" r="9" strokeWidth="0.6" opacity="0.7" />
      <line x1="297" y1="37" x2="297" y2="55" strokeWidth="0.5" opacity="0.5" />
      <line x1="288" y1="46" x2="306" y2="46" strokeWidth="0.5" opacity="0.5" />
      <path d="M355 56 L358 60" strokeWidth="0.75" />
      <line x1="120" y1="76" x2="120" y2="82" strokeWidth="0.6" opacity="0.6" />
      <line x1="40" y1="74" x2="40" y2="79" strokeWidth="0.6" opacity="0.6" />
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
