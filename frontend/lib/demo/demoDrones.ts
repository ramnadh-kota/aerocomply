// Centralized, deterministic synthetic dataset for the KOTA Aerospace Demo Environment.
// Exclusively used when sessionType === "DEMO" (DEMO_ORG_ID).
// Real sessions (sessionType === "REAL") communicate directly with backend APIs.

import type {
  AssetLifecycleEventResponse,
  BatteryInstallationResponse,
  BatteryResponse,
  ComponentInstallationResponse,
  ComponentResponse,
  DeploymentReadinessResponse,
  DroneResponse,
  FlightResponse,
  MaintenanceDueItem,
  UtilizationResponse,
} from "@/lib/api/drones";
import type { BackendFinding } from "@/lib/api/findings";
import { DEMO_ORG_ID } from "@/lib/auth/SessionContext";

export interface DemoMission {
  id: string;
  mission_code: string;
  asset_id: string;
  pilot_name: string;
  purpose: string;
  status: "PLANNED" | "PRE_FLIGHT" | "AUTHORIZED" | "IN_PROGRESS" | "COMPLETED" | "CLOSED";
  operating_area: string;
  planned_start: string;
  planned_end: string;
  preflight_checks: {
    airframe_condition: "PASS" | "FAIL" | "NOT_CHECKED";
    battery_state: "PASS" | "FAIL" | "NOT_CHECKED";
    maintenance_status: "PASS" | "FAIL" | "NOT_CHECKED";
    inspection_clearance: "PASS" | "FAIL" | "NOT_CHECKED";
    open_findings: "PASS" | "FAIL" | "NOT_CHECKED";
    pilot_qualification: "PASS" | "FAIL" | "NOT_CHECKED";
    airspace_authorization: "PASS" | "FAIL" | "NOT_CHECKED";
  };
  overall_preflight: "READY" | "BLOCKED";
  blockers: string[];
  outcome: string | null;
}

// -----------------------------------------------------------------------------
// 1. Synthetic Drone Airframes (6 Drones with realistic operational mix)
// -----------------------------------------------------------------------------
export const DEMO_DRONES: DroneResponse[] = [
  {
    id: "drn-kota-001",
    organization_id: DEMO_ORG_ID,
    asset_type: "DRONE",
    registration: "KOTA-D001",
    manufacturer: "SkyRanger Systems",
    model: "SkyRanger X4 Enterprise",
    serial_number: "SRX4-2025-0811",
    status: "ACTIVE",
    facility_id: "fac-hub-north",
    created_at: "2026-01-15T08:00:00Z",
  },
  {
    id: "drn-kota-002",
    organization_id: DEMO_ORG_ID,
    asset_type: "DRONE",
    registration: "KOTA-D002",
    manufacturer: "AeroScout Dynamics",
    model: "AeroScout Pro Survey",
    serial_number: "ASP-2025-0422",
    status: "ACTIVE",
    facility_id: "fac-hub-north",
    created_at: "2026-02-01T09:30:00Z",
  },
  {
    id: "drn-kota-003",
    organization_id: DEMO_ORG_ID,
    asset_type: "DRONE",
    registration: "KOTA-D003",
    manufacturer: "Guardian Avionics",
    model: "Guardian V2 Heavy Lift",
    serial_number: "GV2-2025-1104",
    status: "ACTIVE",
    facility_id: "fac-hub-east",
    created_at: "2026-02-15T11:00:00Z",
  },
  {
    id: "drn-kota-004",
    organization_id: DEMO_ORG_ID,
    asset_type: "DRONE",
    registration: "KOTA-D004",
    manufacturer: "Falcon Wing Aerospace",
    model: "Falcon Wing VTOL-12",
    serial_number: "FW12-2025-0955",
    status: "ACTIVE",
    facility_id: "fac-hub-east",
    created_at: "2026-03-01T14:15:00Z",
  },
  {
    id: "drn-kota-005",
    organization_id: DEMO_ORG_ID,
    asset_type: "DRONE",
    registration: "KOTA-D005",
    manufacturer: "HoverTech Industrial",
    model: "HoverTech 500 Infrastructure",
    serial_number: "HT500-2025-0199",
    status: "GROUNDED",
    facility_id: "fac-hub-south",
    created_at: "2026-03-10T10:00:00Z",
  },
  {
    id: "drn-kota-006",
    organization_id: DEMO_ORG_ID,
    asset_type: "DRONE",
    registration: "KOTA-D006",
    manufacturer: "SkyRanger Systems",
    model: "SkyRanger X4 Enterprise",
    serial_number: "SRX4-2025-0902",
    status: "ACTIVE",
    facility_id: "fac-hub-south",
    created_at: "2026-03-18T16:20:00Z",
  },
];

