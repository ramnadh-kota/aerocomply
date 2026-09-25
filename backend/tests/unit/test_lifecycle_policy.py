"""Unit tests for the Kota Aerospace Data Lifecycle & Deletion Governance
policy registry (app/core/lifecycle_policy.py).

This is pure policy metadata plus pure functions -- no DB, no mocks needed
beyond the registry module itself.
"""

import pytest

from app.core import lifecycle_policy
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.lifecycle_policy import (
    ENTITY_LIFECYCLE_POLICIES,
    DeletionMechanism,
    LifecycleCategory,
)


class TestRegistryIntegrity:
    def test_every_entry_has_a_category_and_mechanism(self):
        for entity_type, policy in ENTITY_LIFECYCLE_POLICIES.items():
            assert policy.entity_type == entity_type
            assert isinstance(policy.category, LifecycleCategory)
            assert isinstance(policy.deletion_mechanism, DeletionMechanism)

    def test_inherits_lifecycle_from_always_points_at_a_registered_entity(self):
        for policy in ENTITY_LIFECYCLE_POLICIES.values():
            if policy.inherits_lifecycle_from is not None:
                assert policy.inherits_lifecycle_from in ENTITY_LIFECYCLE_POLICIES

    def test_retention_protected_entities_never_permit_any_delete_action(self):
        for policy in ENTITY_LIFECYCLE_POLICIES.values():
            if policy.category == LifecycleCategory.RETENTION_PROTECTED:
                assert policy.tenant_delete_permitted is False
                assert policy.restore_permitted is False
                assert policy.permanent_delete_permitted is False

    def test_expected_entities_are_all_registered(self):
        expected = {
            "ORGANIZATION", "ASSET", "AIRCRAFT", "DRONE", "HELICOPTER", "EVTOL",
            "USER", "COMPONENT", "BATTERY", "WORKORDER", "VENDOR", "FACILITY",
            "FLIGHT", "INSPECTIONREQUIREMENT", "COMPLIANCEASSESSMENT",
            "MAINTENANCEACCOMPLISHMENT", "FINDING", "EVIDENCE", "EVIDENCEFILE",
            "DEFERREDITEM", "REGULATORYDOCUMENT", "MISSION", "AOGEVENT",
            "AOGBLOCKER", "APPROVALREQUEST", "PART", "PURCHASEORDER",
            "PROCUREMENTREQUEST", "TECHNICIANQUALIFICATION", "TASK", "IMPORTJOB",
            "INVENTORYTRANSACTION", "INSTALLATIONHISTORY",
            "LISACONVERSATIONCONTEXT", "AUDITEVENT", "USERROLE",
            "TENANTFEATUREOVERRIDE", "TENANTUSAGELIMIT", "VENDORPARTAVAILABILITY",
            "PARTREQUIREMENT", "CONFIGURATIONS",
        }
        assert expected <= set(ENTITY_LIFECYCLE_POLICIES.keys())


class TestGetAndResolvePolicy:
    def test_get_policy_is_case_insensitive(self):
        assert lifecycle_policy.get_policy("asset") is lifecycle_policy.get_policy("ASSET")

    def test_get_policy_returns_none_for_unknown_entity(self):
        assert lifecycle_policy.get_policy("NOT_A_REAL_ENTITY") is None

    def test_resolve_policy_raises_not_found_for_unknown_entity(self):
        with pytest.raises(NotFoundError):
            lifecycle_policy.resolve_policy("NOT_A_REAL_ENTITY")

    def test_resolve_policy_on_a_non_inheriting_entity_returns_itself(self):
        resolved = lifecycle_policy.resolve_policy("ASSET")
        assert resolved.entity_type == "ASSET"


class TestAircraftDroneHelicopterEvtolInheritFromAsset:
    """The specific, explicitly-required check: these four must resolve to
    Asset's OWN policy object, not carry an independent lifecycle."""

    @pytest.mark.parametrize("entity_type", ["AIRCRAFT", "DRONE", "HELICOPTER", "EVTOL"])
    def test_resolves_to_assets_policy(self, entity_type):
        own_entry = lifecycle_policy.get_policy(entity_type)
        assert own_entry.deletion_mechanism == DeletionMechanism.INHERITED
        assert own_entry.inherits_lifecycle_from == "ASSET"

        resolved = lifecycle_policy.resolve_policy(entity_type)
        asset_policy = lifecycle_policy.resolve_policy("ASSET")
        assert resolved is asset_policy
        assert resolved.entity_type == "ASSET"

    @pytest.mark.parametrize("entity_type", ["AIRCRAFT", "DRONE", "HELICOPTER", "EVTOL"])
    def test_assert_guards_succeed_via_inheritance(self, entity_type):
        # These must not raise -- they inherit Asset's implemented+permitted policy.
        lifecycle_policy.assert_tenant_delete_permitted(entity_type)
        lifecycle_policy.assert_restore_permitted(entity_type)
        lifecycle_policy.assert_permanent_delete_permitted(entity_type)


