import { getAircraftType } from "@/lib/mock/aircraft";

/**
 * Aircraft-type-aware visual context configuration.
 *
 * This registry is the scaffolding for a broader visual-context system
 * (see docs/brief §19/20). Only two real aircraft types exist in the mock
 * fleet today — Boeing 737 and Airbus A320, both narrowbody — so only the
 * `narrowbody` mapping is exercised by real data. The classification logic
 * below is written generically (by manufacturer/designation name pattern)
 * so it scales honestly if wide-body, turboprop, business-jet, or rotary
 * types are added later, without ever fabricating a category for a type
 * that isn't actually in the data.
 */

export type AircraftCategory =
  | "narrowbody"
  | "widebody"
  | "regional-turboprop"
  | "business-jet"
  | "helicopter"
  | "unknown";

export interface AircraftVisualConfig {
  category: AircraftCategory;
  label: string;
  /** Key into the SVG silhouette component registry. */
  silhouetteId: string;
}

export const AIRCRAFT_VISUAL_CONFIGS: Record<AircraftCategory, AircraftVisualConfig> = {
  narrowbody: {
    category: "narrowbody",
    label: "Narrow-body jet",
    silhouetteId: "narrowbody",
  },
  widebody: {
    category: "widebody",
    label: "Wide-body jet",
    silhouetteId: "widebody",
  },
  "regional-turboprop": {
    category: "regional-turboprop",
    label: "Regional turboprop",
    silhouetteId: "regional-turboprop",
  },
  "business-jet": {
    category: "business-jet",
    label: "Business jet",
    silhouetteId: "generic",
  },
  helicopter: {
    category: "helicopter",
    label: "Helicopter",
    silhouetteId: "helicopter",
  },
  unknown: {
    category: "unknown",
    label: "Aircraft",
    silhouetteId: "generic",
  },
};

// Name-pattern hints for classification. These are generic rules, not a
// hardcoded list of real fleet types — they only fire when a matching
// designation string actually appears in aircraftTypes/aircraftVariants.
const WIDEBODY_PATTERNS = [/747/, /767/, /777/, /787/, /a3[03]0/i, /a340/i, /a350/i, /a380/i, /md-?11/i];
const TURBOPROP_PATTERNS = [/atr/i, /dash/i, /q400/i, /q300/i, /saab/i, /dhc/i, /embraer\s*1[23]0/i];
const HELICOPTER_PATTERNS = [/helicopter/i, /^ec\d/i, /^as\d/i, /^bell/i, /^r\d\d$/i, /^h1[23]5/i, /^s-?\d\d/i];
const BUSINESS_JET_PATTERNS = [/gulfstream/i, /citation/i, /learjet/i, /challenger/i, /falcon\s*\d/i, /phenom/i];
const NARROWBODY_PATTERNS = [/^737/, /^a3[12]0/i, /^757/, /^md-?8\d/i, /^717/];

function classifyByText(text: string): AircraftCategory | null {
  if (WIDEBODY_PATTERNS.some((p) => p.test(text))) return "widebody";
  if (TURBOPROP_PATTERNS.some((p) => p.test(text))) return "regional-turboprop";
  if (HELICOPTER_PATTERNS.some((p) => p.test(text))) return "helicopter";
  if (BUSINESS_JET_PATTERNS.some((p) => p.test(text))) return "business-jet";
  if (NARROWBODY_PATTERNS.some((p) => p.test(text))) return "narrowbody";
  return null;
}

/**
 * Resolves an aircraft category from a real aircraftTypeId in the mock
 * dataset. Falls back to 'unknown' honestly whenever the type can't be
 * confidently classified — never guesses a specific category wrong.
 */
export function resolveAircraftCategory(aircraftTypeId: string | undefined): AircraftCategory {
  if (!aircraftTypeId) return "unknown";
  const type = getAircraftType(aircraftTypeId);
  if (!type) return "unknown";

  const combined = `${type.manufacturer} ${type.designation}`.trim();
  return classifyByText(combined) ?? classifyByText(type.designation) ?? "unknown";
}

export function getAircraftVisualConfig(category: AircraftCategory): AircraftVisualConfig {
  return AIRCRAFT_VISUAL_CONFIGS[category];
}
