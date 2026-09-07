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

/**
 * Named regions on the aircraft silhouette that a specific ATA-100 chapter
 * can be honestly mapped onto for visual highlighting/fault markers.
 */
export type AircraftRegion = "engine" | "wing" | "landingGear" | "cockpit" | "tail" | "fuselage";

/**
 * ATA-100 chapter -> silhouette region mapping used to place highlight and
 * fault markers. Deliberately conservative: a chapter is included only when
 * it maps to one region a reasonable technician would point to on a side
 * silhouette. Chapters that are physically distributed across the airframe,
 * or ambiguous, return null rather than guess wrong.
 *
 *  Chapter(s)      System                          Region        Rationale
 *  --------------  ------------------------------  ------------  ------------------------------------------------
 *  70-79           Powerplant                       engine        Engine chapters map directly to the engine.
 *  32              Landing gear                      landingGear   One-to-one system-to-region match.
 *  57               Wings                            wing          One-to-one system-to-region match.
 *  27               Flight controls                  wing          Primary flight controls (ailerons/spoilers/
 *                                                                    flaps) are wing-mounted on every silhouette
 *                                                                    in this registry; elevator/rudder are a
 *                                                                    minority of ch.27 findings, so 'wing' is the
 *                                                                    more common/defensible single answer.
 *  55               Stabilizers                      tail          Horizontal/vertical stabilizer -> tail.
 *  53               Fuselage                          fuselage      One-to-one system-to-region match.
 *  23, 31, 34        Comms / indicating-recording /    cockpit       Flight-deck avionics and instrument
 *                    navigation                                      chapters are physically housed in/around
 *                                                                    the flight deck on every type here.
 *  21               Air conditioning                  cockpit       Cabin-altitude/pressurization controls and
 *                                                                    the primary flight-deck indications for
 *                                                                    ch.21 events sit at the flight deck; the
 *                                                                    ducting itself is distributed, so this is a
 *                                                                    judgment call documented here rather than a
 *                                                                    clean 1:1 match.
 *  24, 33, 49, ...   Electrical / lights / APU / etc.  null          Electrical power (24) and lighting (33) are
 *                                                                    distributed across the whole airframe; APU
 *                                                                    (49) sits in the tailcone on some types and
 *                                                                    is not represented on every silhouette here.
 *                                                                    Rather than guess, these — and any chapter
 *                                                                    not listed above — return null.
 */
const ATA_CHAPTER_TO_REGION: Record<string, AircraftRegion> = {
  "27": "wing",
  "32": "landingGear",
  "53": "fuselage",
  "55": "tail",
  "57": "wing",
  "70": "engine",
  "71": "engine",
  "72": "engine",
  "73": "engine",
  "74": "engine",
  "75": "engine",
  "76": "engine",
  "77": "engine",
  "78": "engine",
  "79": "engine",
  "21": "cockpit",
  "23": "cockpit",
  "31": "cockpit",
  "34": "cockpit",
};

export function ataChapterToRegion(ataChapter: string): AircraftRegion | null {
  return ATA_CHAPTER_TO_REGION[ataChapter] ?? null;
}
