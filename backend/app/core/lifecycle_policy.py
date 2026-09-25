"""Kota Aerospace Data Lifecycle & Deletion Governance -- the entity policy
catalog behind the Platform Control Plane's soft-delete/restore/permanent-
delete system (app/services/deletion_service.py, restoration_service.py,
app/api/v1/platform.py's /platform/deleted-records/*).

Mirrors app/core/permissions.py's role: a static, importable catalog that
every layer consults instead of re-deciding policy inline. Where
permissions.py answers "what can this role do," this module answers "what
kind of lifecycle does this entity have, and what does that permit."

THIS IS POLICY METADATA, NOT AUTHORIZATION AND NOT A DELETE MECHANISM.
Registering an entity here does not create an endpoint, a SoftDeleteMixin
column, or a service function for it -- see EntityLifecyclePolicy.implemented
below. A service function that performs a real deletion/restoration MUST
call one of the assert_*_permitted guards in this module before acting;
until it does, an entity's registration here is purely documentation.

Categories (from the Kota Aerospace Data Lifecycle & Deletion Governance
policy pass):
    A -- SOFT_DELETE_RESTORE: tenant deletion hides it; Platform Admin can
         see and restore it; permanent deletion is Platform-only and
         (per-entity) dependency-controlled.
    B -- ARCHIVE_STATUS: the entity's own status enum already models
         "removed" (e.g. ComponentStatus.SCRAPPED, BatteryStatus.RETIRED,
         MissionStatus.CANCELLED). No generic soft-delete is layered on top
         -- adding one would create two competing "is this gone" signals.
    C -- RETENTION_PROTECTED: historical/compliance/safety/audit record.
         No tenant delete, no restore, no permanent delete, ever, by policy
         -- not merely "not implemented yet."
    D -- DEPENDENCY_CONTROLLED: a genuine future soft-delete/permanent-
         delete candidate, gated on dependency checks, not yet built.
    UNRESOLVED -- a deliberate, tracked policy decision that has not been
         made yet (see Facility below). Never silently defaults to A or B.
    NOT_APPLICABLE -- the identifier does not correspond to an independently
         user-deletable entity at all (a pure join/config/system table, or
         -- for "Configurations" -- not a real model in this codebase).

retention_protected is a SEPARATE boolean from category C: it answers
"should this never be permanently deleted," which can be true for a B
entity too (User is category B -- is_active is its whole lifecycle -- but
is also retention_protected, since deleting a User would break referential
integrity to every audit/work/evidence trail it's attributed to).
"""

from dataclasses import dataclass, field
from enum import StrEnum

from app.core.errors import ConflictError, ForbiddenError, NotFoundError


class LifecycleCategory(StrEnum):
    SOFT_DELETE_RESTORE = "A"
    ARCHIVE_STATUS = "B"
    RETENTION_PROTECTED = "C"
    DEPENDENCY_CONTROLLED = "D"
    # A recorded, tracked "we have not decided yet" -- see Facility. Never
    # used as a silent default; every entry below sets it explicitly or not
    # at all.
    UNRESOLVED = "UNRESOLVED"
    # The identifier is not an independently user-deletable entity (a pure
    # join/config/system table), or -- for "Configurations" -- not a real
    # model in this codebase at all.
    NOT_APPLICABLE = "NOT_APPLICABLE"


class DeletionMechanism(StrEnum):
    # SoftDeleteMixin-shaped: deleted_at/deleted_by/deletion_reason/
    # restored_at/restored_by (app/db/base.py), the Asset/Organization shape.
    SOFT_DELETE = "SOFT_DELETE"
    # The entity's own status enum already expresses "removed" (SCRAPPED,
    # RETIRED, CANCELLED, ...) -- no deleted_at concept at all.
    STATUS_TRANSITION = "STATUS_TRANSITION"
    # No tenant-facing removal action exists or should exist.
    NONE = "NONE"
    # Delegates entirely to another entity's policy -- see
    # inherits_lifecycle_from. The dependent has no lifecycle machinery of
    # its own (Aircraft never gets its own SoftDeleteMixin; it rides Asset's).
    INHERITED = "INHERITED"


