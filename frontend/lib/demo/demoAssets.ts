import {
  AssetResponse,
  AssetConfigurationResponse,
  AssetComponentResponse,
  AssetOperationsResponse,
  AssetMaintenanceResponse,
  AssetInspectionsResponse,
  AssetEvidenceResponse,
  AssetFindingsResponse,
  AssetComplianceResponse,
  AssetReadinessResponse,
  AssetHistoryResponse,
  AssetDomainContextResponse,
} from "@/lib/api/assets";

export const DEMO_ASSETS: AssetResponse[] = [
  {
    id: "a1000000-0000-0000-0000-000000000001",
    organization_id: "demo-org-id",
    asset_type: "AIRCRAFT",
    manufacturer: "Boeing",
    model: "737-800",
    serial_number: "MSN-30124",
    registration: "N737AA",
    status: "IN_SERVICE",
    acquired_at: "2021-03-15T00:00:00Z",
    retired_at: null,
    created_at: "2021-03-15T00:00:00Z",
  },
  {
    id: "a1000000-0000-0000-0000-000000000002",
    organization_id: "demo-org-id",
    asset_type: "DRONE",
    manufacturer: "DJI",
    model: "Matrice 300 RTK",
    serial_number: "1581F1Z882001",
    registration: "DRN-M300-01",
    status: "IN_SERVICE",
    acquired_at: "2023-01-10T00:00:00Z",
    retired_at: null,
    created_at: "2023-01-10T00:00:00Z",
  },
  {
    id: "a1000000-0000-0000-0000-000000000003",
    organization_id: "demo-org-id",
    asset_type: "HELICOPTER",
    manufacturer: "Bell Helicopter",
    model: "429 GlobalRanger",
    serial_number: "BH-57019",
    registration: "N429HL",
    status: "IN_SERVICE",
    acquired_at: "2022-06-20T00:00:00Z",
    retired_at: null,
    created_at: "2022-06-20T00:00:00Z",
  },
  {
    id: "a1000000-0000-0000-0000-000000000004",
    organization_id: "demo-org-id",
    asset_type: "EVTOL",
    manufacturer: "Joby Aviation",
    model: "S4 Pre-Production",
    serial_number: "JBY-004",
    registration: "N401EV",
    status: "ACTIVE",
    acquired_at: "2024-02-01T00:00:00Z",
    retired_at: null,
    created_at: "2024-02-01T00:00:00Z",
  },
  {
    id: "a1000000-0000-0000-0000-000000000005",
    organization_id: "demo-org-id",
    asset_type: "DRONE",
    manufacturer: "Skydio",
    model: "X2D Enterprise",
    serial_number: "SK2-99014",
    registration: "DRN-SK2-04",
    status: "MAINTENANCE",
    acquired_at: "2023-08-14T00:00:00Z",
    retired_at: null,
    created_at: "2023-08-14T00:00:00Z",
  },
];

export function getDemoAssetDetail(assetId: string): AssetResponse | null {
  const staticFound = DEMO_ASSETS.find((a) => a.id === assetId);
  if (staticFound) return staticFound;
  if (typeof globalThis !== "undefined" && typeof (globalThis as any).__aerocomply_demo_get_asset__ === "function") {
    const memFound = (globalThis as any).__aerocomply_demo_get_asset__(assetId);
    if (memFound) return memFound;
  }
  if (typeof window !== "undefined") {
    try {
      const raw = window.sessionStorage.getItem("aerocomply_demo_store_v1");
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed.assets)) {
          const found = parsed.assets.find((a: any) => a.id === assetId);
          if (found) return found;
        }
      }
    } catch {
      // ignore
    }
  }
  return null;
}

