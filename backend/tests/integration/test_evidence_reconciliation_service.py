"""M16.8: EvidenceFile <-> object-storage reconciliation tests.

No HTTP layer is involved (there is no new endpoint) -- these are
service-level integration tests against the real DB, following the same
direct-model-construction pattern as test_evidence_file_model.py. Only
StorageService is mocked, at the abstraction boundary (object_exists/
delete), never the domain/service layer itself.
"""

import uuid

from sqlalchemy import select

from app.models.audit_event import AuditEvent
from app.models.evidence import EvidenceFile, EvidenceFileStatus
from app.models.organization import Organization
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import aircraft_service, evidence_service, work_order_service
from app.services.evidence_reconciliation_service import (
    ReconciliationClassification,
    apply_repairs,
    scan_evidence_files,
)
from app.services.storage.exceptions import StorageDeleteError, StorageUnavailableError


def _create_org_and_user(db_session, org_id=None):
    org_id = org_id or uuid.uuid4()
    db_session.add(Organization(id=org_id, name=f"Recon Org {org_id}"))
    db_session.commit()
    user = User(
        organization_id=org_id,
        email=f"{uuid.uuid4()}@example.com",
        hashed_password="not-a-real-hash",
        full_name="Test User",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return org_id, user


def _create_evidence(db_session, org_id, uploaded_by_user_id, wo_number):
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(
            registration=f"N{wo_number[-4:]}", msn=f"MSN-{wo_number}", aircraft_type="A320"
        ),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=uploaded_by_user_id,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number=wo_number),
    )
    task = work_order_service.create_task(
        db_session,
        organization_id=org_id,
        payload=TaskCreateRequest(work_order_id=work_order.id, description="Inspect panel"),
    )
    return evidence_service.create_evidence(
        db_session, organization_id=org_id, task_id=task.id, uploaded_by_user_id=uploaded_by_user_id
    )


def _make_file(evidence, uploader_id, **overrides):
    data = dict(
        organization_id=evidence.organization_id,
        evidence_id=evidence.id,
        uploaded_by_user_id=uploader_id,
        original_filename="inspection-photo.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        storage_key=f"evidence/{evidence.organization_id}/{evidence.id}/{uuid.uuid4()}_photo.jpg",
        status=EvidenceFileStatus.STORED.value,
    )
    data.update(overrides)
    return EvidenceFile(**data)


def _save(db_session, evidence_file):
    db_session.add(evidence_file)
    db_session.commit()
    db_session.refresh(evidence_file)
    return evidence_file


class _FakeStorage:
    """Minimal StorageService double: object_exists()/delete() only, exactly
    the abstraction boundary reconciliation uses -- never boto3, never the
    real service's put()/presign_get()."""

    def __init__(
        self, existing_keys: set[str] | None = None, unavailable_keys: set[str] | None = None
    ):
        self.existing_keys = existing_keys or set()
        self.unavailable_keys = unavailable_keys or set()
        self.deleted_keys: list[str] = []
        self.delete_calls = 0
        self.exists_calls = 0

    def object_exists(self, *, key: str) -> bool:
        self.exists_calls += 1
        if key in self.unavailable_keys:
            raise StorageUnavailableError("simulated storage unavailable")
        return key in self.existing_keys

    def delete(self, *, key: str) -> None:
        self.delete_calls += 1
        self.deleted_keys.append(key)
        self.existing_keys.discard(key)


