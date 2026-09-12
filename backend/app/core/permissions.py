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


class Role(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    COMPLIANCE_MANAGER = "COMPLIANCE_MANAGER"
    CAMO_MANAGER = "CAMO_MANAGER"
    QUALITY_MANAGER = "QUALITY_MANAGER"
    MAINTENANCE_ENGINEER = "MAINTENANCE_ENGINEER"
    VIEWER = "VIEWER"


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
    },
    Role.VIEWER: {
        Permission.AIRCRAFT_READ,
        Permission.REGULATION_READ,
        Permission.EVIDENCE_READ,
        Permission.INSPECTION_READ,
        Permission.PART_READ,
        Permission.VENDOR_READ,
        Permission.PROCUREMENT_READ,
        Permission.TECHNICIAN_READ,
        Permission.ASSESSMENT_READ,
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
