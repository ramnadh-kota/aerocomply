import { DEMO_ORG_ID, DEMO_ORG_NAME, DEMO_USER_ID, DEMO_USER_NAME, DEMO_USER_EMAIL } from "@/lib/auth/SessionContext";
import type {
  TenantDashboardStats,
  TenantInvitation,
  TenantProfile,
  TenantRoleInfo,
  TenantSettings,
  TenantTeam,
  TenantUsage,
  TenantUser,
} from "@/lib/api/tenant";
import type { AuditEventResponse } from "@/lib/api/audit";

export const DEMO_TENANT_PROFILE: TenantProfile = {
  id: DEMO_ORG_ID,
  name: DEMO_ORG_NAME,
  status: "ACTIVE",
  industry: "AIRCRAFT",
  created_at: "2026-01-15T08:00:00Z",
  primary_contact_email: DEMO_USER_EMAIL,
  primary_contact_name: DEMO_USER_NAME,
};

export const DEMO_TENANT_SETTINGS: TenantSettings = {
  organization_id: DEMO_ORG_ID,
  timezone: "UTC+05:30",
  operational_mode: "STANDARD",
  default_asset_type: "AIRCRAFT",
  notification_email: "ops@kotaaerospace.com",
};

export const DEMO_TENANT_ROLES: TenantRoleInfo[] = [
  {
    role_name: "ORG_ADMIN",
    display_name: "Organization Administrator",
    description: "Full administrative authority over the customer organization, users, and operational configuration.",
    permissions: [
      "aircraft:read", "aircraft:write", "assessment:read", "assessment:write", "audit:read",
      "compliance:assess", "compliance:decide", "drone:read", "drone:write", "evidence:read",
      "evidence:upload", "facility:read", "facility:write", "inspection:read", "inspection:write",
      "org:manage", "part:read", "part:write", "procurement:approve", "procurement:read",
      "procurement:write", "regulation:read", "technician:read", "technician:write", "user:manage"
    ],
    is_system_role: true,
  },
  {
    role_name: "CAMO_MANAGER",
    display_name: "CAMO Manager",
    description: "Continuing Airworthiness Management Organization lead; oversees maintenance scheduling, fleet reliability, and work orders.",
    permissions: [
      "aircraft:read", "aircraft:write", "assessment:read", "assessment:write", "compliance:assess",
      "compliance:decide", "drone:read", "drone:write", "evidence:read", "evidence:upload",
      "facility:read", "facility:write", "inspection:read", "inspection:write", "part:read",
      "part:write", "procurement:approve", "procurement:read", "procurement:write", "regulation:read",
      "technician:read", "technician:write", "vendor:read", "vendor:write"
    ],
    is_system_role: true,
  },
  {
    role_name: "COMPLIANCE_MANAGER",
    display_name: "Compliance Manager",
    description: "Regulatory compliance officer; oversees assessment frameworks, regulatory registries, and audit readiness.",
    permissions: [
      "aircraft:read", "assessment:read", "assessment:write", "audit:read", "compliance:assess",
      "compliance:decide", "drone:read", "evidence:read", "evidence:upload", "facility:read",
      "inspection:read", "inspection:write", "part:read", "procurement:read", "regulation:ingest",
      "regulation:read", "regulation:write", "technician:read", "vendor:read"
    ],
    is_system_role: true,
  },
  {
    role_name: "QUALITY_MANAGER",
    display_name: "Quality Manager",
    description: "Quality assurance manager; inspects maintenance findings, RII approvals, and safety governance.",
    permissions: [
      "aircraft:read", "assessment:read", "assessment:write", "audit:read", "compliance:assess",
      "drone:read", "evidence:read", "facility:read", "inspection:read", "inspection:write",
      "part:read", "procurement:read", "regulation:read", "technician:read", "vendor:read"
    ],
    is_system_role: true,
  },
  {
    role_name: "MAINTENANCE_ENGINEER",
    display_name: "Maintenance Engineer",
    description: "Licensed maintenance personnel; signs off tasks, uploads documentary evidence, and executes work orders.",
    permissions: [
      "aircraft:read", "assessment:read", "drone:read", "evidence:read", "evidence:upload",
      "facility:read", "inspection:read", "part:read", "procurement:read", "procurement:write",
      "regulation:read", "technician:read", "technician:write", "vendor:read"
    ],
    is_system_role: true,
  },
  {
    role_name: "VIEWER",
    display_name: "Stakeholder / Viewer",
    description: "Read-only stakeholder access to fleet health, documentation, and compliance status.",
    permissions: [
      "aircraft:read", "assessment:read", "drone:read", "evidence:read", "facility:read",
      "inspection:read", "part:read", "procurement:read", "regulation:read", "technician:read",
      "vendor:read"
    ],
    is_system_role: true,
  },
];

