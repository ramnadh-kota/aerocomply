// Deterministic Synthetic Platform Control Plane Dataset for DEMO mode.
// Strictly isolated: never contacts backend APIs, never mutates real database records.
// Explicitly labeled as "DEMO ENVIRONMENT · SYNTHETIC DATA".

import type { BackendPlatformOrganization, PlatformUser } from "@/lib/api/platform";
import type { PlanResponse, PlanFeatureResponse } from "@/lib/api/plan";
import type {
  EntitlementResolutionResponse,
  TenantFeatureOverrideResponse,
  TenantUsageLimitResponse,
} from "@/lib/api/entitlement";
import type { SubscriptionResponse } from "@/lib/api/subscription";
import type { AuditEventResponse } from "@/lib/api/audit";

export const DEMO_PLATFORM_ORGANIZATIONS: BackendPlatformOrganization[] = [
  {
    id: "00000000-0000-0000-0000-000000000001",
    name: "KOTA Aerospace Demo Operations",
    status: "ACTIVE",
    industry: "DRONE_UAV",
    created_at: "2026-01-15T08:00:00Z",
    user_count: 8,
    aircraft_count: 4,
    drone_count: 6,
  },
  {
    id: "00000000-0000-0000-0000-000000000010",
    name: "AeroAir Charter Systems (Demo Org A)",
    status: "ACTIVE",
    industry: "AIRCRAFT",
    created_at: "2026-02-01T09:30:00Z",
    user_count: 14,
    aircraft_count: 8,
    drone_count: 0,
  },
  {
    id: "00000000-0000-0000-0000-000000000020",
    name: "Horizon Drone Services (Demo Org B)",
    status: "ACTIVE",
    industry: "DRONE_UAV",
    created_at: "2026-02-15T11:00:00Z",
    user_count: 6,
    aircraft_count: 0,
    drone_count: 12,
  },
  {
    id: "00000000-0000-0000-0000-000000000030",
    name: "Apex Cargo Transport (Demo Org C)",
    status: "SUSPENDED",
    industry: "AIRCRAFT",
    created_at: "2026-03-01T14:15:00Z",
    user_count: 10,
    aircraft_count: 5,
    drone_count: 0,
  },
  {
    id: "00000000-0000-0000-0000-000000000040",
    name: "Skyline Urban Air Mobility (Demo Org D)",
    status: "ACTIVE",
    industry: "EVTOL_AAM",
    created_at: "2026-03-10T16:45:00Z",
    user_count: 5,
    aircraft_count: 0,
    drone_count: 4,
  },
];

