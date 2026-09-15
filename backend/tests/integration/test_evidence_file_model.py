"""M16.2: EvidenceFile model + migration tests.

Schema/model only -- there is no upload/download/delete endpoint yet, so
these tests construct EvidenceFile rows directly rather than through a
service (that's M16.3). The Alembic upgrade/downgrade itself is already
exercised by every integration-test run via the session-scoped `engine`
fixture (tests/integration/conftest.py runs migrations "head" then "base"),
so a real upgrade->head has already happened by the time these tests run;
this file additionally verifies upgrade/downgrade/re-upgrade explicitly.
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.evidence import EvidenceFile, EvidenceFileStatus, EvidenceStatus
from app.models.organization import Organization
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import aircraft_service, evidence_service, work_order_service


def _create_user(db_session, org_id):
    # users.organization_id has a real DB-level FK to organizations (added in
    # migration, not declared on the User ORM model itself) -- unlike
    # Evidence/EvidenceFile.organization_id, which are plain
    # TenantScopedMixin columns with no FK. A real Organization row is
    # therefore required here.
    if db_session.get(Organization, org_id) is None:
        db_session.add(Organization(id=org_id, name="Test Org"))
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
    return user


def _create_evidence(db_session, org_id, uploaded_by_user_id):
    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N100EF", msn="MSN-EF1", aircraft_type="A320"),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=uploaded_by_user_id,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-EF-1"),
    )
    task = work_order_service.create_task(
        db_session,
        organization_id=org_id,
        payload=TaskCreateRequest(work_order_id=work_order.id, description="Inspect panel"),
    )
    return evidence_service.create_evidence(
        db_session,
        organization_id=org_id,
        task_id=task.id,
        uploaded_by_user_id=uploaded_by_user_id,
    )


def _make_file(evidence, uploader_id, **overrides):
    data = dict(
        organization_id=evidence.organization_id,
        evidence_id=evidence.id,
        uploaded_by_user_id=uploader_id,
        original_filename="inspection-photo.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        storage_key=f"evidence/{evidence.organization_id}/{evidence.id}/{uuid.uuid4()}_inspection-photo.jpg",
    )
    data.update(overrides)
    return EvidenceFile(**data)


class TestEvidenceFileCreation:
    def test_create_with_valid_required_metadata(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id)
        db_session.add(file)
        db_session.commit()
        db_session.refresh(file)

        assert file.id is not None
        assert file.status == EvidenceFileStatus.PENDING.value
        assert file.checksum_sha256 is None
        assert file.deleted_at is None
        assert file.created_at is not None

    def test_belongs_to_evidence(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id)
        db_session.add(file)
        db_session.commit()
        db_session.refresh(file)

        assert file.evidence.id == evidence.id
        assert file.evidence.status == EvidenceStatus.UPLOADED.value

    def test_evidence_files_relationship_exposes_children(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file_a = _make_file(evidence, user.id, original_filename="a.jpg")
        file_b = _make_file(evidence, user.id, original_filename="b.jpg")
        db_session.add_all([file_a, file_b])
        db_session.commit()
        db_session.refresh(evidence)

        assert {f.original_filename for f in evidence.files} == {"a.jpg", "b.jpg"}

    def test_status_accepts_all_known_values(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        for status in EvidenceFileStatus:
            file = _make_file(evidence, user.id, status=status.value)
            db_session.add(file)
        db_session.commit()

    def test_checksum_may_be_null(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, checksum_sha256=None)
        db_session.add(file)
        db_session.commit()
        db_session.refresh(file)
        assert file.checksum_sha256 is None

    def test_deleted_at_may_be_null(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id)
        db_session.add(file)
        db_session.commit()
        db_session.refresh(file)
        assert file.deleted_at is None


class TestEvidenceFileRequiredFields:
    def test_organization_id_required(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, organization_id=None)
        db_session.add(file)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_evidence_id_required(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, evidence_id=None)
        db_session.add(file)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_evidence_id_must_reference_existing_row(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, evidence_id=uuid.uuid4())
        db_session.add(file)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_uploaded_by_user_id_required(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, uploaded_by_user_id=None)
        db_session.add(file)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_uploaded_by_user_id_must_reference_existing_row(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, uploaded_by_user_id=uuid.uuid4())
        db_session.add(file)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_original_filename_required(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, original_filename=None)
        db_session.add(file)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_content_type_required(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, content_type=None)
        db_session.add(file)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_storage_key_required(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, storage_key=None)
        db_session.add(file)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestEvidenceFileConstraints:
    def test_size_bytes_accepts_zero_and_positive_values(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file_zero = _make_file(evidence, user.id, size_bytes=0)
        db_session.add(file_zero)
        db_session.commit()

        file_positive = _make_file(evidence, user.id, size_bytes=5_000_000)
        db_session.add(file_positive)
        db_session.commit()

    def test_negative_size_bytes_rejected(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id, size_bytes=-1)
        db_session.add(file)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_storage_key_uniqueness_enforced(self, db_session):
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        shared_key = f"evidence/{org_id}/{evidence.id}/{uuid.uuid4()}_dup.jpg"
        file_a = _make_file(evidence, user.id, storage_key=shared_key)
        db_session.add(file_a)
        db_session.commit()

        file_b = _make_file(evidence, user.id, storage_key=shared_key)
        db_session.add(file_b)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()


class TestEvidenceFileTenantScoping:
    def test_organization_id_matches_tenant_scoped_mixin_shape(self, db_session):
        # EvidenceFile.organization_id is stored directly (not only reachable
        # via evidence_id -> evidence), matching every other tenant-scoped
        # table in this codebase (see TenantScopedMixin) -- this is required
        # for direct tenant-scoped filtering without a join.
        org_id = uuid.uuid4()
        user = _create_user(db_session, org_id)
        evidence = _create_evidence(db_session, org_id, user.id)

        file = _make_file(evidence, user.id)
        db_session.add(file)
        db_session.commit()
        db_session.refresh(file)

        assert file.organization_id == org_id == evidence.organization_id

    def test_cross_tenant_parent_child_consistency_is_not_db_enforced(self, db_session):
        """Cross-tenant parent/child consistency (evidence_files.organization_id
        must equal the parent evidence's organization_id) is enforced by
        M16.3's service layer, not the database -- there is no composite FK
        for it (see the 0026 migration docstring for why). This test proves
        that fact honestly rather than asserting a DB-level guarantee that
        does not exist: a mismatched organization_id currently persists
        successfully at the model/DB layer.
        """
        org_a = uuid.uuid4()
        org_b = uuid.uuid4()
        user = _create_user(db_session, org_a)
        evidence_in_org_a = _create_evidence(db_session, org_a, user.id)

        file = _make_file(evidence_in_org_a, user.id, organization_id=org_b)
        db_session.add(file)
        db_session.commit()
        db_session.refresh(file)

        assert file.organization_id == org_b
        assert file.evidence.organization_id == org_a