export const DEMO_TENANT_USERS: TenantUser[] = [
  {
    id: DEMO_USER_ID,
    email: DEMO_USER_EMAIL,
    full_name: DEMO_USER_NAME,
    is_active: true,
    roles: ["ORG_ADMIN", "CAMO_MANAGER"],
    created_at: "2026-01-15T08:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000011",
    email: "priya.nair@kotaaerospace.com",
    full_name: "Priya Nair",
    is_active: true,
    roles: ["ORG_ADMIN"],
    created_at: "2026-01-18T10:15:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000012",
    email: "elena.petrov@kotaaerospace.com",
    full_name: "Elena Petrov",
    is_active: true,
    roles: ["COMPLIANCE_MANAGER"],
    created_at: "2026-01-20T11:30:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000013",
    email: "marcus.webb@kotaaerospace.com",
    full_name: "Marcus Webb",
    is_active: true,
    roles: ["CAMO_MANAGER"],
    created_at: "2026-01-22T09:45:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000014",
    email: "rahul.menon@kotaaerospace.com",
    full_name: "Rahul Menon",
    is_active: true,
    roles: ["MAINTENANCE_ENGINEER"],
    created_at: "2026-02-01T14:20:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000015",
    email: "diego.alvarez@kotaaerospace.com",
    full_name: "Diego Alvarez",
    is_active: true,
    roles: ["QUALITY_MANAGER"],
    created_at: "2026-02-05T08:10:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000016",
    email: "auditor@aviation-authority.gov",
    full_name: "Regulator Liaison",
    is_active: true,
    roles: ["VIEWER"],
    created_at: "2026-02-15T16:00:00Z",
  },
];

export const DEMO_TENANT_INVITATIONS: TenantInvitation[] = [
  {
    id: "00000000-0000-0000-0000-000000000021",
    user_id: "00000000-0000-0000-0000-000000000031",
    email: "vikram.sharma@kotaaerospace.com",
    full_name: "Capt. Vikram Sharma",
    role: "CAMO_MANAGER",
    status: "PENDING",
    created_at: "2026-03-20T09:00:00Z",
    expires_at: "2026-03-27T09:00:00Z",
    can_resend: true,
    can_cancel: true,
  },
  {
    id: "00000000-0000-0000-0000-000000000022",
    user_id: "00000000-0000-0000-0000-000000000032",
    email: "sarah.chen@kotaaerospace.com",
    full_name: "Sarah Chen",
    role: "MAINTENANCE_ENGINEER",
    status: "PENDING",
    created_at: "2026-03-21T14:30:00Z",
    expires_at: "2026-03-28T14:30:00Z",
    can_resend: true,
    can_cancel: true,
  },
  {
    id: "00000000-0000-0000-0000-000000000023",
    user_id: "00000000-0000-0000-0000-000000000033",
    email: "diego.alvarez@kotaaerospace.com",
    full_name: "Diego Alvarez",
    role: "QUALITY_MANAGER",
    status: "ACCEPTED",
    created_at: "2026-02-05T08:00:00Z",
    expires_at: "2026-02-12T08:00:00Z",
    can_resend: false,
    can_cancel: false,
  },
  {
    id: "00000000-0000-0000-0000-000000000024",
    user_id: "00000000-0000-0000-0000-000000000034",
    email: "james.wilson@partner.com",
    full_name: "James Wilson",
    role: "VIEWER",
    status: "EXPIRED",
    created_at: "2026-02-10T10:00:00Z",
    expires_at: "2026-02-17T10:00:00Z",
    can_resend: true,
    can_cancel: false,
  },
];