export function getDemoConfiguration(assetId: string): AssetConfigurationResponse {
  const asset = getDemoAssetDetail(assetId) || DEMO_ASSETS[0];

  if (asset.asset_type === "DRONE") {
    return {
      asset_id: asset.id,
      asset_type: "DRONE",
      airframe_spec: {
        max_takeoff_weight_kg: 9.0,
        battery_bays: 2,
        ip_rating: "IP45",
      },
      slots: [
        {
          slot_name: "Flight Controller",
          component_type: "FLIGHT_CONTROLLER",
          is_occupied: true,
          component: {
            id: "c1000000-0000-0000-0000-000000000001",
            organization_id: "demo-org-id",
            asset_id: asset.id,
            component_type: "FLIGHT_CONTROLLER",
            name: "DJI A3 Pro Autopilot Module",
            serial_number: "FC-99124",
            manufacturer: "DJI",
            model: "A3-PRO",
            status: "INSTALLED",
            installed_at: "2023-01-10T10:00:00Z",
            created_at: "2023-01-10T10:00:00Z",
          },
        },
        {
          slot_name: "Propulsion Motor (Left Forward)",
          component_type: "MOTOR",
          is_occupied: true,
          component: {
            id: "c1000000-0000-0000-0000-000000000002",
            organization_id: "demo-org-id",
            asset_id: asset.id,
            component_type: "MOTOR",
            name: "Brushless Motor CW",
            serial_number: "MTR-10291",
            manufacturer: "DJI",
            model: "M300-BL",
            status: "INSTALLED",
            installed_at: "2023-01-10T10:00:00Z",
            created_at: "2023-01-10T10:00:00Z",
          },
        },
        {
          slot_name: "Sensor / Camera Payload",
          component_type: "CAMERA",
          is_occupied: true,
          component: {
            id: "c1000000-0000-0000-0000-000000000003",
            organization_id: "demo-org-id",
            asset_id: asset.id,
            component_type: "CAMERA",
            name: "Zenmuse H20T Thermal Payload",
            serial_number: "H20T-44021",
            manufacturer: "DJI",
            model: "H20T",
            status: "INSTALLED",
            installed_at: "2023-01-15T14:00:00Z",
            created_at: "2023-01-15T14:00:00Z",
          },
        },
        {
          slot_name: "Navigation GNSS/GPS",
          component_type: "GPS",
          is_occupied: true,
          component: null,
        },
      ],
      total_components_installed: 3,
    };
  }

  if (asset.asset_type === "HELICOPTER") {
    return {
      asset_id: asset.id,
      asset_type: "HELICOPTER",
      airframe_spec: {
        rotor_system: "4-blade bearingless rotor",
        max_gross_weight_lbs: 7500,
        turbine_count: 2,
      },
      slots: [
        {
          slot_name: "Turboshaft Engine #1 (Left)",
          component_type: "ENGINE",
          is_occupied: true,
          component: {
            id: "c2000000-0000-0000-0000-000000000001",
            organization_id: "demo-org-id",
            asset_id: asset.id,
            component_type: "ENGINE",
            name: "Pratt & Whitney PW207D1",
            serial_number: "PCE-BL0491",
            manufacturer: "Pratt & Whitney Canada",
            model: "PW207D1",
            status: "INSTALLED",
            installed_at: "2022-06-20T10:00:00Z",
            created_at: "2022-06-20T10:00:00Z",
          },
        },
        {
          slot_name: "Turboshaft Engine #2 (Right)",
          component_type: "ENGINE",
          is_occupied: true,
          component: {
            id: "c2000000-0000-0000-0000-000000000002",
            organization_id: "demo-org-id",
            asset_id: asset.id,
            component_type: "ENGINE",
            name: "Pratt & Whitney PW207D1",
            serial_number: "PCE-BL0492",
            manufacturer: "Pratt & Whitney Canada",
            model: "PW207D1",
            status: "INSTALLED",
            installed_at: "2022-06-20T10:00:00Z",
            created_at: "2022-06-20T10:00:00Z",
          },
        },
        {
          slot_name: "Main Rotor Transmission",
          component_type: "TRANSMISSION",
          is_occupied: true,
          component: {
            id: "c2000000-0000-0000-0000-000000000003",
            organization_id: "demo-org-id",
            asset_id: asset.id,
            component_type: "TRANSMISSION",
            name: "Main Gearbox 429 Assembly",
            serial_number: "MGB-9014",
            manufacturer: "Bell Helicopter",
            model: "429-MGB",
            status: "INSTALLED",
            installed_at: "2022-06-20T10:00:00Z",
            created_at: "2022-06-20T10:00:00Z",
          },
        },
        {
          slot_name: "Tail Rotor Assembly",
          component_type: "ROTOR",
          is_occupied: true,
          component: null,
        },
      ],
      total_components_installed: 3,
    };
  }

  // Default: AIRCRAFT (Fixed-Wing)
  return {
    asset_id: asset.id,
    asset_type: "AIRCRAFT",
    airframe_spec: {
      msn: "30124",
      wingspan_ft: 117.4,
      max_fuel_capacity_lbs: 46063,
    },
    slots: [
      {
        slot_name: "Turbofan Engine #1 (Left Wing)",
        component_type: "ENGINE",
        is_occupied: true,
        component: {
          id: "c3000000-0000-0000-0000-000000000001",
          organization_id: "demo-org-id",
          asset_id: asset.id,
          component_type: "ENGINE",
          name: "CFM56-7B26 High Bypass Turbofan",
          serial_number: "CFM-89104",
          manufacturer: "CFM International",
          model: "CFM56-7B26",
          status: "INSTALLED",
          installed_at: "2021-03-15T12:00:00Z",
          created_at: "2021-03-15T12:00:00Z",
        },
      },
      {
        slot_name: "Turbofan Engine #2 (Right Wing)",
        component_type: "ENGINE",
        is_occupied: true,
        component: {
          id: "c3000000-0000-0000-0000-000000000002",
          organization_id: "demo-org-id",
          asset_id: asset.id,
          component_type: "ENGINE",
          name: "CFM56-7B26 High Bypass Turbofan",
          serial_number: "CFM-89105",
          manufacturer: "CFM International",
          model: "CFM56-7B26",
          status: "INSTALLED",
          installed_at: "2021-03-15T12:00:00Z",
          created_at: "2021-03-15T12:00:00Z",
        },
      },
      {
        slot_name: "Auxiliary Power Unit (APU)",
        component_type: "APU",
        is_occupied: true,
        component: {
          id: "c3000000-0000-0000-0000-000000000003",
          organization_id: "demo-org-id",
          asset_id: asset.id,
          component_type: "APU",
          name: "Honeywell 131-9B APU",
          serial_number: "APU-131-502",
          manufacturer: "Honeywell Aerospace",
          model: "131-9B",
          status: "INSTALLED",
          installed_at: "2021-03-15T12:00:00Z",
          created_at: "2021-03-15T12:00:00Z",
        },
      },
      {
        slot_name: "Flight Management System (FMS)",
        component_type: "AVIONICS",
        is_occupied: true,
        component: null,
      },
    ],
    total_components_installed: 3,
  };
}