class TestBasicClassification:
    def test_stored_with_object_is_consistent(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-1")
        f = _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.STORED.value))
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.scanned_count == 1
        assert result.consistent_count == 1
        assert result.anomaly_count == 0
        assert result.anomalies == []

    def test_stored_without_object_is_anomaly(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-2")
        f = _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.STORED.value))
        storage = _FakeStorage(existing_keys=set())

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.anomaly_count == 1
        assert result.manual_review_count == 1
        assert result.anomalies[0].classification == ReconciliationClassification.MANUAL_REVIEW
        assert result.anomalies[0].evidence_file_id == f.id
        assert result.anomalies[0].object_exists is False

    def test_pending_with_object_is_manual_review(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-3")
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.PENDING.value)
        )
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.anomaly_count == 1
        assert result.anomalies[0].classification == ReconciliationClassification.MANUAL_REVIEW

    def test_pending_without_object_is_manual_review(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-4")
        _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.PENDING.value))
        storage = _FakeStorage(existing_keys=set())

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.anomaly_count == 1
        assert result.anomalies[0].classification == ReconciliationClassification.MANUAL_REVIEW

    def test_failed_with_object_is_manual_review(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-5")
        f = _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.FAILED.value))
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.anomaly_count == 1
        assert result.anomalies[0].classification == ReconciliationClassification.MANUAL_REVIEW

    def test_failed_without_object_is_no_action_and_counts_as_consistent(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-6")
        _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.FAILED.value))
        storage = _FakeStorage(existing_keys=set())

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.anomaly_count == 0
        assert result.consistent_count == 1
        assert result.anomalies == []

    def test_deleted_with_object_is_safe_to_repair(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-7")
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value)
        )
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.anomaly_count == 1
        assert result.repairable_count == 1
        assert result.manual_review_count == 0
        assert result.anomalies[0].classification == ReconciliationClassification.SAFE_TO_REPAIR

    def test_deleted_without_object_is_consistent_no_action(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-8")
        _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value))
        storage = _FakeStorage(existing_keys=set())

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.anomaly_count == 0
        assert result.consistent_count == 1


