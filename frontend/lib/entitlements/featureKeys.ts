// Single authoritative source of canonical feature keys and normalization on the frontend.

export const FEATURE_KEYS = {
  // Maintenance & Operations
  WORK_ORDER_MANAGEMENT: "work_order_management",
  INSPECTIONS_MANAGEMENT: "inspections_management",
  RELEASE_READINESS: "release_readiness",

  // Asset Fleets
  AIRCRAFT_FLEET_MANAGEMENT: "aircraft_fleet_management",
  DRONE_FLEET_MANAGEMENT: "drone_fleet_management",
  HELICOPTER_FLEET_MANAGEMENT: "helicopter_fleet_management",
  EVTOL_FLEET_MANAGEMENT: "evtol_fleet_management",
  FLIGHT_TELEMETRY: "flight_telemetry",
  BATTERY_ANALYTICS: "battery_analytics",

  // Procurement
  PROCUREMENT_MANAGEMENT: "procurement_management",

  // Compliance & Governance
  COMPLIANCE_MANAGEMENT: "compliance_management",
  ADVANCED_COMPLIANCE_INTELLIGENCE: "advanced_compliance_intelligence",
  AUDIT_LOGGING: "audit_logging",

  // AI & Intelligence
  LISA_AI_COPILOT: "lisa_ai_copilot",
  PREDICTIVE_MAINTENANCE: "predictive_maintenance",

  // Advanced Engineering & Sensors
  DIGITAL_TWIN: "digital_twin",
  HUMS: "hums",
  MRO_INTELLIGENCE: "mro_intelligence",
} as const;

export type FeatureKey = (typeof FEATURE_KEYS)[keyof typeof FEATURE_KEYS];

const FEATURE_KEY_ALIASES: Record<string, FeatureKey> = {
  // Digital Twin
  digital_twin: FEATURE_KEYS.DIGITAL_TWIN,
  digital_twin_beta: FEATURE_KEYS.DIGITAL_TWIN,
  digital_twin_module: FEATURE_KEYS.DIGITAL_TWIN,
  digitaltwin: FEATURE_KEYS.DIGITAL_TWIN,
  digital_twin_feature: FEATURE_KEYS.DIGITAL_TWIN,

  // HUMS
  hums: FEATURE_KEYS.HUMS,
  hums_module: FEATURE_KEYS.HUMS,
  hums_ai: FEATURE_KEYS.HUMS,
  hums_feature: FEATURE_KEYS.HUMS,
  hums_intelligence: FEATURE_KEYS.HUMS,

  // LISA
  lisa: FEATURE_KEYS.LISA_AI_COPILOT,
  lisa_ai: FEATURE_KEYS.LISA_AI_COPILOT,
  lisa_ai_copilot: FEATURE_KEYS.LISA_AI_COPILOT,
  lisa_copilot: FEATURE_KEYS.LISA_AI_COPILOT,
  ai_assistant: FEATURE_KEYS.LISA_AI_COPILOT,
  ai_copilot: FEATURE_KEYS.LISA_AI_COPILOT,

  // MRO Intelligence
  mro_intelligence: FEATURE_KEYS.MRO_INTELLIGENCE,
  mro_intelligence_module: FEATURE_KEYS.MRO_INTELLIGENCE,
  mro_intel: FEATURE_KEYS.MRO_INTELLIGENCE,

  // Work Orders
  work_order_management: FEATURE_KEYS.WORK_ORDER_MANAGEMENT,
  work_orders: FEATURE_KEYS.WORK_ORDER_MANAGEMENT,
  work_order: FEATURE_KEYS.WORK_ORDER_MANAGEMENT,

  // Drones
  drone_fleet_management: FEATURE_KEYS.DRONE_FLEET_MANAGEMENT,
  drone_operations: FEATURE_KEYS.DRONE_FLEET_MANAGEMENT,
  drones: FEATURE_KEYS.DRONE_FLEET_MANAGEMENT,

  // Telemetry & Batteries
  flight_telemetry: FEATURE_KEYS.FLIGHT_TELEMETRY,
  telemetry: FEATURE_KEYS.FLIGHT_TELEMETRY,
  battery_analytics: FEATURE_KEYS.BATTERY_ANALYTICS,
  battery_operations: FEATURE_KEYS.BATTERY_ANALYTICS,

  // Procurement
  procurement_management: FEATURE_KEYS.PROCUREMENT_MANAGEMENT,
  procurement: FEATURE_KEYS.PROCUREMENT_MANAGEMENT,
  procurement_operations: FEATURE_KEYS.PROCUREMENT_MANAGEMENT,

  // Inspections
  inspections_management: FEATURE_KEYS.INSPECTIONS_MANAGEMENT,
  inspections: FEATURE_KEYS.INSPECTIONS_MANAGEMENT,
  maintenance_inspections: FEATURE_KEYS.INSPECTIONS_MANAGEMENT,

  // Compliance
  compliance_management: FEATURE_KEYS.COMPLIANCE_MANAGEMENT,
  compliance: FEATURE_KEYS.COMPLIANCE_MANAGEMENT,
  compliance_reporting: FEATURE_KEYS.COMPLIANCE_MANAGEMENT,
  compliance_governance: FEATURE_KEYS.COMPLIANCE_MANAGEMENT,

  // Advanced Compliance Intelligence
  advanced_compliance_intelligence: FEATURE_KEYS.ADVANCED_COMPLIANCE_INTELLIGENCE,
  compliance_intelligence: FEATURE_KEYS.ADVANCED_COMPLIANCE_INTELLIGENCE,

  // Predictive Maintenance
  predictive_maintenance: FEATURE_KEYS.PREDICTIVE_MAINTENANCE,
  predictive_ops: FEATURE_KEYS.PREDICTIVE_MAINTENANCE,

  // Release Readiness & Audit
  release_readiness: FEATURE_KEYS.RELEASE_READINESS,
  audit_logging: FEATURE_KEYS.AUDIT_LOGGING,
  audit_trail: FEATURE_KEYS.AUDIT_LOGGING,
};