export function getDemoOperations(assetId: string): AssetOperationsResponse {
  const asset = getDemoAssetDetail(assetId) || DEMO_ASSETS[0];
  const isDrone = asset.asset_type === "DRONE";

  return {
    asset_id: asset.id,
    utilization: {
      asset_id: asset.id,
      asset_type: asset.asset_type,
      total_flight_hours: isDrone ? 142.5 : 8420.0,
      total_minutes: isDrone ? 8550 : 505200,
      total_cycles: isDrone ? 312 : 4210,
      total_flights: isDrone ? 312 : 4210,
      total_landings: isDrone ? 312 : 4210,
      metrics: [
        {
          metric_key: "TOTAL_FLIGHT_HOURS",
          metric_label: "Total Flight Hours (TTAF)",
          value: isDrone ? 142.5 : 8420.0,
          unit: "hours",
          source: "FLIGHT",
          is_metered: true,
        },
        {
          metric_key: "TOTAL_CYCLES",
          metric_label: "Airframe Cycles",
          value: isDrone ? 312 : 4210,
          unit: "cycles",
          source: "FLIGHT",
          is_metered: true,
        },
        {
          metric_key: "TOTAL_LANDINGS",
          metric_label: "Total Landing Touchdowns",
          value: isDrone ? 312 : 4210,
          unit: "landings",
          source: "FLIGHT",
          is_metered: true,
        },
      ],
    },
    recent_flights: [
      {
        id: "f1000000-0000-0000-0000-000000000001",
        organization_id: "demo-org-id",
        asset_id: asset.id,
        mission_id: null,
        flown_at: "2026-09-21T14:30:00Z",
        duration_minutes: isDrone ? 35 : 180,
        cycles: 1,
        pilot_user_id: null,
        notes: isDrone ? "Infrastructure inspection sector Bravo" : "KDEN to KSEA scheduled revenue leg",
        created_at: "2026-09-21T18:00:00Z",
      },
      {
        id: "f1000000-0000-0000-0000-000000000002",
        organization_id: "demo-org-id",
        asset_id: asset.id,
        mission_id: null,
        flown_at: "2026-09-20T09:15:00Z",
        duration_minutes: isDrone ? 28 : 210,
        cycles: 1,
        pilot_user_id: null,
        notes: isDrone ? "Automated perimeter survey grid" : "KORD to KDEN scheduled revenue leg",
        created_at: "2026-09-20T13:30:00Z",
      },
    ],
    active_missions: isDrone
      ? [
          {
            id: "m1000000-0000-0000-0000-000000000001",
            title: "Perimeter Automated Patrol Beta",
            status: "IN_PROGRESS",
            created_at: "2026-09-23T08:00:00Z",
          },
        ]
      : [],
  };
}

