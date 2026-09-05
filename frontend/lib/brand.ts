// Centralized brand identity. Every UI surface, generated document, and AI/
// report string that needs to name the company or the AI assistant should
// import from here rather than hardcoding a string — this is the single
// place a future logo, name, or tagline change gets made.
//
// LOCKED BRAND ARCHITECTURE (three identities, kept clearly separate):
//
//   COMPANY / PLATFORM  — KOTA'S AEROSPACE
//     The one company/platform brand. There is no separate "OS" product
//     name layered on top of it — do not reintroduce "KOTA AEROSPACE OS"
//     anywhere user-facing.
//
//   COMPLIANCE PRODUCT  — AeroComply
//     "Compliance & Airworthiness Intelligence." A real, named module
//     inside the platform (like Finance/Procurement), not renamed away.
//     Not centralized as a "module system" here — it's named directly at
//     its own call sites, the same way "Finance" and "Procurement" are.
//
//   AI ASSISTANT        — Lisa
//     The one AI identity used everywhere the single engine
//     (lib/mock/ai/engine.ts) surfaces an answer — console, audit actor,
//     report attribution, Finance/Procurement/Compliance AI call-outs.
//     Never "KOTA Aerospace AI", "AeroComply AI", or a per-module AI name.
//
// No logo has been finalized — these are text wordmarks only, deliberately
// kept as plain strings (not an <svg>/image component) so swapping in a
// real mark later touches this file only.

export const COMPANY_NAME = "KOTA'S AEROSPACE";
export const COMPANY_TAGLINE = "Building Intelligence for Aerospace";
export const COMPANY_DESCRIPTION = "Aerospace maintenance, compliance and operational intelligence.";

// Kept as an alias of COMPANY_NAME (not a distinct "OS" brand) so every
// existing call site that names the platform — sidebar wordmark, browser
// title, login, module eyebrows, report headers — updates from this one
// line without a second repo-wide sweep. Do not give this its own value.
export const PLATFORM_NAME = COMPANY_NAME;
export const PLATFORM_TAGLINE = COMPANY_DESCRIPTION;

export const AI_NAME = "Lisa";
export const AI_DESCRIPTION = "Aviation Intelligence Assistant";
export const AI_DISCLAIMER =
  `${AI_NAME} provides evidence-based intelligence from available system data. ${AI_NAME} does not replace approved maintenance data, regulatory requirements, inspection authority, or human authorization.`;

// Kept as an alias of AI_NAME for the same reason as PLATFORM_NAME above —
// every existing "Ask {PLATFORM_AI_NAME}" call site becomes "Ask Lisa"
// from this one line.
export const PLATFORM_AI_NAME = AI_NAME;

// Standard disclaimer footer attached to every AI answer (via
// lib/mock/ai/engine.ts's TRUST_FOOTER) and every AI-attributed report
// section. Kept as one exported constant so this — and any future
// rebrand — is a one-file change rather than a find-and-replace sweep.
export const AI_DEMO_DATA_FOOTER = `AI Prototype · Based on current ${COMPANY_NAME} demo data · Non-authoritative · Human review required.`;

export const MODULE_AEROCOMPLY_NAME = "AeroComply";
export const MODULE_AEROCOMPLY_TAGLINE = "Compliance & Airworthiness Intelligence";
export const COMPLIANCE_PRODUCT = MODULE_AEROCOMPLY_NAME;
export const COMPLIANCE_PRODUCT_FULL = `${MODULE_AEROCOMPLY_NAME} — ${MODULE_AEROCOMPLY_TAGLINE}`;