class TestStorageFailureDistinctFromMissing:
    def test_storage_unavailable_is_infrastructure_failure_not_missing(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-9")
        f = _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.STORED.value))
        storage = _FakeStorage(unavailable_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.infrastructure_failure_count == 1
        assert result.anomaly_count == 0
        assert result.consistent_count == 0
        anomaly = result.anomalies[0]
        assert anomaly.classification == ReconciliationClassification.INFRASTRUCTURE_FAILURE
        assert anomaly.object_exists is None
        assert len(result.failures) == 1

    def test_permission_failure_is_also_infrastructure_failure(self, db_session):
        # StorageUnavailableError is the single typed exception covering
        # permission failures, timeouts, and provider errors alike (see
        # StorageService.object_exists) -- reconciliation cannot and should
        # not try to distinguish between them, only that none is "missing".
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-10")
        f = _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.STORED.value))
        storage = _FakeStorage(unavailable_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.infrastructure_failure_count == 1
        assert result.anomalies[0].object_exists is None


class TestTenantIsolation:
    def test_scan_scoped_to_one_organization_does_not_see_another(self, db_session):
        org_a, user_a = _create_org_and_user(db_session)
        org_b, user_b = _create_org_and_user(db_session)
        evidence_a = _create_evidence(db_session, org_a, user_a.id, "WO-RC-TA")
        evidence_b = _create_evidence(db_session, org_b, user_b.id, "WO-RC-TB")
        f_a = _save(
            db_session, _make_file(evidence_a, user_a.id, status=EvidenceFileStatus.STORED.value)
        )
        f_b = _save(
            db_session, _make_file(evidence_b, user_b.id, status=EvidenceFileStatus.STORED.value)
        )
        storage = _FakeStorage(existing_keys={f_a.storage_key, f_b.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_a)

        assert result.scanned_count == 1
        assert all(a.organization_id == org_a for a in result.anomalies)
        # Only org A's key was ever checked against storage.
        assert storage.exists_calls == 1

    def test_platform_wide_scan_covers_multiple_organizations(self, db_session):
        org_a, user_a = _create_org_and_user(db_session)
        org_b, user_b = _create_org_and_user(db_session)
        evidence_a = _create_evidence(db_session, org_a, user_a.id, "WO-RC-MA")
        evidence_b = _create_evidence(db_session, org_b, user_b.id, "WO-RC-MB")
        f_a = _save(
            db_session, _make_file(evidence_a, user_a.id, status=EvidenceFileStatus.STORED.value)
        )
        f_b = _save(
            db_session,
            _make_file(evidence_b, user_b.id, status=EvidenceFileStatus.STORED.value),
        )
        # f_b's object is missing -- an anomaly that must be attributed to org_b, never org_a.
        storage = _FakeStorage(existing_keys={f_a.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=None)

        ids = {a.evidence_file_id for a in result.anomalies}
        assert f_b.id in ids
        assert f_a.id not in ids
        anomaly = next(a for a in result.anomalies if a.evidence_file_id == f_b.id)
        assert anomaly.organization_id == org_b

    def test_no_cross_tenant_storage_key_confusion(self, db_session):
        # Two orgs' files never share a storage_key (real keys are
        # namespaced by org/evidence/file uuid) -- confirm reconciliation
        # checks each row against its own key only, never a shared one.
        org_a, user_a = _create_org_and_user(db_session)
        org_b, user_b = _create_org_and_user(db_session)
        evidence_a = _create_evidence(db_session, org_a, user_a.id, "WO-RC-XA")
        evidence_b = _create_evidence(db_session, org_b, user_b.id, "WO-RC-XB")
        f_a = _save(
            db_session, _make_file(evidence_a, user_a.id, status=EvidenceFileStatus.STORED.value)
        )
        f_b = _save(
            db_session, _make_file(evidence_b, user_b.id, status=EvidenceFileStatus.STORED.value)
        )
        assert f_a.storage_key != f_b.storage_key

        storage = _FakeStorage(existing_keys={f_a.storage_key, f_b.storage_key})
        result = scan_evidence_files(db_session, storage, organization_id=None)
        assert result.consistent_count == 2
        assert result.anomaly_count == 0


class TestRepair:
    def test_repair_deletes_orphaned_object_and_records_audit_event(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-R1")
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value)
        )
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)
        repaired = apply_repairs(
            db_session, storage, anomalies=result.anomalies, actor_user_id=user.id
        )

        assert repaired == 1
        assert storage.delete_calls == 1
        assert f.storage_key not in storage.existing_keys

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "evidence_file.reconciliation_repaired",
                    AuditEvent.entity_id == f.id,
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.organization_id == org_id
        assert event.user_id == user.id
        assert event.entity_type == "EvidenceFile"
        metadata_str = str(event.event_metadata)
        assert f.storage_key not in metadata_str
        assert "https://" not in metadata_str

    def test_repair_does_not_mutate_evidence_file_status_or_deleted_at(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-R2")
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value)
        )
        original_deleted_at = f.deleted_at
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)
        apply_repairs(db_session, storage, anomalies=result.anomalies, actor_user_id=user.id)

        db_session.refresh(f)
        assert f.status == EvidenceFileStatus.DELETED.value
        assert f.deleted_at == original_deleted_at

    def test_repair_does_not_mutate_evidence_status(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-R3")
        original_status = evidence.status
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value)
        )
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)
        apply_repairs(db_session, storage, anomalies=result.anomalies, actor_user_id=user.id)

        db_session.refresh(evidence)
        assert evidence.status == original_status

    def test_repair_skips_anomaly_whose_state_changed_since_scan(self, db_session):
        # Simulates the concurrency guard: between scan() and apply_repairs(),
        # something changed the row away from DELETED. Repair must re-check
        # fresh state and skip rather than trust the stale scan snapshot.
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-R4")
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value)
        )
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        # Mutate the row directly to simulate a state change the scan didn't see.
        f.status = EvidenceFileStatus.STORED.value
        db_session.add(f)
        db_session.commit()

        repaired = apply_repairs(
            db_session, storage, anomalies=result.anomalies, actor_user_id=user.id
        )

        assert repaired == 0
        assert storage.delete_calls == 0
        assert f.storage_key in storage.existing_keys
        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "evidence_file.reconciliation_repaired"
                )
            )
            .scalars()
            .all()
        )
        assert events == []

    def test_repair_storage_failure_creates_no_audit_event(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-R5")
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value)
        )

        class FailingDeleteStorage(_FakeStorage):
            def delete(self, *, key: str) -> None:
                raise StorageDeleteError("simulated delete failure")

        storage = FailingDeleteStorage(existing_keys={f.storage_key})
        result = scan_evidence_files(db_session, storage, organization_id=org_id)
        repaired = apply_repairs(
            db_session, storage, anomalies=result.anomalies, actor_user_id=user.id
        )

        assert repaired == 0
        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "evidence_file.reconciliation_repaired"
                )
            )
            .scalars()
            .all()
        )
        assert events == []

    def test_repair_ignores_manual_review_anomalies(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-R6")
        _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.STORED.value))
        storage = _FakeStorage(existing_keys=set())  # STORED + missing -> MANUAL_REVIEW

        result = scan_evidence_files(db_session, storage, organization_id=org_id)
        repaired = apply_repairs(
            db_session, storage, anomalies=result.anomalies, actor_user_id=user.id
        )

        assert repaired == 0
        assert storage.delete_calls == 0

    def test_repair_accepts_none_actor_for_system_initiated_run(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-R7")
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value)
        )
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)
        repaired = apply_repairs(
            db_session, storage, anomalies=result.anomalies, actor_user_id=None
        )

        assert repaired == 1
        event = db_session.execute(
            select(AuditEvent).where(AuditEvent.action == "evidence_file.reconciliation_repaired")
        ).scalar_one()
        assert event.user_id is None


