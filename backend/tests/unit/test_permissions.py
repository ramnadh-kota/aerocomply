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


# Phase 2 of the WorkOrder lifecycle feature: WORK_ORDER_READ/CREATE/UPDATE/
# DELETE/RESTORE replace the prior reuse of AIRCRAFT_READ/AIRCRAFT_WRITE on
# app/api/v1/work_orders.py's routes. WORK_ORDER_DELETE/WORK_ORDER_RESTORE
# are granted here to complete the authorization boundary ahead of the
# delete/restore endpoints themselves, which do not exist yet.
def test_org_admin_has_full_work_order_authority():
    granted = permissions_for_roles([Role.ORG_ADMIN.value])
    assert Permission.WORK_ORDER_READ.value in granted
    assert Permission.WORK_ORDER_CREATE.value in granted
    assert Permission.WORK_ORDER_UPDATE.value in granted
    assert Permission.WORK_ORDER_DELETE.value in granted
    assert Permission.WORK_ORDER_RESTORE.value in granted


def test_camo_manager_has_full_work_order_authority():
    granted = permissions_for_roles([Role.CAMO_MANAGER.value])
    assert Permission.WORK_ORDER_READ.value in granted
    assert Permission.WORK_ORDER_CREATE.value in granted
    assert Permission.WORK_ORDER_UPDATE.value in granted
    assert Permission.WORK_ORDER_DELETE.value in granted
    assert Permission.WORK_ORDER_RESTORE.value in granted


def test_maintenance_engineer_can_operate_but_not_delete_or_restore_work_order():
    granted = permissions_for_roles([Role.MAINTENANCE_ENGINEER.value])
    assert Permission.WORK_ORDER_READ.value in granted
    assert Permission.WORK_ORDER_CREATE.value in granted
    assert Permission.WORK_ORDER_UPDATE.value in granted
    assert Permission.WORK_ORDER_DELETE.value not in granted
    assert Permission.WORK_ORDER_RESTORE.value not in granted


def test_quality_manager_can_operate_but_not_delete_or_restore_work_order():
    granted = permissions_for_roles([Role.QUALITY_MANAGER.value])
    assert Permission.WORK_ORDER_READ.value in granted
    assert Permission.WORK_ORDER_CREATE.value in granted
    assert Permission.WORK_ORDER_UPDATE.value in granted
    assert Permission.WORK_ORDER_DELETE.value not in granted
    assert Permission.WORK_ORDER_RESTORE.value not in granted


def test_viewer_can_only_read_work_order():
    granted = permissions_for_roles([Role.VIEWER.value])
    assert Permission.WORK_ORDER_READ.value in granted
    assert Permission.WORK_ORDER_CREATE.value not in granted
    assert Permission.WORK_ORDER_UPDATE.value not in granted
    assert Permission.WORK_ORDER_DELETE.value not in granted
    assert Permission.WORK_ORDER_RESTORE.value not in granted