class TestTaskAndPartRequirementInheritFromWorkOrder:
    @pytest.mark.parametrize("entity_type", ["TASK", "PARTREQUIREMENT"])
    def test_resolves_to_work_order_policy(self, entity_type):
        resolved = lifecycle_policy.resolve_policy(entity_type)
        assert resolved.entity_type == "WORKORDER"

    @pytest.mark.parametrize("entity_type", ["TASK", "PARTREQUIREMENT"])
    def test_assert_guard_permits_via_work_order_now_implemented(self, entity_type):
        # WorkOrder is category A (tenant_delete_permitted=True) and is now
        # implemented -- Task/PartRequirement resolve to WorkOrder's policy,
        # so the guard succeeds (Task/PartRequirement still have no delete
        # route of their own; this only proves the resolved policy permits
        # it, matching WorkOrder's own implemented=True state).
        policy = lifecycle_policy.assert_tenant_delete_permitted(entity_type)
        assert policy.entity_type == "WORKORDER"


class TestAogBlockerInheritsFromAogEvent:
    def test_resolves_to_aog_event_policy(self):
        resolved = lifecycle_policy.resolve_policy("AOGBLOCKER")
        assert resolved.entity_type == "AOGEVENT"


class TestCategoryCCannotBecomeDeletableMerelyByBeingRegistered:
    """The explicit testing requirement: registering a retention-protected
    entity in the policy catalog must never, by itself, grant it any delete
    capability -- every guard must independently refuse it."""

    @pytest.mark.parametrize(
        "entity_type",
        [
            "FLIGHT", "INSPECTIONREQUIREMENT", "COMPLIANCEASSESSMENT",
            "MAINTENANCEACCOMPLISHMENT", "FINDING", "EVIDENCE", "EVIDENCEFILE",
            "DEFERREDITEM", "REGULATORYDOCUMENT", "APPROVALREQUEST",
            "TECHNICIANQUALIFICATION", "IMPORTJOB", "INVENTORYTRANSACTION",
            "INSTALLATIONHISTORY", "AUDITEVENT",
        ],
    )
    def test_category_c_entities_refuse_every_delete_action(self, entity_type):
        policy = lifecycle_policy.get_policy(entity_type)
        assert policy.category == LifecycleCategory.RETENTION_PROTECTED
        assert policy.retention_protected is True

        with pytest.raises((ConflictError, ForbiddenError)):
            lifecycle_policy.assert_tenant_delete_permitted(entity_type)
        with pytest.raises((ConflictError, ForbiddenError)):
            lifecycle_policy.assert_restore_permitted(entity_type)
        with pytest.raises((ConflictError, ForbiddenError)):
            lifecycle_policy.assert_permanent_delete_permitted(entity_type)

    @pytest.mark.parametrize(
        "entity_type",
        [
            "FLIGHT", "INSPECTIONREQUIREMENT", "COMPLIANCEASSESSMENT",
            "MAINTENANCEACCOMPLISHMENT", "FINDING", "EVIDENCE", "EVIDENCEFILE",
            "DEFERREDITEM", "REGULATORYDOCUMENT", "APPROVALREQUEST",
            "TECHNICIANQUALIFICATION", "IMPORTJOB", "INVENTORYTRANSACTION",
            "INSTALLATIONHISTORY", "AUDITEVENT",
        ],
    )
    def test_category_c_entities_refused_from_the_deletion_queue(self, entity_type):
        with pytest.raises(ForbiddenError) as exc:
            lifecycle_policy.assert_visible_in_deletion_queue(entity_type)
        assert exc.value.code == "retention_protected"