class TestNoUnsafeAutomaticDeletion:
    def test_failed_with_object_never_deletes_automatically(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-S1")
        f = _save(db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.FAILED.value))
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)
        repaired = apply_repairs(
            db_session, storage, anomalies=result.anomalies, actor_user_id=user.id
        )

        assert repaired == 0
        assert storage.delete_calls == 0
        assert f.storage_key in storage.existing_keys

    def test_pending_with_object_never_deletes_automatically(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-S2")
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.PENDING.value)
        )
        storage = _FakeStorage(existing_keys={f.storage_key})

        result = scan_evidence_files(db_session, storage, organization_id=org_id)
        apply_repairs(db_session, storage, anomalies=result.anomalies, actor_user_id=user.id)

        assert storage.delete_calls == 0


class TestEmptyAndMultiFile:
    def test_empty_dataset_returns_zeroed_result(self, db_session):
        org_id, _user = _create_org_and_user(db_session)
        storage = _FakeStorage()

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.scanned_count == 0
        assert result.consistent_count == 0
        assert result.anomaly_count == 0
        assert result.anomalies == []
        assert result.failures == []

    def test_multiple_files_for_same_evidence_are_each_checked(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-M1")
        f1 = _save(
            db_session,
            _make_file(
                evidence, user.id, status=EvidenceFileStatus.STORED.value, original_filename="a.jpg"
            ),
        )
        f2 = _save(
            db_session,
            _make_file(
                evidence, user.id, status=EvidenceFileStatus.STORED.value, original_filename="b.jpg"
            ),
        )
        storage = _FakeStorage(existing_keys={f1.storage_key})  # f2's object missing

        result = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result.scanned_count == 2
        assert result.consistent_count == 1
        assert result.anomaly_count == 1
        assert result.anomalies[0].evidence_file_id == f2.id


class TestIdempotency:
    def test_repeated_scan_is_deterministic(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-I1")
        f1 = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.STORED.value)
        )
        f2 = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value)
        )
        storage = _FakeStorage(existing_keys={f1.storage_key, f2.storage_key})

        result1 = scan_evidence_files(db_session, storage, organization_id=org_id)
        result2 = scan_evidence_files(db_session, storage, organization_id=org_id)

        assert result1.scanned_count == result2.scanned_count
        assert result1.consistent_count == result2.consistent_count
        assert result1.anomaly_count == result2.anomaly_count
        assert [a.evidence_file_id for a in result1.anomalies] == [
            a.evidence_file_id for a in result2.anomalies
        ]

    def test_repeated_repair_is_idempotent_second_run_finds_nothing_to_repair(self, db_session):
        org_id, user = _create_org_and_user(db_session)
        evidence = _create_evidence(db_session, org_id, user.id, "WO-RC-I2")
        f = _save(
            db_session, _make_file(evidence, user.id, status=EvidenceFileStatus.DELETED.value)
        )
        storage = _FakeStorage(existing_keys={f.storage_key})

        result1 = scan_evidence_files(db_session, storage, organization_id=org_id)
        repaired1 = apply_repairs(
            db_session, storage, anomalies=result1.anomalies, actor_user_id=user.id
        )
        assert repaired1 == 1

        # Second scan: the object is now genuinely gone, so this is NO_ACTION,
        # not SAFE_TO_REPAIR again -- nothing left to repair.
        result2 = scan_evidence_files(db_session, storage, organization_id=org_id)
        repaired2 = apply_repairs(
            db_session, storage, anomalies=result2.anomalies, actor_user_id=user.id
        )

        assert result2.anomaly_count == 0
        assert repaired2 == 0
        assert storage.delete_calls == 1  # not called a second time