export const DEMO_PLATFORM_PLANS: PlanResponse[] = [
  {
    id: "10000000-0000-0000-0000-000000000001",
    name: "Kota Drone",
    code: "DRONE_001",
    description: "Foundational drone fleet management, telemetry, and compliance operations.",
    asset_scope: "DRONE",
    included_features_count: 6,
    tenant_count: 2,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "10000000-0000-0000-0000-000000000002",
    name: "Kota Aircraft",
    code: "AIRCRAFT_001",
    description: "Fixed-wing commercial airworthiness, CAMO, MRO work orders, and inspections.",
    asset_scope: "AIRCRAFT",
    included_features_count: 6,
    tenant_count: 2,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "10000000-0000-0000-0000-000000000003",
    name: "Kota Helicopter",
    code: "HELICOPTER_001",
    description: "Rotorcraft airframe lifecycle, dynamic component tracking, and flight maintenance.",
    asset_scope: "HELICOPTER",
    included_features_count: 5,
    tenant_count: 0,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "10000000-0000-0000-0000-000000000004",
    name: "Kota eVTOL",
    code: "EVTOL_001",
    description: "Advanced Air Mobility (AAM) operations, AI predictive maintenance, and battery intelligence.",
    asset_scope: "EVTOL",
    included_features_count: 9,
    tenant_count: 1,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

export interface PlatformFeatureItem {
  feature_key: string;
  name: string;
  description: string;
  category: "Fleet Operations" | "Maintenance & MRO" | "Compliance & Audit" | "Intelligence & AI";
  plans: string[];
}

export const DEMO_PLATFORM_FEATURES: PlatformFeatureItem[] = [
  {
    feature_key: "drone_fleet_management",
    name: "Drone Fleet Operations",
    description: "Operational management of UAS assets, batteries, components, and telemetry.",
    category: "Fleet Operations",
    plans: ["starter", "professional", "enterprise"],
  },
  {
    feature_key: "work_order_management",
    name: "Work Order Management",
    description: "MRO task scheduling, step execution, and technician sign-offs.",
    category: "Maintenance & MRO",
    plans: ["starter", "professional", "enterprise"],
  },
  {
    feature_key: "compliance_reporting",
    name: "Compliance & Regulatory Register",
    description: "Rule compliance assessments, regulatory requirements tracking, and evidence.",
    category: "Compliance & Audit",
    plans: ["starter", "professional", "enterprise"],
  },
  {
    feature_key: "audit_logging",
    name: "Audit Trail & Verification",
    description: "Append-only immutable record of all operational and maintenance transitions.",
    category: "Compliance & Audit",
    plans: ["starter", "professional", "enterprise"],
  },
  {
    feature_key: "release_readiness",
    name: "Release to Service Readiness",
    description: "Automated pre-flight readiness gate evaluating evidence, RII, and open tasks.",
    category: "Maintenance & MRO",
    plans: ["professional", "enterprise"],
  },
  {
    feature_key: "flight_telemetry",
    name: "Live Mission & Flight Telemetry",
    description: "Mission flight logging, airspace integration, and pilot flight telemetry.",
    category: "Fleet Operations",
    plans: ["professional", "enterprise"],
  },
  {
    feature_key: "battery_analytics",
    name: "Battery Cycle & Health Analytics",
    description: "Predictive health monitoring and cycle lifetime management for UAS batteries.",
    category: "Fleet Operations",
    plans: ["professional", "enterprise"],
  },
  {
    feature_key: "lisa_ai_copilot",
    name: "LISA AI Aerospace Intelligence",
    description: "Airworthiness knowledge copilot for technical records and regulatory guidance.",
    category: "Intelligence & AI",
    plans: ["enterprise"],
  },
  {
    feature_key: "procurement_management",
    name: "Procurement & Vendor Intelligence",
    description: "Part catalog ordering, purchase order workflows, and supplier intelligence.",
    category: "Maintenance & MRO",
    plans: ["enterprise"],
  },
];

export const DEMO_PLATFORM_SUBSCRIPTIONS: SubscriptionResponse[] = [
  {
    id: "20000000-0000-0000-0000-000000000001",
    organization_id: "00000000-0000-0000-0000-000000000001",
    plan_id: "10000000-0000-0000-0000-000000000003",
    status: "ACTIVE",
    starts_at: "2026-01-15T00:00:00Z",
    ends_at: null,
    created_at: "2026-01-15T00:00:00Z",
    updated_at: "2026-01-15T00:00:00Z",
  },
  {
    id: "20000000-0000-0000-0000-000000000002",
    organization_id: "00000000-0000-0000-0000-000000000010",
    plan_id: "10000000-0000-0000-0000-000000000002",
    status: "ACTIVE",
    starts_at: "2026-02-01T00:00:00Z",
    ends_at: null,
    created_at: "2026-02-01T00:00:00Z",
    updated_at: "2026-02-01T00:00:00Z",
  },
  {
    id: "20000000-0000-0000-0000-000000000003",
    organization_id: "00000000-0000-0000-0000-000000000020",
    plan_id: "10000000-0000-0000-0000-000000000002",
    status: "TRIALING",
    starts_at: "2026-02-15T00:00:00Z",
    ends_at: "2026-04-15T00:00:00Z",
    created_at: "2026-02-15T00:00:00Z",
    updated_at: "2026-02-15T00:00:00Z",
  },
  {
    id: "20000000-0000-0000-0000-000000000004",
    organization_id: "00000000-0000-0000-0000-000000000030",
    plan_id: "10000000-0000-0000-0000-000000000001",
    status: "PAST_DUE",
    starts_at: "2026-03-01T00:00:00Z",
    ends_at: null,
    created_at: "2026-03-01T00:00:00Z",
    updated_at: "2026-03-01T00:00:00Z",
  },
  {
    id: "20000000-0000-0000-0000-000000000005",
    organization_id: "00000000-0000-0000-0000-000000000040",
    plan_id: "10000000-0000-0000-0000-000000000002",
    status: "ACTIVE",
    starts_at: "2026-03-10T00:00:00Z",
    ends_at: null,
    created_at: "2026-03-10T00:00:00Z",
    updated_at: "2026-03-10T00:00:00Z",
  },
];

export const DEMO_PLATFORM_USERS: PlatformUser[] = [
  {
    id: "30000000-0000-0000-0000-000000000001",
    organization_id: "00000000-0000-0000-0000-000000000001",
    organization_name: "KOTA Aerospace Demo Operations",
    email: "admin@kotaaerospace.com",
    full_name: "Marcus Vance",
    is_active: true,
    roles: ["ORG_ADMIN", "CAMO_MANAGER"],
    created_at: "2026-01-15T08:05:00Z",
  },
  {
    id: "30000000-0000-0000-0000-000000000002",
    organization_id: "00000000-0000-0000-0000-000000000001",
    organization_name: "KOTA Aerospace Demo Operations",
    email: "pilot@kotaaerospace.com",
    full_name: "Elena Rostova",
    is_active: true,
    roles: ["CHIEF_PILOT"],
    created_at: "2026-01-15T08:10:00Z",
  },
  {
    id: "30000000-0000-0000-0000-000000000010",
    organization_id: "00000000-0000-0000-0000-000000000010",
    organization_name: "AeroAir Charter Systems (Demo Org A)",
    email: "c.mitchell@aeroair.com",
    full_name: "Christopher Mitchell",
    is_active: true,
    roles: ["ORG_ADMIN"],
    created_at: "2026-02-01T09:35:00Z",
  },
  {
    id: "30000000-0000-0000-0000-000000000020",
    organization_id: "00000000-0000-0000-0000-000000000020",
    organization_name: "Horizon Drone Services (Demo Org B)",
    email: "t.hayes@horizondrones.com",
    full_name: "Tanya Hayes",
    is_active: true,
    roles: ["ORG_ADMIN"],
    created_at: "2026-02-15T11:05:00Z",
  },
  {
    id: "30000000-0000-0000-0000-000000000030",
    organization_id: "00000000-0000-0000-0000-000000000030",
    organization_name: "Apex Cargo Transport (Demo Org C)",
    email: "d.chen@apexcargo.com",
    full_name: "David Chen",
    is_active: false,
    roles: ["ORG_ADMIN"],
    created_at: "2026-03-01T14:20:00Z",
  },
  {
    id: "30000000-0000-0000-0000-000000000040",
    organization_id: "00000000-0000-0000-0000-000000000040",
    organization_name: "Skyline Urban Air Mobility (Demo Org D)",
    email: "s.patel@skylineaam.com",
    full_name: "Siddharth Patel",
    is_active: true,
    roles: ["ORG_ADMIN"],
    created_at: "2026-03-10T16:50:00Z",
  },
  {
    id: "30000000-0000-0000-0000-000000000099",
    organization_id: "00000000-0000-0000-0000-000000000001",
    organization_name: "KOTA Aerospace (Platform Operator)",
    email: "platform.admin@kotaaerospace.com",
    full_name: "Platform Master Admin",
    is_active: true,
    roles: ["PLATFORM_ADMIN"],
    created_at: "2026-01-01T00:00:00Z",
  },
];

export const DEMO_PLATFORM_AUDIT_EVENTS: AuditEventResponse[] = [
  {
    id: "40000000-0000-0000-0000-000000000001",
    organization_id: "00000000-0000-0000-0000-000000000040",
    user_id: "30000000-0000-0000-0000-000000000099",
    action: "platform.organization.provision",
    entity_type: "Organization",
    entity_id: "00000000-0000-0000-0000-000000000040",
    event_metadata: { plan_code: "professional", admin_email: "s.patel@skylineaam.com" },
    created_at: "2026-03-10T16:45:00Z",
  },
  {
    id: "40000000-0000-0000-0000-000000000002",
    organization_id: "00000000-0000-0000-0000-000000000030",
    user_id: "30000000-0000-0000-0000-000000000099",
    action: "platform.organization.suspend",
    entity_type: "Organization",
    entity_id: "00000000-0000-0000-0000-000000000030",
    event_metadata: { reason: "Overdue commercial billing delinquency" },
    created_at: "2026-03-08T11:20:00Z",
  },
  {
    id: "40000000-0000-0000-0000-000000000003",
    organization_id: "00000000-0000-0000-0000-000000000020",
    user_id: "30000000-0000-0000-0000-000000000099",
    action: "platform.entitlement.override_create",
    entity_type: "TenantFeatureOverride",
    entity_id: "50000000-0000-0000-0000-000000000001",
    event_metadata: { feature_key: "battery_analytics", enabled: true, reason: "Enterprise trial request" },
    created_at: "2026-02-20T10:15:00Z",
  },
  {
    id: "40000000-0000-0000-0000-000000000004",
    organization_id: "00000000-0000-0000-0000-000000000010",
    user_id: "30000000-0000-0000-0000-000000000099",
    action: "platform.subscription.create",
    entity_type: "Subscription",
    entity_id: "20000000-0000-0000-0000-000000000002",
    event_metadata: { plan_code: "professional", status: "ACTIVE" },
    created_at: "2026-02-01T09:30:00Z",
  },
];

export interface PlatformDashboardKPIs {
  totalOrganizations: number;
  activeOrganizations: number;
  suspendedOrganizations: number;
  pendingProvisioning: number;
  activeSubscriptions: number;
  trialSubscriptions: number;
  totalUsers: number;
  totalAircraft: number;
  totalDrones: number;
  organizationsByPlan: { planCode: string; planName: string; count: number }[];
  enabledFeatureDistribution: { featureKey: string; name: string; orgCount: number }[];
  recentActivity: AuditEventResponse[];
}

export function getDemoPlatformStats(): PlatformDashboardKPIs {
  const totalOrgs = DEMO_PLATFORM_ORGANIZATIONS.length;
  const activeOrgs = DEMO_PLATFORM_ORGANIZATIONS.filter((o) => o.status === "ACTIVE").length;
  const suspendedOrgs = DEMO_PLATFORM_ORGANIZATIONS.filter((o) => o.status === "SUSPENDED").length;
  const activeSubs = DEMO_PLATFORM_SUBSCRIPTIONS.filter((s) => s.status === "ACTIVE").length;
  const trialSubs = DEMO_PLATFORM_SUBSCRIPTIONS.filter((s) => s.status === "TRIALING").length;

  const totalUsers = DEMO_PLATFORM_ORGANIZATIONS.reduce((sum, o) => sum + o.user_count, 0);
  const totalAircraft = DEMO_PLATFORM_ORGANIZATIONS.reduce((sum, o) => sum + o.aircraft_count, 0);
  const totalDrones = DEMO_PLATFORM_ORGANIZATIONS.reduce((sum, o) => sum + (o.drone_count ?? 0), 0);

  const orgsByPlan = [
    { planCode: "enterprise", planName: "Enterprise Multi-Domain Control", count: 1 },
    { planCode: "professional", planName: "Professional Autonomous Ops", count: 3 },
    { planCode: "starter", planName: "Starter Commercial Fleet", count: 1 },
  ];

  const enabledFeatureDistribution = [
    { featureKey: "drone_fleet_management", name: "Drone Fleet Operations", orgCount: 5 },
    { featureKey: "work_order_management", name: "Work Order Management", orgCount: 5 },
    { featureKey: "compliance_reporting", name: "Compliance & Regulatory Register", orgCount: 5 },
    { featureKey: "audit_logging", name: "Audit Trail & Verification", orgCount: 5 },
    { featureKey: "release_readiness", name: "Release to Service Readiness", orgCount: 4 },
    { featureKey: "flight_telemetry", name: "Live Mission & Flight Telemetry", orgCount: 4 },
    { featureKey: "battery_analytics", name: "Battery Cycle & Health Analytics", orgCount: 4 },
    { featureKey: "lisa_ai_copilot", name: "LISA AI Aerospace Intelligence", orgCount: 1 },
    { featureKey: "procurement_management", name: "Procurement & Vendor Intelligence", orgCount: 1 },
  ];

  return {
    totalOrganizations: totalOrgs,
    activeOrganizations: activeOrgs,
    suspendedOrganizations: suspendedOrgs,
    pendingProvisioning: 0,
    activeSubscriptions: activeSubs,
    trialSubscriptions: trialSubs,
    totalUsers,
    totalAircraft,
    totalDrones,
    organizationsByPlan: orgsByPlan,
    enabledFeatureDistribution,
    recentActivity: DEMO_PLATFORM_AUDIT_EVENTS,
  };
}

export function getDemoOrganization(id: string): BackendPlatformOrganization | undefined {
  return DEMO_PLATFORM_ORGANIZATIONS.find((o) => o.id === id);
}

export function getDemoOrganizationUsers(organizationId: string): PlatformUser[] {
  return DEMO_PLATFORM_USERS.filter((u) => u.organization_id === organizationId);
}

export function getDemoOrganizationSubscriptions(organizationId: string): SubscriptionResponse[] {
  return DEMO_PLATFORM_SUBSCRIPTIONS.filter((s) => s.organization_id === organizationId);
}

export function getDemoOrganizationEntitlements(organizationId: string): EntitlementResolutionResponse {
  const org = getDemoOrganization(organizationId);
  const sub = DEMO_PLATFORM_SUBSCRIPTIONS.find((s) => s.organization_id === organizationId);
  const plan = DEMO_PLATFORM_PLANS.find((p) => p.id === sub?.plan_id);

  if (!org || org.status === "SUSPENDED") {
    return {
      organization_id: organizationId,
      resolution_status: "SUSPENDED",
      organization_status: org?.status ?? "UNKNOWN",
      subscription_id: sub?.id ?? null,
      subscription_status: sub?.status ?? null,
      plan_id: plan?.id ?? null,
      plan_code: plan?.code ?? null,
      plan_name: plan?.name ?? null,
      effective_features: {},
      usage_limits: [],
      reason: "Organization is SUSPENDED. All operational entitlements denied.",
    };
  }

  const effectiveFeatures: Record<string, boolean> = {
    drone_fleet_management: true,
    work_order_management: true,
    compliance_reporting: true,
    audit_logging: true,
    release_readiness: plan?.code === "professional" || plan?.code === "enterprise",
    flight_telemetry: plan?.code === "professional" || plan?.code === "enterprise",
    battery_analytics: plan?.code === "professional" || plan?.code === "enterprise",
    lisa_ai_copilot: plan?.code === "enterprise",
    procurement_management: plan?.code === "enterprise",
  };

  return {
    organization_id: organizationId,
    resolution_status: "ACTIVE",
    organization_status: org.status,
    subscription_id: sub?.id ?? null,
    subscription_status: sub?.status ?? null,
    plan_id: plan?.id ?? null,
    plan_code: plan?.code ?? null,
    plan_name: plan?.name ?? null,
    effective_features: effectiveFeatures,
    usage_limits: [
      {
        feature_key: "fleet_limits",
        limit_key: "max_drones",
        limit_value: plan?.code === "enterprise" ? null : 20,
        is_unlimited: plan?.code === "enterprise",
      },
      {
        feature_key: "user_seats",
        limit_key: "max_users",
        limit_value: plan?.code === "enterprise" ? null : 15,
        is_unlimited: plan?.code === "enterprise",
      },
    ],
    reason: `Subscription ${sub?.id ?? ""} on plan ${plan?.code ?? ""} is active.`,
  };
}
