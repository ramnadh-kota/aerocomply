"""RBAC permission catalog.

Roles map to permission strings. Permission checks happen at the service layer
(see app.core.deps.require_permission), never only in the frontend.
"""

from enum import StrEnum


class Permission(StrEnum):
    AIRCRAFT_READ = "aircraft:read"
    AIRCRAFT_WRITE = "aircraft:write"
    REGULATION_READ = "regulation:read"
    REGULATION_WRITE = "regulation:write"
    REGULATION_INGEST = "regulation:ingest"
    COMPLIANCE_ASSESS = "compliance:assess"
    COMPLIANCE_DECIDE = "compliance:decide"  # accept/override a system determination
    EVIDENCE_READ = "evidence:read"
    EVIDENCE_WRITE = "evidence:upload"
    INSPECTION_READ = "inspection:read"
    # Covers both creating/managing an inspection requirement and performing
    # the transition (including RII sign-off) — same single-permission shape
    # as EVIDENCE_WRITE above; the RII independence rule is enforced in
    # app/services/inspection_service.py regardless of who holds this grant.
    INSPECTION_WRITE = "inspection:write"
    USER_MANAGE = "user:manage"
    ORG_MANAGE = "org:manage"
    AUDIT_READ = "audit:read"
    PART_READ = "part:read"
    PART_WRITE = "part:write"
    VENDOR_READ = "vendor:read"
    VENDOR_WRITE = "vendor:write"
    PROCUREMENT_READ = "procurement:read"
    PROCUREMENT_WRITE = "procurement:write"
    # Separate from PROCUREMENT_WRITE deliberately: approving a procurement
    # request is a distinct authority from creating/editing one, enforced both
    # here (who can hold the grant) and in procurement_service (an approver
    # can never approve their own request, regardless of grant).
    PROCUREMENT_APPROVE = "procurement:approve"
    TECHNICIAN_READ = "technician:read"
    # Granting/revoking a qualification, and assigning a technician to a
    # task, are both maintenance-ownership actions — same grant, same
    # reasoning as PART_WRITE below.
    TECHNICIAN_WRITE = "technician:write"
    ASSESSMENT_READ = "assessment:read"
    # Creating/running an assessment reads across the whole operational
    # graph and writes durable snapshot history — restricted to the same
    # management-tier roles that hold COMPLIANCE_ASSESS/PROCUREMENT_APPROVE,
    # not to MAINTENANCE_ENGINEER/VIEWER.
    ASSESSMENT_WRITE = "assessment:write"
    # Phase 18.4: general physical-site (hangar/workshop/office/store/...)
    # management -- deliberately its own permission, not reused from
    # PART_READ/PART_WRITE, because Facility is not an inventory concept
    # (see app/models/facility.py's module docstring for why it is a
    # separate table from Warehouse, which PART_* already gates).
    FACILITY_READ = "facility:read"
    FACILITY_WRITE = "facility:write"
    # Phase 18.6: covers the whole drone operations vertical slice (drone,
    # battery, component, flight, deployment readiness) under one grant,
    # mirroring AIRCRAFT_READ/WRITE's role distribution -- not split into
    # DRONE_READ/BATTERY_READ/FLIGHT_READ/etc, since all of it is the same
    # "who operates this asset" authority (see app/api/v1/assets.py's own
    # comment anticipating this: "revisit once a second AssetType is real").
    DRONE_READ = "drone:read"
    DRONE_WRITE = "drone:write"
    # Platform-level cross-tenant administration (create/activate/suspend
    # organizations, create a customer's first admin, view platform-wide
    # audit events). Deliberately its own permission, never bundled into
    # ORG_ADMIN's grant set — an org admin manages their own tenant only.
    PLATFORM_MANAGE = "platform:manage"
    # M6: narrower than PLATFORM_MANAGE. Ordinary platform administration
    # (subscription CRUD, restrictive overrides/limits) only needs
    # PLATFORM_MANAGE. Anything that would EXPAND a tenant's effective
    # entitlements beyond what their plan already grants (see
    # app/services/tenant_entitlement_admin_service.py's classification
    # function) additionally requires this permission. Deliberately its own
    # permission per M4's recommendation, so the code stays structurally
    # correct even though today only PLATFORM_ADMIN holds it (see
    # ROLE_PERMISSIONS below for why it is not yet a separately-grantable
    # tier).
    PLATFORM_ENTITLEMENT_OVERRIDE = "platform:entitlement_override"
    # Phase 2 of the WorkOrder lifecycle feature: dedicated permissions
    # replacing the prior reuse of AIRCRAFT_READ/AIRCRAFT_WRITE on
    # app/api/v1/work_orders.py's routes. WORK_ORDER_DELETE/WORK_ORDER_RESTORE
    # exist now purely to complete the authorization boundary ahead of time —
    # no delete/restore endpoint exists yet (that is a later phase); no role
    # below is granted either until that behavior actually ships.
    WORK_ORDER_READ = "work_order:read"
    WORK_ORDER_CREATE = "work_order:create"
    WORK_ORDER_UPDATE = "work_order:update"
    WORK_ORDER_DELETE = "work_order:delete"
    WORK_ORDER_RESTORE = "work_order:restore"


