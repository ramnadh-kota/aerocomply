import type { Component, ComponentInstallation, ComponentInstance } from "./types";

// MOCK DATA. Component/ComponentInstance/ComponentInstallation three-way split
// per ADR-009 — "Part" and "Component" are treated as one concept; only
// components with requiresSerialization=true ever get a ComponentInstance.

export const components: Component[] = [
  { id: "comp-hp442", partNumber: "HP-442", description: "Hydraulic Pump", manufacturer: "Parker Aerospace", requiresSerialization: true },
  { id: "comp-abc123", partNumber: "ABC-123", description: "Fan Disk Assembly", manufacturer: "CFM International", requiresSerialization: true },
  { id: "comp-fcu220", partNumber: "FCU-220", description: "Fuel Control Unit", manufacturer: "Honeywell", requiresSerialization: true },
  { id: "comp-avn115", partNumber: "AVN-115", description: "Flight Management Computer", manufacturer: "Collins Aerospace", requiresSerialization: true },
  { id: "comp-act330", partNumber: "ACT-330", description: "Flap Actuator", manufacturer: "Moog", requiresSerialization: true },
  { id: "comp-val089", partNumber: "VAL-089", description: "Bleed Air Valve", manufacturer: "Eaton", requiresSerialization: true },
  { id: "comp-brk210", partNumber: "BRK-210", description: "Brake Assembly", manufacturer: "Safran Landing Systems", requiresSerialization: true },
  { id: "comp-gen305", partNumber: "GEN-305", description: "Integrated Drive Generator", manufacturer: "Hamilton Sundstrand", requiresSerialization: true },
  { id: "comp-apu410", partNumber: "APU-410", description: "Auxiliary Power Unit", manufacturer: "Honeywell", requiresSerialization: true },
  { id: "comp-pmp512", partNumber: "PMP-512", description: "Fuel Boost Pump", manufacturer: "Parker Aerospace", requiresSerialization: true },
  { id: "comp-sen077", partNumber: "SEN-077", description: "Angle of Attack Sensor", manufacturer: "Collins Aerospace", requiresSerialization: true },
  { id: "comp-oxy140", partNumber: "OXY-140", description: "Oxygen Generator", manufacturer: "B/E Aerospace", requiresSerialization: true },
  { id: "comp-smk008", partNumber: "SMK-008", description: "Smoke Detector Unit", manufacturer: "Kidde Aerospace", requiresSerialization: true },
  { id: "comp-tcas225", partNumber: "TCAS-225", description: "Traffic Collision Avoidance Computer", manufacturer: "Honeywell", requiresSerialization: true },
  { id: "comp-wgt060", partNumber: "WGT-060", description: "Weight-on-Wheels Sensor", manufacturer: "Safran", requiresSerialization: true },
  // Non-serialized (batch/lot-tracked) parts — deliberately without ComponentInstance rows.
  { id: "comp-bolt001", partNumber: "MS20470AD4-5", description: "Structural Rivet (lot)", manufacturer: "Standard Hardware", requiresSerialization: false },
  { id: "comp-seal014", partNumber: "SEAL-014", description: "Hydraulic Seal Kit", manufacturer: "Parker Aerospace", requiresSerialization: false },
  { id: "comp-gask033", partNumber: "GASK-033", description: "Engine Gasket Set", manufacturer: "CFM International", requiresSerialization: false },
  { id: "comp-filt090", partNumber: "FILT-090", description: "Hydraulic Filter Element", manufacturer: "Pall Aerospace", requiresSerialization: false },
  { id: "comp-clmp101", partNumber: "CLMP-101", description: "Tube Clamp Assembly", manufacturer: "Standard Hardware", requiresSerialization: false },
  { id: "comp-wire205", partNumber: "WIRE-205", description: "Wiring Harness Segment", manufacturer: "TE Connectivity", requiresSerialization: false },
  { id: "comp-lamp312", partNumber: "LAMP-312", description: "Navigation Light Assembly", manufacturer: "Whelen Aerospace", requiresSerialization: false },
  { id: "comp-tire419", partNumber: "TIRE-419", description: "Main Landing Gear Tire", manufacturer: "Michelin Aircraft", requiresSerialization: false },
  { id: "comp-brg527", partNumber: "BRG-527", description: "Bearing Assembly", manufacturer: "SKF Aerospace", requiresSerialization: false },
  { id: "comp-fltr634", partNumber: "FLTR-634", description: "Cabin Air Filter", manufacturer: "Pall Aerospace", requiresSerialization: false },
];

