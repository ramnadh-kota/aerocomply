from app.core.permissions import Permission, Role, permissions_for_roles


def test_super_admin_has_all_permissions():
    granted = permissions_for_roles([Role.SUPER_ADMIN.value])
    assert granted == {p.value for p in Permission}


def test_viewer_cannot_write():
    granted = permissions_for_roles([Role.VIEWER.value])
    assert Permission.AIRCRAFT_READ.value in granted
    assert Permission.AIRCRAFT_WRITE.value not in granted
    assert Permission.COMPLIANCE_DECIDE.value not in granted


def test_unknown_role_grants_nothing():
    assert permissions_for_roles(["NOT_A_REAL_ROLE"]) == set()


def test_maintenance_engineer_cannot_decide_compliance():
    granted = permissions_for_roles([Role.MAINTENANCE_ENGINEER.value])
    assert Permission.COMPLIANCE_DECIDE.value not in granted
    assert Permission.EVIDENCE_WRITE.value in granted


def test_roles_combine_permissions():
    granted = permissions_for_roles([Role.VIEWER.value, Role.MAINTENANCE_ENGINEER.value])
    assert Permission.EVIDENCE_WRITE.value in granted
    assert Permission.AIRCRAFT_READ.value in granted