class Role(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    COMPLIANCE_MANAGER = "COMPLIANCE_MANAGER"
    CAMO_MANAGER = "CAMO_MANAGER"
    QUALITY_MANAGER = "QUALITY_MANAGER"
    MAINTENANCE_ENGINEER = "MAINTENANCE_ENGINEER"
    VIEWER = "VIEWER"
    # Platform operator staff — NOT a customer-organization role. A user
    # holding this role still belongs to exactly one organization (the
    # platform operator's own), but PLATFORM_MANAGE grants them access to
    # cross-tenant /platform/* endpoints that intentionally do not filter
    # by their own organization_id.
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    # M15: the "PLATFORM_MANAGE-only staff tier" anticipated by M6/M14's
    # comments (see ROLE_PERMISSIONS below). Can administer day-to-day
    # tenant lifecycle (organizations, subscriptions, restrictive/neutral
    # overrides and limits) and can FILE a governance ApprovalRequest for an
    # expansive change, but cannot hold PLATFORM_ENTITLEMENT_OVERRIDE and so
    # cannot directly execute an expansive mutation nor approve an
    # ApprovalRequest that would (approval_service.approve_approval_request
    # calls straight into tenant_entitlement_admin_service's existing
    # require_expansion_permission_if_needed check, so this falls out of the
    # existing enforcement with no new bespoke rule).
    PLATFORM_STAFF = "PLATFORM_STAFF"


ALL_PERMISSIONS = {p.value for p in Permission}

# PART_READ/VENDOR_READ reasoning: granted alongside AIRCRAFT_READ/EVIDENCE_READ
# on every role, including VIEWER — parts and vendor records are reference/
# inventory data that every operational role plausibly needs to see (e.g. to
# check part availability before requesting work), mirroring how broadly
# AIRCRAFT_READ is already granted.
#
# PART_WRITE/VENDOR_WRITE reasoning: restricted to the roles that actually own
# inventory and supplier relationships in an MRO org — ORG_ADMIN (full admin
# authority) and CAMO_MANAGER (owns continuing-airworthiness/maintenance
# planning, the natural owner of parts stock and vendor approval status).
# COMPLIANCE_MANAGER, QUALITY_MANAGER, MAINTENANCE_ENGINEER, and VIEWER get
# read-only: none of those roles are inventory/procurement owners in this
# slice (procurement workflows are explicitly out of scope for M3).
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SUPER_ADMIN: set(Permission),
    Role.ORG_ADMIN: {
        Permission.AIRCRAFT_READ,
        Permission.AIRCRAFT_WRITE,
        Permission.REGULATION_READ,
        Permission.COMPLIANCE_ASSESS,
        Permission.COMPLIANCE_DECIDE,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_WRITE,
        Permission.INSPECTION_READ,
        Permission.INSPECTION_WRITE,
        Permission.USER_MANAGE,
        Permission.ORG_MANAGE,
        Permission.AUDIT_READ,
        Permission.PART_READ,
        Permission.PART_WRITE,
        Permission.VENDOR_READ,
        Permission.VENDOR_WRITE,
        Permission.PROCUREMENT_READ,
        Permission.PROCUREMENT_WRITE,
        Permission.PROCUREMENT_APPROVE,
        Permission.TECHNICIAN_READ,
        Permission.TECHNICIAN_WRITE,
        Permission.ASSESSMENT_READ,
        Permission.ASSESSMENT_WRITE,
        Permission.FACILITY_READ,
        Permission.FACILITY_WRITE,
        Permission.DRONE_READ,
        Permission.DRONE_WRITE,
        Permission.WORK_ORDER_READ,
        Permission.WORK_ORDER_CREATE,
        Permission.WORK_ORDER_UPDATE,
        Permission.WORK_ORDER_DELETE,
        Permission.WORK_ORDER_RESTORE,
    },
    Role.COMPLIANCE_MANAGER: {
        Permission.AIRCRAFT_READ,
        Permission.REGULATION_READ,
        Permission.REGULATION_WRITE,
        Permission.REGULATION_INGEST,
        Permission.COMPLIANCE_ASSESS,
        Permission.COMPLIANCE_DECIDE,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_WRITE,
        Permission.INSPECTION_READ,
        Permission.INSPECTION_WRITE,
        Permission.AUDIT_READ,
        Permission.PART_READ,
        Permission.VENDOR_READ,
        Permission.PROCUREMENT_READ,
        Permission.TECHNICIAN_READ,
        Permission.ASSESSMENT_READ,
        Permission.ASSESSMENT_WRITE,
        Permission.FACILITY_READ,
        Permission.DRONE_READ,
    },
    Role.CAMO_MANAGER: {
        Permission.AIRCRAFT_READ,
        Permission.AIRCRAFT_WRITE,
        Permission.REGULATION_READ,
        Permission.COMPLIANCE_ASSESS,
        Permission.COMPLIANCE_DECIDE,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_WRITE,
        Permission.INSPECTION_READ,
        Permission.INSPECTION_WRITE,
        Permission.PART_READ,
        Permission.PART_WRITE,
        Permission.VENDOR_READ,
        Permission.VENDOR_WRITE,
        Permission.PROCUREMENT_READ,
        Permission.PROCUREMENT_WRITE,
        Permission.PROCUREMENT_APPROVE,
        Permission.TECHNICIAN_READ,
        Permission.TECHNICIAN_WRITE,
        Permission.ASSESSMENT_READ,
        Permission.ASSESSMENT_WRITE,
        Permission.FACILITY_READ,
        Permission.FACILITY_WRITE,
        Permission.DRONE_READ,
        Permission.DRONE_WRITE,
        Permission.WORK_ORDER_READ,
        Permission.WORK_ORDER_CREATE,
        Permission.WORK_ORDER_UPDATE,
        Permission.WORK_ORDER_DELETE,
        Permission.WORK_ORDER_RESTORE,
    },
    Role.QUALITY_MANAGER: {
        Permission.AIRCRAFT_READ,
        Permission.REGULATION_READ,
        Permission.COMPLIANCE_ASSESS,
        Permission.EVIDENCE_READ,
        Permission.INSPECTION_READ,
        Permission.INSPECTION_WRITE,
        Permission.AUDIT_READ,
        Permission.PART_READ,
        Permission.VENDOR_READ,
        Permission.PROCUREMENT_READ,
        Permission.TECHNICIAN_READ,
        Permission.ASSESSMENT_READ,
        Permission.ASSESSMENT_WRITE,
        Permission.FACILITY_READ,
        Permission.DRONE_READ,
        Permission.WORK_ORDER_READ,
        Permission.WORK_ORDER_CREATE,
        Permission.WORK_ORDER_UPDATE,
    },
    Role.MAINTENANCE_ENGINEER: {
        Permission.AIRCRAFT_READ,
        Permission.REGULATION_READ,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_WRITE,
        Permission.INSPECTION_READ,
        Permission.PART_READ,
        Permission.VENDOR_READ,
        Permission.PROCUREMENT_READ,
        Permission.PROCUREMENT_WRITE,
        Permission.TECHNICIAN_READ,
        Permission.TECHNICIAN_WRITE,
        Permission.ASSESSMENT_READ,
        Permission.FACILITY_READ,
        Permission.DRONE_READ,
        Permission.WORK_ORDER_READ,
        Permission.WORK_ORDER_CREATE,
        Permission.WORK_ORDER_UPDATE,
    },
    Role.VIEWER: {
        Permission.AIRCRAFT_READ,
        Permission.REGULATION_READ,
        Permission.EVIDENCE_READ,
        Permission.INSPECTION_READ,
        Permission.FACILITY_READ,
        Permission.DRONE_READ,
        Permission.PART_READ,
        Permission.VENDOR_READ,
        Permission.PROCUREMENT_READ,
        Permission.TECHNICIAN_READ,
        Permission.ASSESSMENT_READ,
        Permission.WORK_ORDER_READ,
    },
    # Deliberately minimal: platform staff can administer tenants but do not
    # implicitly gain any customer operational-data permission — a platform
    # admin who also needs to view a customer's MRO data would need a
    # separate, explicit grant within that tenant, same as any other user.
    # M15: PLATFORM_ADMIN keeps both permissions -- it is the only platform
    # role that can directly execute an expansive entitlement mutation or
    # approve an ApprovalRequest for one.
    Role.PLATFORM_ADMIN: {
        Permission.PLATFORM_MANAGE,
        Permission.PLATFORM_ENTITLEMENT_OVERRIDE,
    },
    # M15: the narrower staff tier anticipated by M6/M14 -- PLATFORM_MANAGE
    # only, deliberately without PLATFORM_ENTITLEMENT_OVERRIDE. A
    # PLATFORM_STAFF user can administer ordinary platform/tenant-lifecycle
    # concerns and can create an ApprovalRequest for an expansive change,
    # but require_expansion_permission_if_needed
    # (tenant_entitlement_admin_service.py) refuses them both a direct
    # expansive mutation and an attempt to approve one -- no separate check
    # was added for this, it falls out of the existing per-permission gate.
    Role.PLATFORM_STAFF: {
        Permission.PLATFORM_MANAGE,
    },
}


def permissions_for_roles(roles: list[str]) -> set[str]:
    result: set[str] = set()
    for role_name in roles:
        try:
            role = Role(role_name)
        except ValueError:
            continue
        result |= {p.value for p in ROLE_PERMISSIONS.get(role, set())}
    return result