// -----------------------------------------------------------------------------
// 2. Synthetic Batteries
// -----------------------------------------------------------------------------
export const DEMO_BATTERIES: BatteryResponse[] = [
  {
    id: "bat-kota-001",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-001",
    serial_number: "BAT-D001-A",
    manufacturer: "VoltaAero",
    model: "LiPo 6S 22000mAh",
    capacity_mah: 22000,
    voltage: 24.8,
    cycle_count: 42,
    health_percent: 98,
    status: "GOOD",
    installed_at: "2026-01-20T10:00:00Z",
    notes: "Nominal cell balance (<0.02V delta), routine charge profile.",
    created_at: "2026-01-15T08:00:00Z",
  },
  {
    id: "bat-kota-002",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-002",
    serial_number: "BAT-D002-A",
    manufacturer: "VoltaAero",
    model: "LiPo 6S 16000mAh",
    capacity_mah: 16000,
    voltage: 24.6,
    cycle_count: 48,
    health_percent: 96,
    status: "GOOD",
    installed_at: "2026-02-05T09:00:00Z",
    notes: "Nominal cell balance (<0.02V delta), routine charge profile.",
    created_at: "2026-02-01T09:30:00Z",
  },
  {
    id: "bat-kota-003",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-003",
    serial_number: "BAT-D003-A",
    manufacturer: "PowerCore Aero",
    model: "SolidState 12S 30000mAh",
    capacity_mah: 30000,
    voltage: 49.2,
    cycle_count: 18,
    health_percent: 99,
    status: "GOOD",
    installed_at: "2026-02-18T12:00:00Z",
    notes: "Operating within optimal temperature and current parameters.",
    created_at: "2026-02-15T11:00:00Z",
  },
  {
    id: "bat-kota-004",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-004",
    serial_number: "BAT-D004-A",
    manufacturer: "VoltaAero",
    model: "LiPo 8S 24000mAh",
    capacity_mah: 24000,
    voltage: 32.4,
    cycle_count: 145,
    health_percent: 88,
    status: "MONITOR",
    installed_at: "2026-03-05T08:30:00Z",
    notes: "Minor cycle wear, scheduled for 150-cycle capacity discharge test.",
    created_at: "2026-03-01T14:15:00Z",
  },
  {
    id: "bat-kota-005",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-005",
    serial_number: "BAT-D005-A",
    manufacturer: "PowerCore Aero",
    model: "LiPo 6S 22000mAh",
    capacity_mah: 22000,
    voltage: 20.4,
    cycle_count: 312,
    health_percent: 64,
    status: "CRITICAL",
    installed_at: "2026-03-12T11:00:00Z",
    notes: "High internal resistance on Cell 3, voltage sag below threshold.",
    created_at: "2026-03-10T10:00:00Z",
  },
  {
    id: "bat-kota-006",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-006",
    serial_number: "BAT-D006-A",
    manufacturer: "VoltaAero",
    model: "LiPo 6S 22000mAh",
    capacity_mah: 22000,
    voltage: 24.2,
    cycle_count: 98,
    health_percent: 90,
    status: "SERVICE_DUE",
    installed_at: "2026-03-20T14:00:00Z",
    notes: "100-cycle calibration discharge due.",
    created_at: "2026-03-18T16:20:00Z",
  },
];

