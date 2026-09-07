import type { SVGProps } from "react";

/**
 * Simple technical-line-art side-profile silhouette of a wide-body jet
 * (e.g. 777 / A350 class): longer, deeper fuselage, larger swept wing with
 * underslung engine, twin-aisle proportions implied by fuselage depth.
 */
export function WidebodySilhouette(props: SVGProps<SVGSVGElement>) {
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
    </svg>
  );
}
