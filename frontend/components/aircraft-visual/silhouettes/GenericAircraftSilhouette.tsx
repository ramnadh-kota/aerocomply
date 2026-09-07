import type { SVGProps } from "react";

/**
 * Fallback technical-line-art side-profile silhouette used when the
 * aircraft category can't be confidently classified. Deliberately generic
 * (simple fixed-wing outline) — never claims a specific real aircraft type.
 */
export function GenericAircraftSilhouette(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 360 110" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" {...props}>
      <path d="M18 60 L270 56 Q296 55 316 50 L318 55 Q298 62 270 64 L110 68 Q72 70 36 66 Z" />
      <path d="M140 58 L176 22 L186 22 L166 58 Z" />
      <path d="M140 62 L174 96 L184 96 L164 62 Z" />
      <path d="M268 57 L292 38 L298 39 L280 59 Z" />
      <line x1="55" y1="66" x2="55" y2="72" />
      <line x1="240" y1="63" x2="240" y2="70" />
    </svg>
  );
}
