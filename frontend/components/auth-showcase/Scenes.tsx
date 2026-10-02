import type { SVGProps } from "react";
import { HelicopterSilhouette, NarrowbodySilhouette } from "@/components/aircraft-visual/silhouettes";
import type { SceneId } from "./slides";

// Original vector illustrations for the showcase cards. They are drawn in
// currentColor line-art so one stroke colour themes the whole scene, and
// they are decorative (aria-hidden): the card text carries the meaning.

type P = SVGProps<SVGSVGElement>;

const base: P = {
  viewBox: "0 0 300 200",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.4,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
  focusable: false,
};

function Rotor({ cx, cy, rx = 30 }: { cx: number; cy: number; rx?: number }) {
  return (
    <g>
      <ellipse cx={cx} cy={cy} rx={rx} ry={rx * 0.22} opacity={0.55} />
      <ellipse cx={cx} cy={cy} rx={rx * 0.55} ry={rx * 0.12} opacity={0.3} />
      <circle cx={cx} cy={cy} r={2} fill="currentColor" stroke="none" />
    </g>
  );
}

function DroneScene(props: P) {
  return (
    <svg {...base} {...props}>
      {/* arms */}
      <path d="M150 110 L72 78 M150 110 L228 78 M150 110 L84 144 M150 110 L216 144" />
      {/* rotors */}
      <Rotor cx={68} cy={72} />
      <Rotor cx={232} cy={72} />
      <Rotor cx={78} cy={148} rx={34} />
      <Rotor cx={222} cy={148} rx={34} />
      {/* motor pods */}
      <path d="M68 72v6M232 72v6M78 148v6M222 148v6" />
      {/* body */}
      <path d="M124 100 Q150 86 176 100 L180 118 Q150 132 120 118 Z" />
      <path d="M134 104 Q150 98 166 104" opacity={0.6} />
      {/* gimbal + camera */}
      <path d="M150 124 v10" />
      <circle cx={150} cy={142} r={8} />
      <circle cx={150} cy={142} r={3} opacity={0.7} />
      {/* landing gear */}
      <path d="M130 120 L118 156 M170 120 L182 156 M110 156 H126 M174 156 H190" opacity={0.7} />
    </svg>
  );
}

function EvtolScene(props: P) {
  return (
    <svg {...base} {...props}>
      {/* wing + booms */}
      <path d="M40 104 H260" />
      <path d="M78 104 V84 M122 104 V84 M178 104 V84 M222 104 V84" opacity={0.8} />
      <Rotor cx={78} cy={78} rx={24} />
      <Rotor cx={122} cy={74} rx={24} />
      <Rotor cx={178} cy={74} rx={24} />
      <Rotor cx={222} cy={78} rx={24} />
      {/* cabin pod */}
      <path d="M116 104 Q150 84 184 104 Q196 128 150 140 Q104 128 116 104 Z" />
      <path d="M128 106 Q150 96 172 106" opacity={0.6} />
      {/* V-tail */}
      <path d="M150 140 L128 172 M150 140 L172 172" />
      <path d="M118 172 H138 M162 172 H182" opacity={0.7} />
      {/* battery pack mark */}
      <rect x={137} y={116} width={26} height={9} rx={2} opacity={0.7} />
      <path d="M163 119 v3" opacity={0.7} />
    </svg>
  );
}

function IntelligenceScene(props: P) {
  const nodes: Array<[number, number]> = [
    [60, 56],
    [236, 48],
    [252, 126],
    [58, 140],
    [150, 168],
  ];
  return (
    <svg {...base} {...props}>
      <ellipse cx={150} cy={100} rx={118} ry={62} opacity={0.35} />
      <ellipse cx={150} cy={100} rx={78} ry={40} opacity={0.5} />
      {nodes.map(([x, y]) => (
        <line key={`l-${x}-${y}`} x1={150} y1={100} x2={x} y2={y} opacity={0.45} />
      ))}
      {nodes.map(([x, y]) => (
        <g key={`n-${x}-${y}`}>
          <circle cx={x} cy={y} r={9} />
          <circle cx={x} cy={y} r={2.5} fill="currentColor" stroke="none" />
        </g>
      ))}
      <circle cx={150} cy={100} r={20} />
      <circle cx={150} cy={100} r={9} opacity={0.6} />
      <circle cx={150} cy={100} r={3} fill="currentColor" stroke="none" />
    </svg>
  );
}

export function ShowcaseScene({ id, className }: { id: SceneId; className?: string }) {
  switch (id) {
    case "drone":
      return <DroneScene className={className} />;
    case "evtol":
      return <EvtolScene className={className} />;
    case "intelligence":
      return <IntelligenceScene className={className} />;
    case "aircraft":
      return <NarrowbodySilhouette className={className} aria-hidden focusable={false} />;
    case "helicopter":
      return <HelicopterSilhouette className={className} aria-hidden focusable={false} />;
  }
}