@dataclass(frozen=True)
class EntityLifecyclePolicy:
    entity_type: str
    category: LifecycleCategory
    deletion_mechanism: DeletionMechanism

    # Policy targets -- what SHOULD eventually be true for this entity's
    # lifecycle, independent of whether the code exists yet.
    tenant_delete_permitted: bool
    restore_permitted: bool
    permanent_delete_permitted: bool
    permanent_delete_requires_dependency_check: bool
    retention_protected: bool

    # Whether a service function/endpoint/mixin ACTUALLY EXISTS today for
    # this entity's own delete/restore path. False for every entity except
    # Organization and Asset as of this policy-registry slice -- this is
    # the field that keeps "registered" from meaning "deletable." A future
    # guard (assert_tenant_delete_permitted, etc.) checks this in addition
    # to the policy-target booleans above.
    implemented: bool = False

    # Set only for an entity whose lifecycle is entirely delegated to
    # another entity's policy (Aircraft/Drone/Helicopter/eVTOL -> Asset;
    # Task/PartRequirement -> WorkOrder; AogBlocker -> AogEvent). Use
    # resolve_policy() to follow this to the effective policy rather than
    # reading a dependent entry's own booleans directly.
    inherits_lifecycle_from: str | None = None

    notes: str = field(default="")


def _asset_derived(entity_type: str, notes: str) -> EntityLifecyclePolicy:
    """Aircraft/Drone/Helicopter/eVTOL share this exact shape: no lifecycle
    of their own, fully delegated to Asset. Drone/Helicopter/eVTOL are not
    even separate tables (Asset.asset_type discriminates them -- see
    app/services/drone_service.py's own docstring), so for them this is
    trivially true. Aircraft IS a separate table (dual-write, see
    app/models/aircraft.py) but still has no SoftDeleteMixin of its own --
    aircraft_service.get_aircraft/list_aircraft instead outer-joins to its
    backing Asset and excludes rows whose Asset is soft-deleted. This
    function exists so all four entries stay identical by construction
    rather than by four people remembering to keep them in sync."""
    return EntityLifecyclePolicy(
        entity_type=entity_type,
        category=LifecycleCategory.SOFT_DELETE_RESTORE,
        deletion_mechanism=DeletionMechanism.INHERITED,
        tenant_delete_permitted=True,
        restore_permitted=True,
        permanent_delete_permitted=True,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=True,
        inherits_lifecycle_from="ASSET",
        notes=notes,
    )


# ---------------------------------------------------------------------------
# The registry. Only the entities named in the policy pass / this task's
# instructions. Do not add an entity here as a side effect of implementing
# its deletion later -- add it here FIRST, as a policy decision, then wire
# behavior to it.
# ---------------------------------------------------------------------------