export function getDemoMaintenance(assetId: string): AssetMaintenanceResponse {
  const asset = getDemoAssetDetail(assetId) || DEMO_ASSETS[0];
  const isDrone = asset.asset_type === "DRONE";

  return {
    asset_id: asset.id,
    has_overdue: false,
    due_items: [
      {
        id: "maint-req-01",
        title: isDrone ? "Propeller 100-Hour Hub Inspection" : "A-Check 500 Flight Hours Interval",
        interval_hours: isDrone ? 100 : 500,
        next_due_hours: isDrone ? 150 : 8500,
        status: "UPCOMING",
      },
    ],
    accomplishments: [
      {
        id: "acc-01",
        title: isDrone ? "Motor Bearing Lubrication & Calibration" : "Engine #1 Borescope Inspection",
        completed_at: "2026-08-15T11:00:00Z",
        technician: "Lead Aviation Technician",
      },
    ],
    open_work_orders: [
      {
        id: "wo-01",
        title: isDrone ? "Quarterly Avionics Sensor Recalibration" : "Avionics Software Patch AD-2026-04",
        status: "OPEN",
        priority: "MEDIUM",
        created_at: "2026-09-18T10:00:00Z",
      },
    ],
  };
}

export function getDemoInspections(assetId: string): AssetInspectionsResponse {
  return {
    asset_id: assetId,
    total: 3,
    completed: 2,
    pending: 1,
    inspections: [
      {
        id: "insp-01",
        title: "Pre-Flight Airframe Structural Check",
        status: "COMPLETED",
        inspector: "Flight Operations Lead",
        signed_at: "2026-09-21T13:45:00Z",
      },
      {
        id: "insp-02",
        title: "Rotor / Propeller Torque Verification",
        status: "COMPLETED",
        inspector: "Senior Airframe Mechanic",
        signed_at: "2026-09-10T16:20:00Z",
      },
      {
        id: "insp-03",
        title: "Emergency Transponder / ELT Functional Test",
        status: "PENDING",
        inspector: "Unassigned",
        signed_at: null,
      },
    ],
  };
}

export function getDemoEvidence(assetId: string): AssetEvidenceResponse {
  return {
    asset_id: assetId,
    total: 3,
    accepted_count: 2,
    pending_count: 1,
    evidence_items: [
      {
        id: "ev-01",
        title: "FAA Standard Airworthiness Certificate Form 8100-2",
        file_name: "airworthiness_cert_2026.pdf",
        status: "ACCEPTED",
        reviewed_by: "Chief Compliance Officer",
        uploaded_at: "2026-01-12T09:30:00Z",
      },
      {
        id: "ev-02",
        title: "Weight and Balance Schedule Sign-off",
        file_name: "weight_balance_rev4.pdf",
        status: "ACCEPTED",
        reviewed_by: "Chief Inspector",
        uploaded_at: "2026-05-18T14:15:00Z",
      },
      {
        id: "ev-03",
        title: "Propeller Hub Dye Penetrant NDT Report",
        file_name: "ndt_penetrant_log.pdf",
        status: "PENDING_REVIEW",
        reviewed_by: null,
        uploaded_at: "2026-09-22T17:00:00Z",
      },
    ],
  };
}

export function getDemoFindings(assetId: string): AssetFindingsResponse {
  return {
    asset_id: assetId,
    total: 2,
    open_count: 1,
    closed_count: 1,
    findings: [
      {
        id: "fnd-01",
        title: "Minor paint erosion on leading edge slat #2",
        severity: "LOW",
        status: "OPEN",
        discovered_at: "2026-09-15T11:00:00Z",
      },
      {
        id: "fnd-02",
        title: "Navigation light fixture housing fastener loose",
        severity: "MEDIUM",
        status: "CLOSED",
        discovered_at: "2026-08-02T14:00:00Z",
      },
    ],
  };
}

export function getDemoCompliance(assetId: string): AssetComplianceResponse {
  return {
    asset_id: assetId,
    overall_status: "COMPLIANT",
    compliant_count: 4,
    non_compliant_count: 0,
    assessments: [
      {
        id: "comp-01",
        regulatory_code: "14 CFR Part 91 / 43",
        title: "Annual Maintenance Records and Logbook Inspection",
        determination: "COMPLIANT",
        assessed_at: "2026-07-10T12:00:00Z",
        assessed_by: "Designated Airworthiness Representative",
      },
      {
        id: "comp-02",
        regulatory_code: "AD 2026-08-11",
        title: "Airworthiness Directive: Flight Control Actuator Inspection",
        determination: "COMPLIANT",
        assessed_at: "2026-08-20T15:30:00Z",
        assessed_by: "Chief Inspector",
      },
    ],
  };
}

