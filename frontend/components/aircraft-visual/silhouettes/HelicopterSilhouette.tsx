import type { SVGProps } from "react";

/**
 * Simple technical-line-art side-profile silhouette of a helicopter: main
 * rotor disc, cabin/tail boom, tail rotor.
 */
export function HelicopterSilhouette(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 300 110" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" {...props}>
      <line x1="30" y1="34" x2="230" y2="34" />
      <line x1="130" y1="34" x2="130" y2="40" />
      <path d="M100 40 Q160 38 160 40 Q160 62 128 70 Q90 70 78 56 Q76 46 100 40 Z" />
      <path d="M160 55 L250 60 L250 66 L164 64 Z" />
      <path d="M244 44 L250 60 L256 44" />
      <line x1="100" y1="70" x2="94" y2="80" />
      <line x1="140" y1="70" x2="146" y2="80" />
    </svg>
  );
}