export const DEMO_TENANT_TEAMS: TenantTeam[] = [
  {
    id: "team-admin",
    name: "Organization Administration",
    description: "Tenant administrators managing personnel, commercial plans, facilities, and access.",
    lead_role: "ORG_ADMIN",
    member_count: 2,
    members: [
      { user_id: DEMO_USER_ID, full_name: DEMO_USER_NAME, email: DEMO_USER_EMAIL, role: "ORG_ADMIN" },
      { user_id: "00000000-0000-0000-0000-000000000011", full_name: "Priya Nair", email: "priya.nair@kotaaerospace.com", role: "ORG_ADMIN" },
    ],
  },
  {
    id: "team-maintenance",
    name: "Maintenance & CAMO",
    description: "CAMO managers, licensed engineers, and technicians executing work orders and AOG recovery.",
    lead_role: "CAMO_MANAGER",
    member_count: 3,
    members: [
      { user_id: DEMO_USER_ID, full_name: DEMO_USER_NAME, email: DEMO_USER_EMAIL, role: "CAMO_MANAGER" },
      { user_id: "00000000-0000-0000-0000-000000000013", full_name: "Marcus Webb", email: "marcus.webb@kotaaerospace.com", role: "CAMO_MANAGER" },
      { user_id: "00000000-0000-0000-0000-000000000014", full_name: "Rahul Menon", email: "rahul.menon@kotaaerospace.com", role: "MAINTENANCE_ENGINEER" },
    ],
  },
  {
    id: "team-quality",
    name: "Quality & Inspection",
    description: "Quality assurance inspectors performing RII sign-offs and maintenance verification.",
    lead_role: "QUALITY_MANAGER",
    member_count: 1,
    members: [
      { user_id: "00000000-0000-0000-0000-000000000015", full_name: "Diego Alvarez", email: "diego.alvarez@kotaaerospace.com", role: "QUALITY_MANAGER" },
    ],
  },
  {
    id: "team-compliance",
    name: "Regulatory & Safety Compliance",
    description: "Compliance managers auditing requirements against CAA, EASA, and FAA frameworks.",
    lead_role: "COMPLIANCE_MANAGER",
    member_count: 1,
    members: [
      { user_id: "00000000-0000-0000-0000-000000000012", full_name: "Elena Petrov", email: "elena.petrov@kotaaerospace.com", role: "COMPLIANCE_MANAGER" },
    ],
  },
  {
    id: "team-viewers",
    name: "Stakeholders & Viewers",
    description: "External and internal stakeholders with read-only operational visibility.",
    lead_role: "VIEWER",
    member_count: 1,
    members: [
      { user_id: "00000000-0000-0000-0000-000000000016", full_name: "Regulator Liaison", email: "auditor@aviation-authority.gov", role: "VIEWER" },
    ],
  },
];

export const DEMO_TENANT_USAGE: TenantUsage = {
  organization_id: DEMO_ORG_ID,
  metrics: [
    {
      key: "user_seats",
      label: "User Accounts",
      tracked: true,
      value: 7,
      limit: 25,
      is_unlimited: false,
      unit: "Seats",
      status: "TRACKED",
    },
    {
      key: "aircraft_assets",
      label: "Fixed-Wing Aircraft Fleet",
      tracked: true,
      value: 4,
      limit: 10,
      is_unlimited: false,
      unit: "Aircraft",
      status: "TRACKED",
    },
    {
      key: "drone_assets",
      label: "Drone UAV Fleet",
      tracked: true,
      value: 3,
      limit: 50,
      is_unlimited: false,
      unit: "Drones",
      status: "TRACKED",
    },
    {
      key: "facilities",
      label: "Operational Facilities & Bases",
      tracked: true,
      value: 3,
      limit: 5,
      is_unlimited: false,
      unit: "Sites",
      status: "TRACKED",
    },
    {
      key: "blob_storage",
      label: "Document / Evidence Blob Storage",
      tracked: false,
      value: null,
      limit: null,
      is_unlimited: false,
      unit: "GB",
      status: "NOT_TRACKED",
    },
    {
      key: "api_bandwidth",
      label: "API Traffic & Query Bandwidth",
      tracked: false,
      value: null,
      limit: null,
      is_unlimited: false,
      unit: "Req/mo",
      status: "NOT_TRACKED",
    },
    {
      key: "lisa_ai_tokens",
      label: "LISA AI Copilot Inference Tokens",
      tracked: false,
      value: null,
      limit: null,
      is_unlimited: false,
      unit: "Tokens",
      status: "NOT_TRACKED",
    },
  ],
};