// -----------------------------------------------------------------------------
// 3. Synthetic Installed Components
// -----------------------------------------------------------------------------
export const DEMO_COMPONENTS: ComponentResponse[] = [
  {
    id: "cmp-kota-001",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-001",
    component_type: "PROPULSION_MOTOR",
    name: "T-Motor U8 II KV100 Set",
    serial_number: "TM-U8-9941",
    manufacturer: "T-Motor",
    model: "U8 II KV100",
    status: "SERVICEABLE",
    created_at: "2026-01-15T08:00:00Z",
  },
  {
    id: "cmp-kota-002",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-001",
    component_type: "PAYLOAD_CAMERA",
    name: "FLIR Vue Pro R 640 Thermal Gimbal",
    serial_number: "FLIR-640-1029",
    manufacturer: "Teledyne FLIR",
    model: "Vue Pro R",
    status: "SERVICEABLE",
    created_at: "2026-01-16T09:00:00Z",
  },
  {
    id: "cmp-kota-003",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-002",
    component_type: "AVIONICS_FLIGHT_CONTROLLER",
    name: "Cube Orange+ Autopilot",
    serial_number: "CUBE-OR-8812",
    manufacturer: "Cubepilot",
    model: "Cube Orange+ with ADS-B",
    status: "SERVICEABLE",
    created_at: "2026-02-01T09:30:00Z",
  },
  {
    id: "cmp-kota-004",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-003",
    component_type: "PAYLOAD_LIDAR",
    name: "Velodyne Puck Lite LiDAR",
    serial_number: "VELO-PL-3301",
    manufacturer: "Velodyne",
    model: "VLP-16 Puck LITE",
    status: "SERVICEABLE",
    created_at: "2026-02-15T11:00:00Z",
  },
  {
    id: "cmp-kota-005",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-004",
    component_type: "NAVIGATION_GNSS",
    name: "Here3+ Precision RTK GNSS",
    serial_number: "HERE3-RTK-5542",
    manufacturer: "Hex Technology",
    model: "Here3+ RTK Dual",
    status: "SERVICEABLE",
    created_at: "2026-03-01T14:15:00Z",
  },
  {
    id: "cmp-kota-006",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-005",
    component_type: "PROPULSION_MOTOR",
    name: "KDE Direct 7215XF Motor Set",
    serial_number: "KDE-7215-081",
    manufacturer: "KDE Direct",
    model: "7215XF-135",
    status: "INSPECT_REQUIRED",
    created_at: "2026-03-10T10:00:00Z",
  },
  {
    id: "cmp-kota-007",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-006",
    component_type: "ESC_SPEED_CONTROLLER",
    name: "T-Motor Flame 80A ESC Set",
    serial_number: "TM-FLAME-4410",
    manufacturer: "T-Motor",
    model: "Flame 80A 12S",
    status: "SERVICEABLE",
    created_at: "2026-03-18T16:20:00Z",
  },
];

// -----------------------------------------------------------------------------
// 4. Synthetic Flight Logs
// -----------------------------------------------------------------------------
export const DEMO_FLIGHTS: FlightResponse[] = [
  {
    id: "flt-d01-01",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-001",
    flown_at: "2026-03-20T10:15:00Z",
    duration_minutes: 42,
    cycles: 1,
    pilot_user_id: "00000000-0000-0000-0000-000000000002",
    notes: "Transmission line corridor inspection. Autonomous waypoint grid, max altitude 85m AGL. Normal landing.",
    created_at: "2026-03-20T11:00:00Z",
  },
  {
    id: "flt-d01-02",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-001",
    flown_at: "2026-03-21T14:30:00Z",
    duration_minutes: 38,
    cycles: 1,
    pilot_user_id: "00000000-0000-0000-0000-000000000002",
    notes: "Substation perimeter surveillance. Thermal signature collection. Battery delta <0.01V.",
    created_at: "2026-03-21T15:15:00Z",
  },
  {
    id: "flt-d02-01",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-002",
    flown_at: "2026-03-18T09:00:00Z",
    duration_minutes: 25,
    cycles: 1,
    pilot_user_id: "00000000-0000-0000-0000-000000000002",
    notes: "Photogrammetry survey sector B. Normal operation and landing.",
    created_at: "2026-03-18T09:30:00Z",
  },
  {
    id: "flt-d03-01",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-003",
    flown_at: "2026-03-22T08:00:00Z",
    duration_minutes: 55,
    cycles: 1,
    pilot_user_id: "00000000-0000-0000-0000-000000000002",
    notes: "LiDAR terrain mapping forest reserve. High crosswind stability test passed.",
    created_at: "2026-03-22T09:00:00Z",
  },
  {
    id: "flt-d04-01",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-004",
    flown_at: "2026-03-15T13:00:00Z",
    duration_minutes: 65,
    cycles: 1,
    pilot_user_id: "00000000-0000-0000-0000-000000000002",
    notes: "Long-range pipeline inspection corridor 4. Routine survey flight.",
    created_at: "2026-03-15T14:10:00Z",
  },
  {
    id: "flt-d05-01",
    organization_id: DEMO_ORG_ID,
    asset_id: "drn-kota-005",
    flown_at: "2026-03-19T11:45:00Z",
    duration_minutes: 20,
    cycles: 1,
    pilot_user_id: "00000000-0000-0000-0000-000000000002",
    notes: "Industrial rooftop inspection. Propeller chip observed during post-flight walkaround. Grounded.",
    created_at: "2026-03-19T12:15:00Z",
  },
];