export function canonicalizeFeatureKey(key: string): string {
  const normalized = key.trim().toLowerCase();
  return FEATURE_KEY_ALIASES[normalized] ?? normalized;
}

export const normalizeFeatureKey = canonicalizeFeatureKey;

/**
 * Baseline capabilities that exist in no seeded plan but that every tenant has
 * always had. Mirrors backend `DEFAULT_ON_FEATURES`: enabled unless a plan row
 * or override explicitly disables them.
 */
export const DEFAULT_ON_FEATURES: ReadonlySet<string> = new Set([
  FEATURE_KEYS.AUDIT_LOGGING,
  FEATURE_KEYS.RELEASE_READINESS,
]);

export function hasFeatureKey(
  entitlements: Record<string, boolean> | null | undefined,
  featureKey: string
): boolean {
  if (!entitlements) return true;
  const canonical = canonicalizeFeatureKey(featureKey);
  const candidates = [
    entitlements[featureKey],
    entitlements[featureKey.toLowerCase()],
    entitlements[featureKey.toUpperCase()],
    entitlements[canonical],
    entitlements[canonical.toUpperCase()],
  ];
  if (candidates.some((v) => v === true)) return true;
  if (candidates.some((v) => v === false)) return false;
  return DEFAULT_ON_FEATURES.has(canonical);
}

/**
 * The backend publishes every effective feature under its canonical key AND its lookup aliases (upper-case, legacy
 * names) so `hasFeatureKey` can resolve any spelling. That map is for lookups only: anything that LISTS or COUNTS
 * features must go through this so each feature appears once. Entries are keyed by canonical key; if aliases ever
 * disagree the feature is reported disabled (fail closed).
 */
export function dedupeEffectiveFeatures(
  effective: Record<string, boolean> | null | undefined
): Array<[string, boolean]> {
  const byCanonical = new Map<string, boolean>();
  for (const [key, enabled] of Object.entries(effective ?? {})) {
    const canonical = canonicalizeFeatureKey(key);
    const prev = byCanonical.get(canonical);
    byCanonical.set(canonical, prev === undefined ? enabled : prev && enabled);
  }
  return Array.from(byCanonical.entries());
}
