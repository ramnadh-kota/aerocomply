// Content for the sign-in aerospace showcase. Headlines, descriptions and
// CTAs are the approved product copy. `capabilities` lists only things the
// product has routes/modules for today; availability still depends on the
// organization's plan, which the panel states.
//
// `photo` is intentionally unset: no licensed photography ships with the
// repo. Set it to a local /images/... path to replace the vector scene; the
// card falls back to the scene if the image fails to load.

export type SceneId = "drone" | "aircraft" | "helicopter" | "evtol" | "intelligence";

export interface ShowcaseSlide {
  id: SceneId;
  category: string;
  headline: string;
  description: string;
  cta: string;
  capabilities: string[];
  photo?: string;
}

export const SHOWCASE_SLIDES: ShowcaseSlide[] = [
  {
    id: "drone",
    category: "Autonomous drones",
    headline: "Beyond Flight. Into Intelligence.",
    description:
      "Explore autonomous fleets, live telemetry, mission awareness and predictive drone health.",
    cta: "Discover Drone Intelligence",
    capabilities: [
      "Drone registry with per-asset detail records",
      "Drone Ops: live map, telemetry, health and alerts",
      "Missions, maintenance and findings in one place",
      "Lisa, the assistant, answers from your own data",
    ],
  },
  {
    id: "aircraft",
    category: "Aircraft",
    headline: "Precision Engineered. Intelligence Driven.",
    description:
      "Experience connected aircraft, fleet readiness, predictive maintenance and intelligent operational visibility.",
    cta: "Explore Aircraft Intelligence",
    capabilities: [
      "Aircraft registry, configuration and fleet health",
      "Maintenance planning, defects and work orders",
      "Inspections, evidence and compliance obligations",
      "Reports for readiness and audit",
    ],
  },
  {
    id: "helicopter",
    category: "Helicopters",
    headline: "Mission Ready. Always Connected.",
    description:
      "Discover helicopter health monitoring, component intelligence, fleet readiness and advanced maintenance operations.",
    cta: "Discover Helicopter Intelligence",
    capabilities: [
      "Helicopter asset records and detail pages",
      "Component and engine tracking",
      "Maintenance and compliance workflows",
    ],
  },
  {
    id: "evtol",
    category: "eVTOL and advanced air mobility",
    headline: "A New Dimension of Aerial Mobility.",
    description:
      "Explore electric aviation, advanced air mobility, battery health and intelligent fleet operations.",
    cta: "Explore Advanced Air Mobility",
    capabilities: [
      "eVTOL asset records and detail pages",
      "Battery component maintenance records",
      "Shared fleet, maintenance and compliance tooling",
    ],
  },
  {
    id: "intelligence",
    category: "Aerospace intelligence",
    headline: "One Intelligence Layer. Every Asset.",
    description:
      "Connect aircraft, drones, helicopters, telemetry, HUMS and AI-powered operational intelligence.",
    cta: "Explore Aerospace Intelligence",
    capabilities: [
      "Fleet intelligence across asset types",
      "HUMS limits and exceedance tracking",
      "Telemetry ingestion with freshness awareness",
      "Human review stays in the loop for every recommendation",
    ],
  },
];

/** Positive modulo, so a negative or oversized carousel offset still wraps. */
export function wrapOffset(offset: number, loopWidth: number): number {
  if (!(loopWidth > 0)) return 0;
  return ((offset % loopWidth) + loopWidth) % loopWidth;
}

/** Exponential approach used for eased pause/resume and manual glides. */
export function easeToward(current: number, target: number, dtSeconds: number, rate: number): number {
  const k = Math.min(1, Math.max(0, dtSeconds * rate));
  return current + (target - current) * k;
}