class TestUserRemainsDeactivateOnlyAndNeverDeletable:
    def test_user_policy_forbids_every_delete_action(self):
        policy = lifecycle_policy.get_policy("USER")
        assert policy.category == LifecycleCategory.ARCHIVE_STATUS
        assert policy.deletion_mechanism == DeletionMechanism.STATUS_TRANSITION
        assert policy.retention_protected is True  # never deletable, even though category is B not C
        with pytest.raises(ForbiddenError):
            lifecycle_policy.assert_tenant_delete_permitted("USER")
        with pytest.raises(ForbiddenError):
            lifecycle_policy.assert_permanent_delete_permitted("USER")


class TestComponentAndBatteryRemainStatusDriven:
    @pytest.mark.parametrize("entity_type", ["COMPONENT", "BATTERY"])
    def test_status_driven_not_soft_deletable(self, entity_type):
        policy = lifecycle_policy.get_policy(entity_type)
        assert policy.category == LifecycleCategory.ARCHIVE_STATUS
        assert policy.deletion_mechanism == DeletionMechanism.STATUS_TRANSITION
        with pytest.raises(ForbiddenError):
            lifecycle_policy.assert_tenant_delete_permitted(entity_type)


class TestFacilityIsExplicitlyUnresolved:
    def test_facility_is_unresolved_not_silently_a_or_b(self):
        policy = lifecycle_policy.get_policy("FACILITY")
        assert policy.category == LifecycleCategory.UNRESOLVED
        assert policy.implemented is False
        assert policy.tenant_delete_permitted is False
        # Must fail closed -- an UNRESOLVED entity has no permitted action.
        with pytest.raises((ConflictError, ForbiddenError)):
            lifecycle_policy.assert_tenant_delete_permitted("FACILITY")


class TestEvidenceFileMismatchIsDocumentedNotFixed:
    def test_evidence_file_is_not_implemented_and_notes_the_mismatch(self):
        policy = lifecycle_policy.get_policy("EVIDENCEFILE")
        assert policy.implemented is False
        assert "mismatch" in policy.notes.lower()
        assert policy.category == LifecycleCategory.RETENTION_PROTECTED


class TestConfigurationsIsNotARealModel:
    def test_configurations_documents_it_is_not_a_model(self):
        policy = lifecycle_policy.get_policy("CONFIGURATIONS")
        assert policy.category == LifecycleCategory.NOT_APPLICABLE
        assert "no model named" in policy.notes.lower()


class TestOrganizationAndAssetImplementedAndPermitted:
    @pytest.mark.parametrize("entity_type", ["ASSET", "ORGANIZATION"])
    def test_all_three_actions_permitted_and_implemented(self, entity_type):
        policy = lifecycle_policy.get_policy(entity_type)
        assert policy.implemented is True
        assert policy.tenant_delete_permitted is True
        assert policy.restore_permitted is True
        assert policy.permanent_delete_permitted is True
        assert policy.permanent_delete_requires_dependency_check is True
        # Must not raise.
        lifecycle_policy.assert_tenant_delete_permitted(entity_type)
        lifecycle_policy.assert_restore_permitted(entity_type)
        lifecycle_policy.assert_permanent_delete_permitted(entity_type)
        lifecycle_policy.assert_visible_in_deletion_queue(entity_type)


class TestNotYetImplementedButEligibleEntitiesAreNotForbiddenFromTheQueue:
    """A category A/D entity that isn't built yet (Vendor, ...) should be
    allowed through the deletion-queue's entity_type filter (and simply
    contribute zero rows, since no data source exists) -- it is a "not
    built" state, not a "forbidden" one, unlike a Category C entity.

    WorkOrder has since been implemented (migration 0042, deletion_service.
    soft_delete_work_order/permanently_delete_work_order,
    restoration_service.restore_work_order) -- it is covered separately
    below rather than parametrized alongside Vendor."""

    @pytest.mark.parametrize("entity_type", ["WORKORDER", "VENDOR"])
    def test_queue_visibility_guard_does_not_raise(self, entity_type):
        lifecycle_policy.assert_visible_in_deletion_queue(entity_type)  # must not raise

    def test_vendor_delete_action_still_refused_as_not_implemented(self):
        with pytest.raises(ConflictError) as exc:
            lifecycle_policy.assert_tenant_delete_permitted("VENDOR")
        assert exc.value.code == "lifecycle_not_implemented"

    def test_work_order_delete_action_now_permitted(self):
        policy = lifecycle_policy.assert_tenant_delete_permitted("WORKORDER")
        assert policy.entity_type == "WORKORDER"
        assert policy.implemented is True