ENTITY_LIFECYCLE_POLICIES: dict[str, EntityLifecyclePolicy] = {
    "ORGANIZATION": EntityLifecyclePolicy(
        entity_type="ORGANIZATION",
        category=LifecycleCategory.SOFT_DELETE_RESTORE,
        deletion_mechanism=DeletionMechanism.SOFT_DELETE,
        tenant_delete_permitted=True,
        restore_permitted=True,
        permanent_delete_permitted=True,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=True,
        notes=(
            "organization_id elsewhere (TenantScopedMixin) is a plain UUID, never a "
            "real FK -- permanently_delete_organization checks User/Asset counts in "
            "application code instead of relying on DB RESTRICT."
        ),
    ),
    "ASSET": EntityLifecyclePolicy(
        entity_type="ASSET",
        category=LifecycleCategory.SOFT_DELETE_RESTORE,
        deletion_mechanism=DeletionMechanism.SOFT_DELETE,
        tenant_delete_permitted=True,
        restore_permitted=True,
        permanent_delete_permitted=True,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=True,
        notes="Dependency check is real DB ondelete=RESTRICT (Flight, Component, WorkOrder, ...).",
    ),
    "AIRCRAFT": _asset_derived(
        "AIRCRAFT",
        "Separate table (dual-write with Asset) but no own SoftDeleteMixin -- "
        "aircraft_service.get_aircraft/list_aircraft outer-join to Asset and "
        "exclude rows whose backing Asset is soft-deleted. Do not add a second "
        "deleted_at here.",
    ),
    "DRONE": _asset_derived(
        "DRONE", "Not a separate table -- Asset.asset_type=DRONE. Lifecycle is Asset's, unconditionally."
    ),
    "HELICOPTER": _asset_derived(
        "HELICOPTER", "Not a separate table -- Asset.asset_type=HELICOPTER. Lifecycle is Asset's, unconditionally."
    ),
    "EVTOL": _asset_derived(
        "EVTOL", "Not a separate table -- Asset.asset_type=EVTOL. Lifecycle is Asset's, unconditionally."
    ),
    "USER": EntityLifecyclePolicy(
        entity_type="USER",
        category=LifecycleCategory.ARCHIVE_STATUS,
        deletion_mechanism=DeletionMechanism.STATUS_TRANSITION,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes=(
            "is_active toggle (PATCH /tenant/users/{id}/status) IS the whole lifecycle. "
            "Reactivation is that same toggle, not restoration_service -- there is no "
            "separate 'restore' concept for a User. Must never gain a delete path: "
            "referential integrity to audit events, assigned work, uploaded evidence."
        ),
    ),
    "COMPONENT": EntityLifecyclePolicy(
        entity_type="COMPONENT",
        category=LifecycleCategory.ARCHIVE_STATUS,
        deletion_mechanism=DeletionMechanism.STATUS_TRANSITION,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="ComponentStatus.SCRAPPED/REMOVED already model 'gone' -- serialized part traceability record.",
    ),
    "BATTERY": EntityLifecyclePolicy(
        entity_type="BATTERY",
        category=LifecycleCategory.ARCHIVE_STATUS,
        deletion_mechanism=DeletionMechanism.STATUS_TRANSITION,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="BatteryStatus.RETIRED already models 'gone' -- cycle-count/health history record.",
    ),
    "WORKORDER": EntityLifecyclePolicy(
        entity_type="WORKORDER",
        category=LifecycleCategory.SOFT_DELETE_RESTORE,
        deletion_mechanism=DeletionMechanism.SOFT_DELETE,
        tenant_delete_permitted=True,
        restore_permitted=True,
        permanent_delete_permitted=True,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=True,
        notes=(
            "IMPLEMENTED (migration 0042_soft_delete_work_orders.py; "
            "deletion_service.soft_delete_work_order/permanently_delete_work_order; "
            "restoration_service.restore_work_order). AogEvent/DeferredItem/Finding/"
            "InspectionRequirement/MaintenanceRequirement/PartRequirement/Task/"
            "ProcurementRequest all reference it via unmodified (non-RESTRICT) FKs -- "
            "permanent-delete dependency check is an explicit application-level COUNT "
            "across all 8, following Organization's app-level pattern rather than "
            "Asset's DB-RESTRICT pattern, since those FK ondelete values were "
            "deliberately left unchanged."
        ),
    ),
    "VENDOR": EntityLifecyclePolicy(
        entity_type="VENDOR",
        category=LifecycleCategory.SOFT_DELETE_RESTORE,
        deletion_mechanism=DeletionMechanism.SOFT_DELETE,
        tenant_delete_permitted=True,
        restore_permitted=True,
        permanent_delete_permitted=True,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=False,
        notes=(
            "NOT YET IMPLEMENTED. Cleanest low-risk candidate: no existing status "
            "field at all to conflict with. Dependents: ProcurementRequest, PurchaseOrder."
        ),
    ),
    "FACILITY": EntityLifecyclePolicy(
        entity_type="FACILITY",
        category=LifecycleCategory.UNRESOLVED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=False,
        notes=(
            "TODO / POLICY DECISION PENDING, deliberately not defaulted: Facility "
            "already has FacilityStatus.ACTIVE/INACTIVE, the closest existing analog "
            "to soft-delete anywhere in the codebase, which makes it genuinely "
            "ambiguous whether it should become a full category A entity (formal "
            "restore audit trail, Platform visibility) or stay category B (INACTIVE "
            "is already 'enough'). Asset has ondelete=RESTRICT to facilities.id. Do "
            "not implement until this is explicitly decided -- see the policy pass "
            "for the same ambiguity noted there."
        ),
    ),
    "FLIGHT": EntityLifecyclePolicy(
        entity_type="FLIGHT",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="Authoritative utilization source of truth (flight hours/cycles, battery cycle_count). No status field.",
    ),
    "INSPECTIONREQUIREMENT": EntityLifecyclePolicy(
        entity_type="INSPECTIONREQUIREMENT",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="No separate 'Inspection' model exists -- this is the actual entity. RII/safety-independence record.",
    ),
    "COMPLIANCEASSESSMENT": EntityLifecyclePolicy(
        entity_type="COMPLIANCEASSESSMENT",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="Core compliance-determination record.",
    ),
    "MAINTENANCEACCOMPLISHMENT": EntityLifecyclePolicy(
        entity_type="MAINTENANCEACCOMPLISHMENT",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="The due-status engine reads these as authoritative; deleting one could falsify an overdue determination.",
    ),
    "FINDING": EntityLifecyclePolicy(
        entity_type="FINDING",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="FindingStatus has no terminal 'deleted' value by design; FindingDisposition is a separate append-only trail.",
    ),
    "EVIDENCE": EntityLifecyclePolicy(
        entity_type="EVIDENCE",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="The Evidence record itself has no delete path (distinct from EvidenceFile below).",
    ),
    "EVIDENCEFILE": EntityLifecyclePolicy(
        entity_type="EVIDENCEFILE",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=False,
        notes=(
            "KNOWN MISMATCH, recorded not fixed (per instruction): EvidenceFile "
            "already carries its own bare `deleted_at` column ('Soft-delete marker "
            "for M16.6 -- no code path sets this yet') that predates SoftDeleteMixin "
            "and does NOT match its shape -- no deleted_by/deletion_reason/"
            "restored_at/restored_by. EvidenceFileStatus.DELETED is also a second, "
            "redundant signal for the same fact. A real hard-delete of a file "
            "already exists (DELETE /evidence/{id}/files/{file_id}, "
            "evidence_file_service.mark_deleted). Do not wire this entity into the "
            "unified deleted-records queue until that mismatch is reconciled -- "
            "explicitly left unchanged in this slice."
        ),
    ),
    "DEFERREDITEM": EntityLifecyclePolicy(
        entity_type="DEFERREDITEM",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="MEL/CDL regulatory record; DeferredItemStatus.CLOSED is its terminal state, not a deletion.",
    ),
    "REGULATORYDOCUMENT": EntityLifecyclePolicy(
        entity_type="REGULATORYDOCUMENT",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="RegulatoryDocumentSourceStatus.WITHDRAWN already models 'no longer current' without deleting the citation.",
    ),
    "MISSION": EntityLifecyclePolicy(
        entity_type="MISSION",
        category=LifecycleCategory.ARCHIVE_STATUS,
        deletion_mechanism=DeletionMechanism.STATUS_TRANSITION,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=False,
        notes="MissionStatus.CANCELLED is its terminal state. Flight.mission_id is ondelete=SET NULL (not RESTRICT). Low priority.",
    ),
    "AOGEVENT": EntityLifecyclePolicy(
        entity_type="AOGEVENT",
        category=LifecycleCategory.ARCHIVE_STATUS,
        deletion_mechanism=DeletionMechanism.STATUS_TRANSITION,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=False,
        notes="AogEventStatus.CANCELLED is its terminal state.",
    ),
    "AOGBLOCKER": EntityLifecyclePolicy(
        entity_type="AOGBLOCKER",
        category=LifecycleCategory.ARCHIVE_STATUS,
        deletion_mechanism=DeletionMechanism.INHERITED,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=False,
        inherits_lifecycle_from="AOGEVENT",
        notes="Always a child row of an AogEvent; no independent lifecycle decision.",
    ),
    "APPROVALREQUEST": EntityLifecyclePolicy(
        entity_type="APPROVALREQUEST",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="Governance/approval trail -- itself part of the entitlement-override audit story (tenant_entitlement_admin_service.py).",
    ),
    "PART": EntityLifecyclePolicy(
        entity_type="PART",
        category=LifecycleCategory.DEPENDENCY_CONTROLLED,
        deletion_mechanism=DeletionMechanism.STATUS_TRANSITION,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=False,
        notes="PartServiceabilityStatus.SCRAPPED/CONSUMED already exist. InventoryTransaction/ProcurementRequest/VendorPartAvailability reference it. Low priority.",
    ),
    "PURCHASEORDER": EntityLifecyclePolicy(
        entity_type="PURCHASEORDER",
        category=LifecycleCategory.DEPENDENCY_CONTROLLED,
        deletion_mechanism=DeletionMechanism.STATUS_TRANSITION,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=False,
        notes="Procurement/financial record with some audit value, not safety-critical. PurchaseOrderLine FKs to it.",
    ),
    "PROCUREMENTREQUEST": EntityLifecyclePolicy(
        entity_type="PROCUREMENTREQUEST",
        category=LifecycleCategory.DEPENDENCY_CONTROLLED,
        deletion_mechanism=DeletionMechanism.STATUS_TRANSITION,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=False,
        notes="PurchaseOrder FKs to it.",
    ),
    "TECHNICIANQUALIFICATION": EntityLifecyclePolicy(
        entity_type="TECHNICIANQUALIFICATION",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="Currency/certification compliance record.",
    ),
    "TASK": EntityLifecyclePolicy(
        entity_type="TASK",
        category=LifecycleCategory.SOFT_DELETE_RESTORE,
        deletion_mechanism=DeletionMechanism.INHERITED,
        tenant_delete_permitted=True,
        restore_permitted=True,
        permanent_delete_permitted=True,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=True,
        inherits_lifecycle_from="WORKORDER",
        notes=(
            "Always reached through its parent WorkOrder -- no independent lifecycle "
            "decision. WorkOrder's lifecycle is now implemented; Task itself gains no "
            "SoftDeleteMixin/delete route of its own (see HARD CONSTRAINTS) -- "
            "work_order_service.list_tasks_for_work_order joins WorkOrder and excludes "
            "rows whose parent is soft-deleted from that one operational listing only, "
            "never mutating the Task row."
        ),
    ),
    "IMPORTJOB": EntityLifecyclePolicy(
        entity_type="IMPORTJOB",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="System-generated data-import job history, not user-authored content to delete.",
    ),
    "INVENTORYTRANSACTION": EntityLifecyclePolicy(
        entity_type="INVENTORYTRANSACTION",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="Ledger-style transaction history -- inventory audit integrity depends on it never being edited or removed.",
    ),
    "INSTALLATIONHISTORY": EntityLifecyclePolicy(
        entity_type="INSTALLATIONHISTORY",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes="BatteryInstallation/ComponentInstallation join/history rows -- traceability record, never independently deleted.",
    ),
    "LISACONVERSATIONCONTEXT": EntityLifecyclePolicy(
        entity_type="LISACONVERSATIONCONTEXT",
        category=LifecycleCategory.ARCHIVE_STATUS,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=False,
        notes="Ephemeral AI session context, not a compliance record -- lowest priority of any entry here if ever revisited.",
    ),
    "AUDITEVENT": EntityLifecyclePolicy(
        entity_type="AUDITEVENT",
        category=LifecycleCategory.RETENTION_PROTECTED,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=True,
        implemented=True,
        notes=(
            "Append-only enforced at the DB level by a Postgres trigger "
            "(migration 0002_audit_events_immutability.py) -- not merely a policy "
            "choice. This entry exists so that fact is machine-checkable policy "
            "metadata, not only a comment in a migration file."
        ),
    ),
    "USERROLE": EntityLifecyclePolicy(
        entity_type="USERROLE",
        category=LifecycleCategory.NOT_APPLICABLE,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=True,
        notes="Join table; managed via role-assignment endpoints (tenant_service.update_tenant_user_roles), not an independently deletable entity.",
    ),
    "TENANTFEATUREOVERRIDE": EntityLifecyclePolicy(
        entity_type="TENANTFEATUREOVERRIDE",
        category=LifecycleCategory.NOT_APPLICABLE,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=True,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=True,
        notes="Already a real, permanent row DELETE today (DELETE /platform/.../feature-overrides/{key}) -- a config toggle, not a record with its own history. Platform-only; do not route through the Asset/Organization-style soft-delete pattern.",
    ),
    "TENANTUSAGELIMIT": EntityLifecyclePolicy(
        entity_type="TENANTUSAGELIMIT",
        category=LifecycleCategory.NOT_APPLICABLE,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=True,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=True,
        notes="Same shape as TenantFeatureOverride -- already a real, permanent row DELETE today, config not a history record.",
    ),
    "VENDORPARTAVAILABILITY": EntityLifecyclePolicy(
        entity_type="VENDORPARTAVAILABILITY",
        category=LifecycleCategory.NOT_APPLICABLE,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=False,
        notes="Vendor+Part availability join/reference row. Low priority, not independently user-deletable.",
    ),
    "PARTREQUIREMENT": EntityLifecyclePolicy(
        entity_type="PARTREQUIREMENT",
        category=LifecycleCategory.SOFT_DELETE_RESTORE,
        deletion_mechanism=DeletionMechanism.INHERITED,
        tenant_delete_permitted=True,
        restore_permitted=True,
        permanent_delete_permitted=True,
        permanent_delete_requires_dependency_check=True,
        retention_protected=False,
        implemented=True,
        inherits_lifecycle_from="WORKORDER",
        notes=(
            "Always reached through its parent WorkOrder, same as Task -- no "
            "independent lifecycle decision. part_requirement_service."
            "list_part_requirements_for_work_order joins WorkOrder and excludes rows "
            "whose parent is soft-deleted from that one operational listing only."
        ),
    ),
    "CONFIGURATIONS": EntityLifecyclePolicy(
        entity_type="CONFIGURATIONS",
        category=LifecycleCategory.NOT_APPLICABLE,
        deletion_mechanism=DeletionMechanism.NONE,
        tenant_delete_permitted=False,
        restore_permitted=False,
        permanent_delete_permitted=False,
        permanent_delete_requires_dependency_check=False,
        retention_protected=False,
        implemented=False,
        notes=(
            "No model named 'Configuration' exists in this codebase. The closest "
            "concept is AssetConfigurationResponse, a computed/derived read "
            "projection over installed Component rows (asset_service."
            "get_asset_configuration) -- not a persisted entity with its own "
            "identity or lifecycle. Fully covered by COMPONENT's classification "
            "above. Entry included only for completeness against the requested list."
        ),
    ),
}


