// Centralized brand identity. Every UI surface, generated document, and AI/
// report string that needs to name the company/platform/module should
// import from here rather than hardcoding a string — this is the single
// place a future logo, tagline, or naming change gets made.
//
// Brand architecture:
//   COMPANY   — the corporate/legal identity (footers, "About", generated
//                business documents where a company name is appropriate).
//   PLATFORM  — the overall aerospace operating system (app shell, browser
//                title, login, AI console, cross-module report headers).
//   Module names (AeroComply, MRO/Finance/Procurement/etc.) are NOT
//   centralized here — they are real, distinct products inside the
//   platform and are named directly at their own call sites, the same way
//   "Finance" and "Procurement" already are.
//
// No logo has been finalized — COMPANY/PLATFORM are text wordmarks only,
// deliberately kept as plain strings (not an <svg>/image component) so
// swapping in a real mark later touches this file only.

export const COMPANY_NAME = "KOTA'S AEROSPACE";
export const COMPANY_TAGLINE = "Building Intelligence for Aerospace";

export const PLATFORM_NAME = "KOTA AEROSPACE OS";
export const PLATFORM_TAGLINE = "The Intelligent Operating System for Aerospace";

// The platform-wide AI actor/voice name, used anywhere the single AI engine
// (lib/mock/ai/engine.ts) identifies itself — in the console UI, audit
// actor fields, and generated-report attribution. This is NOT a second AI
// engine or a new identity per module; every module's AI answers still
// come from the one engine and carry this one name.
export const PLATFORM_AI_NAME = "KOTA Aerospace AI";

// Standard disclaimer, unchanged in meaning from the prototype's original
// "AeroComply demo data" footer — only the platform name changed. Kept as
// one exported constant (rather than a literal repeated at every call
// site) specifically so this rebrand — and any future one — is a
// one-file change.
export const AI_DEMO_DATA_FOOTER = `AI Prototype · Based on current ${PLATFORM_NAME} demo data · Non-authoritative · Human review required.`;

export const MODULE_AEROCOMPLY_NAME = "AeroComply";
export const MODULE_AEROCOMPLY_TAGLINE = "Compliance & Airworthiness Intelligence";