// -----------------------------------------------------------------------------
// 5. Synthetic Findings (Linked to Drones)
// -----------------------------------------------------------------------------
export const DEMO_FINDINGS: BackendFinding[] = [
  {
    id: "fnd-kota-d005-01",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-005",
    component_id: "cmp-kota-006",
    inspection_requirement_id: null,
    work_order_id: null,
    task_id: null,
    title: "Propeller Blade #3 Leading Edge Scuff and Micro-Fracture",
    description: "Post-flight inspection revealed 3mm chip and hairline stress fracture on CW carbon prop #3. Exceeds allowable limits per AMM section 61-10.",
    severity: "MAJOR",
    status: "OPEN",
    discovered_at: "2026-03-19T12:00:00Z",
    discovered_by_user_id: "00000000-0000-0000-0000-000000000002",
    responsible_user_id: "00000000-0000-0000-0000-000000000002",
    created_at: "2026-03-19T12:15:00Z",
    updated_at: "2026-03-19T12:15:00Z",
    dispositions: [],
  },
  {
    id: "fnd-kota-d003-01",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-003",
    component_id: "cmp-kota-004",
    inspection_requirement_id: null,
    work_order_id: null,
    task_id: null,
    title: "LiDAR Optical Window Micro-Scratch & Degraded Signal Return",
    description: "Telemetry log indicates 15% drop in laser return intensity. Visual inspection confirms 2mm optical window abrasion.",
    severity: "MAJOR",
    status: "OPEN",
    discovered_at: "2026-03-22T09:15:00Z",
    discovered_by_user_id: "00000000-0000-0000-0000-000000000002",
    responsible_user_id: "00000000-0000-0000-0000-000000000002",
    created_at: "2026-03-22T09:30:00Z",
    updated_at: "2026-03-22T09:30:00Z",
    dispositions: [],
  },
  {
    id: "fnd-kota-d001-01",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-001",
    component_id: "cmp-kota-002",
    inspection_requirement_id: null,
    work_order_id: null,
    task_id: null,
    title: "Thermal Gimbal Pitch Axis Cable Tension",
    description: "Minor tension observed on video feed ribbon during 90 degree pitch down. Calibrated and cleared.",
    severity: "MINOR",
    status: "CLOSED",
    discovered_at: "2026-03-10T08:00:00Z",
    discovered_by_user_id: "00000000-0000-0000-0000-000000000002",
    responsible_user_id: "00000000-0000-0000-0000-000000000002",
    created_at: "2026-03-10T08:15:00Z",
    updated_at: "2026-03-10T11:00:00Z",
    dispositions: [
      {
        id: "dsp-001-1",
        organization_id: DEMO_ORG_ID,
        finding_id: "fnd-kota-d001-01",
        disposition_type: "NO_ACTION_REQUIRED",
        corrective_action: "Harness adjusted and full 360 gimbal movement verified.",
        evidence_id: null,
        closed_at: "2026-03-10T11:00:00Z",
        closed_by_user_id: "00000000-0000-0000-0000-000000000002",
        created_at: "2026-03-10T09:00:00Z",
      },
    ],
  },
];