def get_policy(entity_type: str) -> EntityLifecyclePolicy | None:
    """Case-insensitive lookup. Returns None for an unregistered
    entity_type -- callers that need a hard failure use resolve_policy or
    one of the assert_* guards, which raise instead."""
    return ENTITY_LIFECYCLE_POLICIES.get(entity_type.upper())


def resolve_policy(entity_type: str) -> EntityLifecyclePolicy:
    """Follows inherits_lifecycle_from to the effective policy -- e.g.
    resolve_policy("AIRCRAFT") returns Asset's own policy object, not
    Aircraft's INHERITED placeholder. This is what "Aircraft resolves to
    Asset lifecycle rather than having an independent lifecycle" means
    concretely: callers should use this, not get_policy, whenever they need
    to know what's actually PERMITTED (as opposed to introspecting the
    registry's own inheritance structure).

    Raises NotFoundError for an unregistered entity_type -- this and every
    assert_* guard below raise the same AeroComplyError-derived types the
    rest of the app already uses, so a service can call them directly
    without a separate translation layer turning a policy violation into an
    HTTP response."""
    policy = get_policy(entity_type)
    if policy is None:
        raise NotFoundError(f"No lifecycle policy registered for entity type {entity_type!r}")
    if policy.inherits_lifecycle_from is not None:
        return resolve_policy(policy.inherits_lifecycle_from)
    return policy


