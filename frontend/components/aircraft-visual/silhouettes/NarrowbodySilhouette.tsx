import type { SVGProps } from "react";

/**
 * Simple, technical-line-art side-profile silhouette of a narrow-body jet
 * (e.g. 737 / A320 class): low, swept wing, single aisle fuselage, swept
 * tail. Single-color, uses currentColor so it themes with the page.
 */
export function NarrowbodySilhouette(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 400 120" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" {...props}>
      <path d="M20 68 L300 62 Q330 61 355 55 L358 60 Q332 68 300 70 L120 76 Q80 78 40 74 Z" />
      <path d="M150 66 L190 20 L200 20 L182 66 Z" />
      <path d="M150 70 L188 108 L198 108 L180 70 Z" />
      <path d="M300 63 L330 40 L336 41 L316 65 Z" />
      <path d="M296 62 Q292 45 296 30 L302 30 Q304 46 302 62 Z" />
      <line x1="60" y1="76" x2="60" y2="82" />
      <line x1="270" y1="72" x2="270" y2="80" />
    </svg>
  );
}