// -----------------------------------------------------------------------------
// 6. Synthetic Maintenance Due Items
// -----------------------------------------------------------------------------
export const DEMO_MAINTENANCE_DUE: Record<string, MaintenanceDueItem[]> = {
  "drn-kota-001": [
    {
      requirement: {
        id: "mreq-001",
        organization_id: DEMO_ORG_ID,
        description: "50-Hour Airframe & Motor Bearing Inspection",
        ata_chapter: "ATA 05",
        interval_type: "FLIGHT_HOURS",
        fh_interval: 50,
        fc_interval: null,
        calendar_interval_days: null,
        task_reference: "AMM-DRN-05-10",
      },
      aircraft_id: null,
      asset_id: "drn-kota-001",
      battery_id: null,
      component_id: null,
      last_accomplished_at: "2026-02-10T00:00:00Z",
      due_status: "NOT_DUE",
      due_date: null,
      reason: "Current usage: 18.5 / 50.0 FH (31.5 FH remaining)",
      current_usage: 18.5,
      remaining_usage: 31.5,
      lifetime_usage: 68.5,
    },
    {
      requirement: {
        id: "mreq-002",
        organization_id: DEMO_ORG_ID,
        description: "Annual Avionics & Barometric Altimeter Calibration",
        ata_chapter: "ATA 34",
        interval_type: "CALENDAR",
        fh_interval: null,
        fc_interval: null,
        calendar_interval_days: 365,
        task_reference: "AMM-DRN-34-20",
      },
      aircraft_id: null,
      asset_id: "drn-kota-001",
      battery_id: null,
      component_id: null,
      last_accomplished_at: "2026-01-15T00:00:00Z",
      due_status: "NOT_DUE",
      due_date: "2027-01-15T00:00:00Z",
      reason: "Annual calibration valid until Jan 2027",
      current_usage: 67,
      remaining_usage: 298,
      lifetime_usage: 67,
    },
  ],
  "drn-kota-003": [
    {
      requirement: {
        id: "mreq-003",
        organization_id: DEMO_ORG_ID,
        description: "50-Hour Motor Bearing & Thrust Test",
        ata_chapter: "ATA 72",
        interval_type: "FLIGHT_HOURS",
        fh_interval: 50,
        fc_interval: null,
        calendar_interval_days: null,
        task_reference: "AMM-GV2-72-01",
      },
      aircraft_id: null,
      asset_id: "drn-kota-003",
      battery_id: null,
      component_id: null,
      last_accomplished_at: null,
      due_status: "OVERDUE",
      due_date: null,
      reason: "Current usage 51.5 FH exceeds 50.0 FH interval (+1.5 FH overdue)",
      current_usage: 51.5,
      remaining_usage: -1.5,
      lifetime_usage: 51.5,
    },
  ],
  "drn-kota-006": [
    {
      requirement: {
        id: "mreq-004",
        organization_id: DEMO_ORG_ID,
        description: "100-Cycle Battery Capacity Verification",
        ata_chapter: "ATA 24",
        interval_type: "BATTERY_CYCLES",
        fh_interval: null,
        fc_interval: null,
        calendar_interval_days: null,
        task_reference: "AMM-BAT-24-05",
      },
      aircraft_id: null,
      asset_id: "drn-kota-006",
      battery_id: "bat-kota-006",
      component_id: null,
      last_accomplished_at: null,
      due_status: "DUE_SOON",
      due_date: null,
      reason: "Cycle count 98 / 100 cycles (2 cycles remaining)",
      current_usage: 98,
      remaining_usage: 2,
      lifetime_usage: 98,
    },
  ],
};