def assert_tenant_delete_permitted(entity_type: str) -> EntityLifecyclePolicy:
    """The guard a tenant-facing soft-delete function calls before acting.
    Checks BOTH the policy target (tenant_delete_permitted) AND that the
    behavior is actually implemented -- a category A/D entity that hasn't
    been built yet (WorkOrder, Vendor, ...) must fail this exactly like a
    category C entity does, so registering an entity's future policy can
    never accidentally make it deletable today."""
    policy = resolve_policy(entity_type)
    if not policy.implemented:
        raise ConflictError(
            f"{entity_type} has a lifecycle policy but no implemented tenant-delete path yet",
            code="lifecycle_not_implemented",
        )
    if not policy.tenant_delete_permitted:
        raise ForbiddenError(
            f"{entity_type} (category {policy.category.value}) does not permit tenant deletion",
            code="lifecycle_forbidden",
        )
    return policy


def assert_restore_permitted(entity_type: str) -> EntityLifecyclePolicy:
    policy = resolve_policy(entity_type)
    if not policy.implemented:
        raise ConflictError(
            f"{entity_type} has a lifecycle policy but no implemented restore path yet",
            code="lifecycle_not_implemented",
        )
    if not policy.restore_permitted:
        raise ForbiddenError(
            f"{entity_type} (category {policy.category.value}) does not permit restoration",
            code="lifecycle_forbidden",
        )
    return policy