const serializedComponentIds = components.filter((c) => c.requiresSerialization).map((c) => c.id);

export const componentInstances: ComponentInstance[] = [
  { id: "ci-hp001", componentId: "comp-hp442", serialNumber: "HP001" },
  { id: "ci-fcu044", componentId: "comp-fcu220", serialNumber: "FCU044" },
  { id: "ci-avn210", componentId: "comp-avn115", serialNumber: "AVN210" },
  { id: "ci-act077", componentId: "comp-act330", serialNumber: "ACT077" },
  { id: "ci-val512", componentId: "comp-val089", serialNumber: "VAL512" },
  { id: "ci-brk203", componentId: "comp-brk210", serialNumber: "BRK203" },
  { id: "ci-gen114", componentId: "comp-gen305", serialNumber: "GEN114" },
  { id: "ci-apu301", componentId: "comp-apu410", serialNumber: "APU301" },
  { id: "ci-pmp408", componentId: "comp-pmp512", serialNumber: "PMP408" },
  { id: "ci-sen019", componentId: "comp-sen077", serialNumber: "SEN019" },
  { id: "ci-oxy220", componentId: "comp-oxy140", serialNumber: "OXY220" },
  { id: "ci-smk006", componentId: "comp-smk008", serialNumber: "SMK006" },
  { id: "ci-tcas118", componentId: "comp-tcas225", serialNumber: "TCAS118" },
  { id: "ci-wgt044", componentId: "comp-wgt060", serialNumber: "WGT044" },
  // ABC-123 (Fan Disk Assembly) is deliberately NOT installed/tracked on VT-ABC
  // (ac-1) — this is what makes the AD-2026-001 assessment for VT-ABC return
  // UNKNOWN/INSUFFICIENT_DATA rather than a guessed APPLICABLE/NOT_APPLICABLE
  // (see docs/ontology/DOMAIN_INVARIANTS.md #23). It IS tracked on ac-3.
  { id: "ci-abc901", componentId: "comp-abc123", serialNumber: "ABC901" },
];