// -----------------------------------------------------------------------------
// 7. Synthetic Missions (Operational Coordination Layer)
// -----------------------------------------------------------------------------
export const DEMO_MISSIONS: DemoMission[] = [
  {
    id: "msn-kota-2026-00421",
    mission_code: "MSN-2026-00421",
    asset_id: "drn-kota-001",
    pilot_name: "Alex Rivera (Lead Pilot)",
    purpose: "Transmission Line Corridor Alpha Inspection",
    status: "AUTHORIZED",
    operating_area: "Sector 4 North Corridor (45.21N, 73.12W)",
    planned_start: "2026-03-24T09:00:00Z",
    planned_end: "2026-03-24T11:30:00Z",
    preflight_checks: {
      airframe_condition: "PASS",
      battery_state: "PASS",
      maintenance_status: "PASS",
      inspection_clearance: "PASS",
      open_findings: "PASS",
      pilot_qualification: "PASS",
      airspace_authorization: "PASS",
    },
    overall_preflight: "READY",
    blockers: [],
    outcome: null,
  },
  {
    id: "msn-kota-2026-00422",
    mission_code: "MSN-2026-00422",
    asset_id: "drn-kota-002",
    pilot_name: "Alex Rivera",
    purpose: "Quarry Photogrammetry Volume Audit",
    status: "PRE_FLIGHT",
    operating_area: "Apex Industrial Quarry (44.88N, 73.50W)",
    planned_start: "2026-03-24T13:00:00Z",
    planned_end: "2026-03-24T15:00:00Z",
    preflight_checks: {
      airframe_condition: "PASS",
      battery_state: "FAIL",
      maintenance_status: "PASS",
      inspection_clearance: "PASS",
      open_findings: "FAIL",
      pilot_qualification: "PASS",
      airspace_authorization: "PASS",
    },
    overall_preflight: "BLOCKED",
    blockers: [
      "Battery BAT-D002-A is in CRITICAL state (voltage collapse under load)",
      "Unresolved CRITICAL finding on battery pack",
    ],
    outcome: null,
  },
  {
    id: "msn-kota-2026-00423",
    mission_code: "MSN-2026-00423",
    asset_id: "drn-kota-003",
    pilot_name: "Alex Rivera",
    purpose: "Forestry LiDAR Canopy Density Mapping",
    status: "COMPLETED",
    operating_area: "East Pine Ridge Reserve (45.60N, 72.90W)",
    planned_start: "2026-03-22T08:00:00Z",
    planned_end: "2026-03-22T09:30:00Z",
    preflight_checks: {
      airframe_condition: "PASS",
      battery_state: "PASS",
      maintenance_status: "PASS",
      inspection_clearance: "PASS",
      open_findings: "PASS",
      pilot_qualification: "PASS",
      airspace_authorization: "PASS",
    },
    overall_preflight: "READY",
    blockers: [],
    outcome: "Mission accomplished. 120 hectares mapped with 100% point cloud coverage. No anomalies.",
  },
  {
    id: "msn-kota-2026-00424",
    mission_code: "MSN-2026-00424",
    asset_id: "drn-kota-005",
    pilot_name: "Alex Rivera",
    purpose: "Solar Farm Thermal Hotspot Scan",
    status: "PLANNED",
    operating_area: "Solar Grid Delta (44.30N, 73.80W)",
    planned_start: "2026-03-25T10:00:00Z",
    planned_end: "2026-03-25T12:00:00Z",
    preflight_checks: {
      airframe_condition: "FAIL",
      battery_state: "PASS",
      maintenance_status: "PASS",
      inspection_clearance: "PASS",
      open_findings: "FAIL",
      pilot_qualification: "PASS",
      airspace_authorization: "PASS",
    },
    overall_preflight: "BLOCKED",
    blockers: [
      "Airframe is GROUNDED",
      "Open MAJOR finding on propeller blade #3 stress fracture",
    ],
    outcome: null,
  },
];

// -----------------------------------------------------------------------------
// 8. Synthetic Compliance Determinations (Asset-Scoped Regulatory Layer)
// -----------------------------------------------------------------------------

export interface DemoComplianceAssessment {
  id: string;
  organization_id: string;
  aircraft_id: null;
  asset_id: string;
  requirement_id: string;
  requirement_number: string;
  authority: string;
  title: string;
  status: "COMPLIANT" | "NON_COMPLIANT" | "REVIEW_REQUIRED" | "UNKNOWN";
  evaluated_at: string;
  evaluated_by_user_id: string | null;
  notes: string | null;
  override_reason: string | null;
  overridden_by_user_id: string | null;
}