export const DEMO_TENANT_DASHBOARD_STATS: TenantDashboardStats = {
  organization: DEMO_TENANT_PROFILE,
  users_count: 7,
  active_users_count: 7,
  pending_invitations_count: 2,
  fleet_count: 7,
  aircraft_count: 4,
  drone_count: 3,
  facility_count: 3,
  team_count: 5,
  current_plan: "ENTERPRISE",
  subscription_status: "ACTIVE",
  effective_features_count: 8,
  attention_items: [
    {
      severity: "INFO",
      category: "PEOPLE",
      title: "2 Pending Invitations",
      message: "Capt. Vikram Sharma and Sarah Chen have pending onboarding invitations.",
      link_href: "/tenant/invitations",
      link_label: "Inspect Invitations",
    },
    {
      severity: "INFO",
      category: "FLEET",
      title: "Mixed Fleet Operational",
      message: "Tenant is operating 4 fixed-wing aircraft and 3 drone UAV assets under unified compliance.",
      link_href: "/tenant/fleet",
      link_label: "View Fleet",
    },
  ],
};

export const DEMO_TENANT_AUDIT_EVENTS: AuditEventResponse[] = [
  {
    id: "00000000-0000-0000-0000-000000000041",
    organization_id: DEMO_ORG_ID,
    created_at: "2026-03-21T14:30:00Z",
    user_id: DEMO_USER_ID,
    action: "tenant.user.invited",
    entity_type: "User",
    entity_id: "00000000-0000-0000-0000-000000000032",
    event_metadata: { email: "sarah.chen@kotaaerospace.com", role: "MAINTENANCE_ENGINEER" },
  },
  {
    id: "00000000-0000-0000-0000-000000000042",
    organization_id: DEMO_ORG_ID,
    created_at: "2026-03-20T09:00:00Z",
    user_id: DEMO_USER_ID,
    action: "tenant.user.invited",
    entity_type: "User",
    entity_id: "00000000-0000-0000-0000-000000000031",
    event_metadata: { email: "vikram.sharma@kotaaerospace.com", role: "CAMO_MANAGER" },
  },
  {
    id: "00000000-0000-0000-0000-000000000043",
    organization_id: DEMO_ORG_ID,
    created_at: "2026-03-15T11:20:00Z",
    user_id: DEMO_USER_ID,
    action: "tenant.profile.updated",
    entity_type: "Organization",
    entity_id: DEMO_ORG_ID,
    event_metadata: { industry: "AIRCRAFT" },
  },
  {
    id: "00000000-0000-0000-0000-000000000044",
    organization_id: DEMO_ORG_ID,
    created_at: "2026-03-10T16:45:00Z",
    user_id: DEMO_USER_ID,
    action: "tenant.settings.updated",
    entity_type: "Organization",
    entity_id: DEMO_ORG_ID,
    event_metadata: { timezone: "UTC+05:30", operational_mode: "STANDARD" },
  },
  {
    id: "00000000-0000-0000-0000-000000000045",
    organization_id: DEMO_ORG_ID,
    created_at: "2026-03-01T10:00:00Z",
    user_id: DEMO_USER_ID,
    action: "facility.created",
    entity_type: "Facility",
    entity_id: "00000000-0000-0000-0000-000000000051",
    event_metadata: { code: "BOM-H1", name: "Main Maintenance Hangar", facility_type: "HANGAR" },
  },
];