export const componentInstallations: ComponentInstallation[] = [
  { id: "cinst-1", componentInstanceId: "ci-hp001", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-1", engineParentId: null, position: "HYD_SYS_1", installedAt: "2025-11-03", removedAt: null },
  { id: "cinst-2", componentInstanceId: "ci-avn210", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-1", engineParentId: null, position: "FMC_1", installedAt: "2024-01-01", removedAt: null },
  { id: "cinst-3", componentInstanceId: "ci-brk203", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-1", engineParentId: null, position: "MLG_LH", installedAt: "2024-01-01", removedAt: null },
  { id: "cinst-4", componentInstanceId: "ci-wgt044", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-1", engineParentId: null, position: "MLG_LH", installedAt: "2024-01-01", removedAt: null },
  { id: "cinst-5", componentInstanceId: "ci-fcu044", parentAssetType: "ENGINE", aircraftParentId: null, engineParentId: "eng-100781", position: "FCU", installedAt: "2026-02-11", removedAt: null },
  { id: "cinst-6", componentInstanceId: "ci-act077", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-2", engineParentId: null, position: "FLAP_RH", installedAt: "2023-06-15", removedAt: null },
  { id: "cinst-7", componentInstanceId: "ci-val512", parentAssetType: "ENGINE", aircraftParentId: null, engineParentId: "eng-200001", position: "BLEED_VALVE", installedAt: "2023-06-15", removedAt: null },
  { id: "cinst-8", componentInstanceId: "ci-gen114", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-3", engineParentId: null, position: "IDG_1", installedAt: "2022-09-10", removedAt: null },
  { id: "cinst-9", componentInstanceId: "ci-apu301", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-3", engineParentId: null, position: "APU", installedAt: "2022-09-10", removedAt: "2025-08-01" },
  { id: "cinst-10", componentInstanceId: "ci-abc901", parentAssetType: "ENGINE", aircraftParentId: null, engineParentId: "eng-200002", position: "FAN_DISK", installedAt: "2022-09-10", removedAt: null },
  { id: "cinst-11", componentInstanceId: "ci-pmp408", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-4", engineParentId: null, position: "FUEL_BOOST_1", installedAt: "2021-03-22", removedAt: null },
  { id: "cinst-12", componentInstanceId: "ci-sen019", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-4", engineParentId: null, position: "AOA_LH", installedAt: "2021-03-22", removedAt: null },
  { id: "cinst-13", componentInstanceId: "ci-oxy220", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-5", engineParentId: null, position: "OXY_GEN_1", installedAt: "2020-11-05", removedAt: null },
  { id: "cinst-14", componentInstanceId: "ci-smk006", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-5", engineParentId: null, position: "CARGO_SMOKE_1", installedAt: "2020-11-05", removedAt: null },
  { id: "cinst-15", componentInstanceId: "ci-tcas118", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-6", engineParentId: null, position: "TCAS", installedAt: "2019-07-18", removedAt: null },
  // Deliberate data-quality gap used in "Attention Required" on the dashboard:
  // a removal with no corresponding new installation recorded yet.
  { id: "cinst-16", componentInstanceId: "ci-apu301", parentAssetType: "AIRCRAFT", aircraftParentId: "ac-7", engineParentId: null, position: "APU", installedAt: "2023-02-14", removedAt: "2026-01-20" },
];

export function getComponentById(id: string): Component | undefined {
  return components.find((c) => c.id === id);
}

export function getComponentInstance(id: string): ComponentInstance | undefined {
  return componentInstances.find((ci) => ci.id === id);
}

export function componentForInstance(instanceId: string): Component | undefined {
  const instance = componentInstances.find((ci) => ci.id === instanceId);
  return instance ? components.find((c) => c.id === instance.componentId) : undefined;
}

export function componentInstallationsForAircraft(aircraftId: string): ComponentInstallation[] {
  return componentInstallations.filter((i) => i.aircraftParentId === aircraftId);
}

export function componentInstallationsForEngine(engineId: string): ComponentInstallation[] {
  return componentInstallations.filter((i) => i.engineParentId === engineId);
}

export function installationsForComponentInstance(instanceId: string): ComponentInstallation[] {
  return componentInstallations.filter((i) => i.componentInstanceId === instanceId).sort((a, b) => a.installedAt.localeCompare(b.installedAt));
}

/** True if a serialized component instance is currently (or as-of a date) installed on a given aircraft. */
export function isComponentPresentOnAircraft(componentId: string, aircraftId: string, isoDate: string): boolean {
  const instanceIds = componentInstances.filter((ci) => ci.componentId === componentId).map((ci) => ci.id);
  return componentInstallations.some(
    (i) =>
      instanceIds.includes(i.componentInstanceId) &&
      i.aircraftParentId === aircraftId &&
      i.installedAt <= isoDate &&
      (i.removedAt === null || i.removedAt > isoDate)
  );
}

/** True if we have ANY installation record at all for this component on this aircraft, ever
 * (used to distinguish "known absent" from "never tracked" — see invariant #23). */
export function hasAnyInstallationRecordForComponentOnAircraft(componentId: string, aircraftId: string): boolean {
  const instanceIds = componentInstances.filter((ci) => ci.componentId === componentId).map((ci) => ci.id);
  return componentInstallations.some((i) => instanceIds.includes(i.componentInstanceId) && i.aircraftParentId === aircraftId);
}

export { serializedComponentIds };