export const DEMO_COMPLIANCE_ASSESSMENTS: DemoComplianceAssessment[] = [
  {
    id: "asmt-drn-001-1",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-001",
    requirement_id: "req-dgca-car-3x",
    requirement_number: "DGCA-CAR-SEC3-UAS",
    authority: "DGCA",
    title: "Type Certification & UAS Operating Rule Compliance",
    status: "COMPLIANT",
    evaluated_at: "2026-03-01",
    evaluated_by_user_id: "usr-tech-01",
    notes: "UIN verified on DigitalSky. Remote ID and NPNT broadcast active.",
    override_reason: null,
    overridden_by_user_id: null,
  },
  {
    id: "asmt-drn-001-2",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-001",
    requirement_id: "req-batt-safe-01",
    requirement_number: "IS-BATT-004",
    authority: "OTHER",
    title: "LiPo Smart Battery Safety & Thermal Containment Standard",
    status: "COMPLIANT",
    evaluated_at: "2026-03-10",
    evaluated_by_user_id: "usr-tech-01",
    notes: "Health verified at 98%, internal resistance balanced across 6 cells.",
    override_reason: null,
    overridden_by_user_id: null,
  },
  {
    id: "asmt-drn-002-1",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-002",
    requirement_id: "req-dgca-car-3x",
    requirement_number: "DGCA-CAR-SEC3-UAS",
    authority: "DGCA",
    title: "Type Certification & UAS Operating Rule Compliance",
    status: "COMPLIANT",
    evaluated_at: "2026-03-01",
    evaluated_by_user_id: "usr-tech-01",
    notes: "Airframe structure compliant. Operating within registered flight envelope.",
    override_reason: null,
    overridden_by_user_id: null,
  },
  {
    id: "asmt-drn-002-2",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-002",
    requirement_id: "req-batt-safe-01",
    requirement_number: "IS-BATT-004",
    authority: "OTHER",
    title: "LiPo Smart Battery Safety & Thermal Containment Standard",
    status: "NON_COMPLIANT",
    evaluated_at: "2026-03-15",
    evaluated_by_user_id: "usr-tech-01",
    notes: "Critical voltage collapse under high discharge rate during benchmark test. Battery grounded.",
    override_reason: null,
    overridden_by_user_id: null,
  },
  {
    id: "asmt-drn-003-1",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-003",
    requirement_id: "req-insp-100h",
    requirement_number: "MP-DRN-100H",
    authority: "DGCA",
    title: "100-Hour Mandatory Airframe Structural Integrity Inspection",
    status: "NON_COMPLIANT",
    evaluated_at: "2026-03-18",
    evaluated_by_user_id: "usr-tech-02",
    notes: "Inspection overdue by 12 flight hours. Dispatch blocked pending maintenance accomplishment.",
    override_reason: null,
    overridden_by_user_id: null,
  },
  {
    id: "asmt-drn-004-1",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-004",
    requirement_id: "req-dgca-car-3x",
    requirement_number: "DGCA-CAR-SEC3-UAS",
    authority: "DGCA",
    title: "Type Certification & UAS Operating Rule Compliance",
    status: "COMPLIANT",
    evaluated_at: "2026-03-05",
    evaluated_by_user_id: "usr-tech-01",
    notes: "VTOL transition controls certified. Airworthiness determination complete.",
    override_reason: null,
    overridden_by_user_id: null,
  },
  {
    id: "asmt-drn-005-1",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-005",
    requirement_id: "req-dgca-car-3x",
    requirement_number: "DGCA-CAR-SEC3-UAS",
    authority: "DGCA",
    title: "Type Certification & UAS Operating Rule Compliance",
    status: "NON_COMPLIANT",
    evaluated_at: "2026-03-16",
    evaluated_by_user_id: "usr-tech-02",
    notes: "Airframe grounded due to stress fracture on carbon propeller blade #3.",
    override_reason: null,
    overridden_by_user_id: null,
  },
  {
    id: "asmt-drn-005-2",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-005",
    requirement_id: "req-uin-renew",
    requirement_number: "DGCA-UIN-RNW",
    authority: "DGCA",
    title: "UAS Registration & UIN Digital Certificate Renewal",
    status: "REVIEW_REQUIRED",
    evaluated_at: "2026-03-16",
    evaluated_by_user_id: "usr-tech-02",
    notes: "Annual digital certificate expiration in 14 days. Renewal application submitted.",
    override_reason: null,
    overridden_by_user_id: null,
  },
  {
    id: "asmt-drn-006-1",
    organization_id: DEMO_ORG_ID,
    aircraft_id: null,
    asset_id: "drn-kota-006",
    requirement_id: "req-dgca-car-3x",
    requirement_number: "DGCA-CAR-SEC3-UAS",
    authority: "DGCA",
    title: "Type Certification & UAS Operating Rule Compliance",
    status: "COMPLIANT",
    evaluated_at: "2026-03-02",
    evaluated_by_user_id: "usr-tech-01",
    notes: "Autonomous perimeter surveillance system and fail-safe return-to-home verified.",
    override_reason: null,
    overridden_by_user_id: null,
  },
];

// -----------------------------------------------------------------------------
// 9. Accessor & Calculation Functions
// -----------------------------------------------------------------------------

export function getDemoComplianceForDrone(droneId: string): DemoComplianceAssessment[] {
  const drone = getDemoDroneById(droneId);
  if (!drone) return [];
  return DEMO_COMPLIANCE_ASSESSMENTS.filter((c) => c.asset_id === drone.id);
}

export function getDemoDrones(): DroneResponse[] {
  return DEMO_DRONES;
}

export function getDemoDroneById(id: string): DroneResponse | undefined {
  return DEMO_DRONES.find((d) => d.id === id || d.registration === id);
}

export function getDemoBatteryForDrone(droneId: string): BatteryResponse | undefined {
  const drone = getDemoDroneById(droneId);
  if (!drone) return undefined;
  return DEMO_BATTERIES.find((b) => b.asset_id === drone.id);
}

export function getDemoComponentsForDrone(droneId: string): ComponentResponse[] {
  const drone = getDemoDroneById(droneId);
  if (!drone) return [];
  return DEMO_COMPONENTS.filter((c) => c.asset_id === drone.id);
}

