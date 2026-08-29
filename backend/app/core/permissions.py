"""RBAC permission catalog.

Roles map to permission strings. Permission checks happen at the service layer
(see app.core.deps.require_permission), never only in the frontend.
"""
from enum import Enum


class Permission(str, Enum):
    AIRCRAFT_READ = "aircraft:read"
    AIRCRAFT_WRITE = "aircraft:write"
    REGULATION_READ = "regulation:read"
    REGULATION_WRITE = "regulation:write"
    REGULATION_INGEST = "regulation:ingest"
    COMPLIANCE_ASSESS = "compliance:assess"
    COMPLIANCE_DECIDE = "compliance:decide"  # accept/override a system determination
    EVIDENCE_READ = "evidence:read"
    EVIDENCE_WRITE = "evidence:upload"
    USER_MANAGE = "user:manage"
    ORG_MANAGE = "org:manage"
    AUDIT_READ = "audit:read"


class Role(str, Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    ORG_ADMIN = "ORG_ADMIN"
    COMPLIANCE_MANAGER = "COMPLIANCE_MANAGER"
    CAMO_MANAGER = "CAMO_MANAGER"
    QUALITY_MANAGER = "QUALITY_MANAGER"
    MAINTENANCE_ENGINEER = "MAINTENANCE_ENGINEER"
    VIEWER = "VIEWER"


ALL_PERMISSIONS = {p.value for p in Permission}

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
        Permission.USER_MANAGE,
        Permission.ORG_MANAGE,
        Permission.AUDIT_READ,
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
        Permission.AUDIT_READ,
    },
    Role.CAMO_MANAGER: {
        Permission.AIRCRAFT_READ,
        Permission.AIRCRAFT_WRITE,
        Permission.REGULATION_READ,
        Permission.COMPLIANCE_ASSESS,
        Permission.COMPLIANCE_DECIDE,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_WRITE,
    },
    Role.QUALITY_MANAGER: {
        Permission.AIRCRAFT_READ,
        Permission.REGULATION_READ,
        Permission.COMPLIANCE_ASSESS,
        Permission.EVIDENCE_READ,
        Permission.AUDIT_READ,
    },
    Role.MAINTENANCE_ENGINEER: {
        Permission.AIRCRAFT_READ,
        Permission.REGULATION_READ,
        Permission.EVIDENCE_READ,
        Permission.EVIDENCE_WRITE,
    },
    Role.VIEWER: {
        Permission.AIRCRAFT_READ,
        Permission.REGULATION_READ,
        Permission.EVIDENCE_READ,
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