def assert_permanent_delete_permitted(entity_type: str) -> EntityLifecyclePolicy:
    policy = resolve_policy(entity_type)
    if not policy.implemented:
        raise ConflictError(
            f"{entity_type} has a lifecycle policy but no implemented permanent-delete path yet",
            code="lifecycle_not_implemented",
        )
    if not policy.permanent_delete_permitted:
        raise ForbiddenError(
            f"{entity_type} (category {policy.category.value}) does not permit permanent deletion "
            f"({'retention-protected' if policy.retention_protected else 'not eligible'})",
            code="lifecycle_forbidden",
        )
    return policy


def assert_visible_in_deletion_queue(entity_type: str) -> EntityLifecyclePolicy:
    """Guards the Platform Admin deleted-records queue's entity_type filter
    (restoration_service.list_deleted_records). A retention-protected
    (category C) entity must never appear there even in principle -- this
    is checked independent of `implemented`, since the point is that a
    query for e.g. entity_type=FINDING should fail clearly rather than
    silently return an empty list that looks like "no results" instead of
    "this can never have results"."""
    policy = resolve_policy(entity_type)
    if policy.retention_protected or policy.category == LifecycleCategory.RETENTION_PROTECTED:
        raise ForbiddenError(
            f"{entity_type} is retention-protected and can never appear in the deletion queue",
            code="retention_protected",
        )
    return policy