export function getDemoFlightsForDrone(droneId: string): FlightResponse[] {
  const drone = getDemoDroneById(droneId);
  if (!drone) return [];
  return DEMO_FLIGHTS.filter((f) => f.asset_id === drone.id);
}

export function getDemoUtilizationForDrone(droneId: string): UtilizationResponse {
  const drone = getDemoDroneById(droneId);
  if (!drone) {
    return { asset_id: droneId, total_flights: 0, total_minutes: 0, total_cycles: 0 };
  }
  const flights = getDemoFlightsForDrone(drone.id);
  const totalMinutes = flights.reduce((sum, f) => sum + f.duration_minutes, 0);
  const totalCycles = flights.reduce((sum, f) => sum + f.cycles, 0);
  return {
    asset_id: drone.id,
    total_flights: flights.length,
    total_minutes: totalMinutes,
    total_cycles: totalCycles,
  };
}

export function getDemoFindingsForDrone(droneId: string): BackendFinding[] {
  const drone = getDemoDroneById(droneId);
  if (!drone) return [];
  return DEMO_FINDINGS.filter((f) => f.asset_id === drone.id);
}

export function getDemoMaintenanceForDrone(droneId: string): MaintenanceDueItem[] {
  const drone = getDemoDroneById(droneId);
  if (!drone) return [];
  return DEMO_MAINTENANCE_DUE[drone.id] ?? [];
}

export function getDemoMissionsForDrone(droneId: string): DemoMission[] {
  const drone = getDemoDroneById(droneId);
  if (!drone) return [];
  return DEMO_MISSIONS.filter((m) => m.asset_id === drone.id);
}

export function getDemoDeploymentReadiness(droneId: string): DeploymentReadinessResponse {
  const drone = getDemoDroneById(droneId);
  if (!drone) {
    return { asset_id: droneId, status: "BLOCKED", blockers: ["Drone not found"] };
  }

  const blockers: string[] = [];
  const findingBlockers: { finding_id: string; title: string; severity: string; status: string }[] = [];

  if (drone.status !== "ACTIVE") {
    blockers.push(`Drone is not active (status: ${drone.status})`);
  }

  const battery = getDemoBatteryForDrone(drone.id);
  if (!battery) {
    blockers.push("No battery assigned");
  } else if (battery.status === "CRITICAL") {
    blockers.push("Battery critical");
  }

  const maintenance = getDemoMaintenanceForDrone(drone.id);
  if (maintenance.some((m) => m.due_status === "OVERDUE")) {
    blockers.push("Maintenance overdue");
  }

  const findings = getDemoFindingsForDrone(drone.id);
  const openFindings = findings.filter((f) => f.status !== "CLOSED");
  for (const f of openFindings) {
    blockers.push(`Unresolved finding: ${f.title}`);
    findingBlockers.push({
      finding_id: f.id,
      title: f.title,
      severity: f.severity,
      status: f.status,
    });
  }

  return {
    asset_id: drone.id,
    status: blockers.length === 0 ? "READY" : "BLOCKED",
    blockers,
    finding_blockers: findingBlockers.length > 0 ? findingBlockers : undefined,
  };
}

export function getDemoFleetStatistics() {
  const total = DEMO_DRONES.length;
  let ready = 0;
  let blocked = 0;
  let grounded = 0;
  let maintDue = 0;

  for (const drone of DEMO_DRONES) {
    if (drone.status === "GROUNDED") {
      grounded++;
    }
    const readiness = getDemoDeploymentReadiness(drone.id);
    if (readiness.status === "READY") {
      ready++;
    } else {
      blocked++;
    }
    const maint = getDemoMaintenanceForDrone(drone.id);
    if (maint.some((m) => m.due_status === "OVERDUE")) {
      maintDue++;
    }
  }

  const openFindings = DEMO_FINDINGS.filter((f) => f.status !== "CLOSED").length;
  const totalFlights = DEMO_FLIGHTS.length;
  const totalFlightHours = (DEMO_FLIGHTS.reduce((sum, f) => sum + f.duration_minutes, 0) / 60).toFixed(1);

  return {
    totalDrones: total,
    readyDrones: ready,
    blockedDrones: blocked,
    groundedDrones: grounded,
    maintenanceDueDrones: maintDue,
    openFindingsCount: openFindings,
    totalFlights,
    totalFlightHours,
  };
}