export function getDemoReadiness(assetId: string): AssetReadinessResponse {
  const asset = getDemoAssetDetail(assetId) || DEMO_ASSETS[0];
  const isGrounded = asset.status === "GROUNDED" || asset.status === "MAINTENANCE";

  return {
    asset_id: asset.id,
    overall_status: isGrounded ? "AT_RISK" : "READY",
    evaluated_at: new Date().toISOString(),
    disclaimer:
      "Operational readiness evaluation only. Does not constitute an electronic Release to Service (RTS) signature.",
    dimensions: [
      {
        dimension: "OPERATIONAL",
        status: isGrounded ? "BLOCKED" : "READY",
        summary: isGrounded
          ? "Airframe status is currently MAINTENANCE or GROUNDED."
          : "Airframe is active and cleared for flight planning.",
        blockers: isGrounded ? ["Asset in maintenance disposition"] : [],
      },
      {
        dimension: "MAINTENANCE",
        status: "READY",
        summary: "No mandatory scheduled maintenance items overdue.",
        blockers: [],
      },
      {
        dimension: "COMPLIANCE",
        status: "READY",
        summary: "Airworthiness directives and mandatory regulations assessed as compliant.",
        blockers: [],
      },
      {
        dimension: "DEPLOYMENT",
        status: isGrounded ? "BLOCKED" : "READY",
        summary: isGrounded
          ? "Asset cannot be deployed on active operations."
          : "All operational prerequisites and pilot assignments cleared.",
        blockers: isGrounded ? ["Pending work order sign-off"] : [],
      },
      {
        dimension: "RELEASE",
        status: isGrounded ? "BLOCKED" : "READY",
        summary: isGrounded
          ? "Open work orders must be released before operational return."
          : "Required task verification gates and evidence uploads accepted.",
        blockers: isGrounded ? ["Unclosed maintenance work order"] : [],
      },
    ],
  };
}

export function getDemoHistory(assetId: string): AssetHistoryResponse {
  return {
    asset_id: assetId,
    total: 4,
    events: [
      {
        event_id: "evt-01",
        event_type: "asset.flight_recorded",
        occurred_at: "2026-09-21T18:00:00Z",
        title: "Flight Logged",
        description: "Recorded flight duration 180 min, 1 cycle",
        actor: "Flight Operations",
        entity_type: "Flight",
        entity_id: "f1000000-0000-0000-0000-000000000001",
        metadata: {},
      },
      {
        event_id: "evt-02",
        event_type: "asset.component.installed",
        occurred_at: "2026-08-15T11:00:00Z",
        title: "Component Installed",
        description: "Installed Honeywell 131-9B APU (APU-131-502)",
        actor: "Lead Avionics Specialist",
        entity_type: "Component",
        entity_id: "c3000000-0000-0000-0000-000000000003",
        metadata: {},
      },
      {
        event_id: "evt-03",
        event_type: "asset.compliance.assessed",
        occurred_at: "2026-08-20T15:30:00Z",
        title: "Compliance Assessed",
        description: "Assessed AD 2026-08-11: Determination COMPLIANT",
        actor: "Chief Inspector",
        entity_type: "ComplianceAssessment",
        entity_id: "comp-02",
        metadata: {},
      },
      {
        event_id: "evt-04",
        event_type: "asset.created",
        occurred_at: "2021-03-15T00:00:00Z",
        title: "Asset Registered",
        description: "Airframe registered into tenant fleet registry",
        actor: "System Administrator",
        entity_type: "Asset",
        entity_id: assetId,
        metadata: {},
      },
    ],
  };
}

export function getDemoDomainContext(assetId: string): AssetDomainContextResponse {
  const asset = getDemoAssetDetail(assetId) || DEMO_ASSETS[0];
  const readiness = getDemoReadiness(assetId);
  const configuration = getDemoConfiguration(assetId);
  const operations = getDemoOperations(assetId);
  const compliance = getDemoCompliance(assetId);

  return {
    identity: asset,
    operational_status: asset.status === "MAINTENANCE" ? "GROUNDED" : "READY",
    lifecycle_status: asset.status,
    readiness,
    configuration,
    utilization: operations.utilization,
    compliance,
    open_work_orders_count: 1,
    open_findings_count: 1,
    overdue_maintenance_count: 0,
    last_flight_at: operations.recent_flights[0]?.flown_at || null,
  };
}
