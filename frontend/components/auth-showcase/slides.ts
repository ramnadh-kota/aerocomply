// Content for the sign-in aerospace showcase. Headlines, descriptions and
// CTAs are the approved product copy. `capabilities` lists only things the
// product has routes/modules for today; availability still depends on the
// organization's plan, which the panel states.
//
// `photo` is intentionally unset: no licensed photography ships with the
// repo. Set it to a local /images/... path to replace the vector scene; the
// card falls back to the scene if the image fails to load.

export type SceneId = "drone" | "aircraft" | "drone-fleet" | "helicopter" | "evtol" | "intelligence";

export interface ShowcaseSlide {
  id: SceneId;
  category: string;
  headline: string;
  description: string;
  cta: string;
  capabilities: string[];
  photo?: string;
  photoPosition?: string;
}

export const SHOWCASE_SLIDES: ShowcaseSlide[] = [
  {
    id: "drone",
    category: "Drone operations",
    headline: "Beyond Flight. Into Intelligence.",
    description: "Autonomous fleets, connected telemetry and predictive drone intelligence.",
    cta: "Discover Drone Intelligence",
    photo: "/images/showcase/drone-operations.avif",
    photoPosition: "center 35%",
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
    description: "Connected aircraft, fleet readiness and predictive maintenance.",
    cta: "Explore Aircraft Intelligence",
    photo: "/images/showcase/aircraft-runway.avif",
    photoPosition: "center 45%",
    capabilities: [
      "Aircraft registry, configuration and fleet health",
      "Maintenance planning, defects and work orders",
      "Inspections, evidence and compliance obligations",
      "Reports for readiness and audit",
    ],
  },
  {
    id: "drone-fleet",
    category: "Drone fleet operations",
    headline: "Connected Fleets. Complete Visibility.",
    description: "Fleet monitoring, coordinated operations and real-time aerospace intelligence.",
    cta: "Explore Fleet Intelligence",
    photo: "/images/showcase/drone-fleet-formation.webp",
    photoPosition: "center 40%",
    capabilities: [
      "Fleet-wide telemetry ingestion and live tracking",
      "Multi-drone coordination and airspace awareness",
      "Automated geofencing and real-time alert dispatch",
      "Consolidated fleet operational reporting",
    ],
  },
  {
    id: "helicopter",
    category: "Helicopters",
    headline: "Mission Ready. Always Connected.",
    description: "Advanced helicopter health, fleet monitoring and operational intelligence.",
    cta: "Discover Helicopter Intelligence",
    photo: "/images/showcase/helicopter-operations.jpg",
    photoPosition: "center 45%",
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
    description: "Electric aviation, advanced air mobility and intelligent fleet operations.",
    cta: "Explore Advanced Air Mobility",
    photo: "/images/showcase/evtol-demonstrator.jpg",
    photoPosition: "center 50%",
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
    description: "Connected aerospace assets, telemetry and AI-powered intelligence.",
    cta: "Explore Aerospace Intelligence",
    photo: "/images/showcase/aerospace-intelligence.jpg",
    photoPosition: "center 40%",
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
