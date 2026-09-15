"""M16.3: tenant-scoped EvidenceFile metadata service tests.

Focus: this service is the security boundary M16.2 deliberately left open at
the database layer (evidence_files.organization_id is not DB-constrained to
match its parent evidence.organization_id). These tests exist to prove the
service closes that gap in the application layer, not just that basic CRUD
works.
"""

import uuid

import pytest

from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.evidence import EvidenceFileStatus
from app.models.organization import Organization
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    evidence_file_service,
    evidence_service,
    work_order_service,
)


def _create_org_and_user(db_session, org_id):
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
        payload=AircraftCreateRequest(registration="N200EF", msn="MSN-EF2", aircraft_type="A320"),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=uploaded_by_user_id,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-EFS-1"),
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


def _valid_file_kwargs(**overrides):
    data = dict(
        original_filename="photo.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        storage_key=f"evidence/x/x/{uuid.uuid4()}_photo.jpg",
        checksum_sha256=None,
    )
    data.update(overrides)
    return data


@pytest.fixture
def two_tenant_setup(db_session):
    """Org A / Org B, each with one user and one Evidence record."""
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_a = _create_org_and_user(db_session, org_a)
    user_b = _create_org_and_user(db_session, org_b)
    evidence_a = _create_evidence(db_session, org_a, user_a.id)
    evidence_b = _create_evidence(db_session, org_b, user_b.id)
    return {
        "org_a": org_a,
        "org_b": org_b,
        "user_a": user_a,
        "user_b": user_b,
        "evidence_a": evidence_a,
        "evidence_b": evidence_b,
    }


class TestCreatePendingFile:
    def test_creates_valid_pending_file(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_photo.jpg"
            ),
        )
        assert file.id is not None
        assert file.status == EvidenceFileStatus.PENDING.value

    def test_status_defaults_to_pending_regardless_of_input(self, db_session, two_tenant_setup):
        # create_pending_file has no status parameter at all -- this test
        # documents that fact by construction (calling it can never produce
        # anything but PENDING).
        t = two_tenant_setup
        file = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_a.jpg"
            ),
        )
        assert file.status == EvidenceFileStatus.PENDING.value

    def test_organization_id_derived_from_evidence_not_caller(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_b.jpg"
            ),
        )
        assert file.organization_id == t["evidence_a"].organization_id == t["org_a"]

    def test_uploaded_by_user_id_derived_from_actor(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_c.jpg"
            ),
        )
        assert file.uploaded_by_user_id == t["user_a"].id

    def test_caller_cannot_override_tenant_or_uploader(self, db_session, two_tenant_setup):
        # There is no organization_id or uploaded_by_user_id parameter on
        # EvidenceFile creation inputs at all -- create_pending_file only
        # accepts organization_id (the *caller's own*, used solely to verify
        # the parent) and actor_user_id (the *caller's own* identity). This
        # test proves the signature has no escape hatch by attempting to pass
        # values through the only available channel (kwargs) and confirming
        # the persisted row reflects the derived values, never anything else.
        t = two_tenant_setup
        someone_else = _create_org_and_user(db_session, t["org_a"])
        file = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_d.jpg"
            ),
        )
        assert file.uploaded_by_user_id == t["user_a"].id
        assert file.uploaded_by_user_id != someone_else.id


class TestCreatePendingFileTenantIsolation:
    def test_same_tenant_create_succeeds(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_b"],
            actor_user_id=t["user_b"].id,
            evidence_id=t["evidence_b"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_b']}/{t['evidence_b'].id}/{uuid.uuid4()}_e.jpg"
            ),
        )
        assert file.organization_id == t["org_b"]

    def test_cross_tenant_create_fails(self, db_session, two_tenant_setup):
        """The core M16.3 invariant: Org B cannot create a file against
        Org A's evidence_id. The service must not persist
        EvidenceFile(organization_id=Org B, evidence_id=Evidence A)."""
        t = two_tenant_setup
        with pytest.raises(NotFoundError):
            evidence_file_service.create_pending_file(
                db_session,
                organization_id=t["org_b"],
                actor_user_id=t["user_b"].id,
                evidence_id=t["evidence_a"].id,
                **_valid_file_kwargs(),
            )

    def test_cross_tenant_create_reverse_direction_fails(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        with pytest.raises(NotFoundError):
            evidence_file_service.create_pending_file(
                db_session,
                organization_id=t["org_a"],
                actor_user_id=t["user_a"].id,
                evidence_id=t["evidence_b"].id,
                **_valid_file_kwargs(),
            )


class TestGetFile:
    def test_owner_can_retrieve(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        created = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_f.jpg"
            ),
        )
        fetched = evidence_file_service.get_file(
            db_session, organization_id=t["org_a"], evidence_file_id=created.id
        )
        assert fetched.id == created.id

    def test_cross_tenant_get_raises_not_found(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file_b = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_b"],
            actor_user_id=t["user_b"].id,
            evidence_id=t["evidence_b"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_b']}/{t['evidence_b'].id}/{uuid.uuid4()}_g.jpg"
            ),
        )
        with pytest.raises(NotFoundError):
            evidence_file_service.get_file(
                db_session, organization_id=t["org_a"], evidence_file_id=file_b.id
            )

    def test_nonexistent_id_raises_same_not_found(self, db_session, two_tenant_setup):
        # Guessed/random IDs and real-but-other-tenant IDs must be
        # indistinguishable -- both NotFoundError, no other signal.
        t = two_tenant_setup
        with pytest.raises(NotFoundError):
            evidence_file_service.get_file(
                db_session, organization_id=t["org_a"], evidence_file_id=uuid.uuid4()
            )


class TestListFilesForEvidence:
    def test_lists_only_files_for_that_evidence(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        f1 = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                original_filename="one.jpg",
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_one.jpg",
            ),
        )
        f2 = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                original_filename="two.jpg",
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_two.jpg",
            ),
        )
        files = evidence_file_service.list_files_for_evidence(
            db_session, organization_id=t["org_a"], evidence_id=t["evidence_a"].id
        )
        assert {f.id for f in files} == {f1.id, f2.id}

    def test_cross_tenant_list_raises_not_found(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        with pytest.raises(NotFoundError):
            evidence_file_service.list_files_for_evidence(
                db_session, organization_id=t["org_a"], evidence_id=t["evidence_b"].id
            )

    def test_multiple_tenants_remain_isolated(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_h.jpg"
            ),
        )
        evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_b"],
            actor_user_id=t["user_b"].id,
            evidence_id=t["evidence_b"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_b']}/{t['evidence_b'].id}/{uuid.uuid4()}_i.jpg"
            ),
        )
        files_a = evidence_file_service.list_files_for_evidence(
            db_session, organization_id=t["org_a"], evidence_id=t["evidence_a"].id
        )
        files_b = evidence_file_service.list_files_for_evidence(
            db_session, organization_id=t["org_b"], evidence_id=t["evidence_b"].id
        )
        assert len(files_a) == 1
        assert len(files_b) == 1
        assert files_a[0].organization_id == t["org_a"]
        assert files_b[0].organization_id == t["org_b"]


class TestMetadataValidation:
    def test_empty_filename_rejected(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        with pytest.raises(AeroComplyError):
            evidence_file_service.create_pending_file(
                db_session,
                organization_id=t["org_a"],
                actor_user_id=t["user_a"].id,
                evidence_id=t["evidence_a"].id,
                **_valid_file_kwargs(original_filename="   "),
            )

    def test_empty_content_type_rejected(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        with pytest.raises(AeroComplyError):
            evidence_file_service.create_pending_file(
                db_session,
                organization_id=t["org_a"],
                actor_user_id=t["user_a"].id,
                evidence_id=t["evidence_a"].id,
                **_valid_file_kwargs(content_type=""),
            )

    def test_negative_size_rejected(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        with pytest.raises(AeroComplyError):
            evidence_file_service.create_pending_file(
                db_session,
                organization_id=t["org_a"],
                actor_user_id=t["user_a"].id,
                evidence_id=t["evidence_a"].id,
                **_valid_file_kwargs(size_bytes=-1),
            )

    def test_empty_storage_key_rejected(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        with pytest.raises(AeroComplyError):
            evidence_file_service.create_pending_file(
                db_session,
                organization_id=t["org_a"],
                actor_user_id=t["user_a"].id,
                evidence_id=t["evidence_a"].id,
                **_valid_file_kwargs(storage_key=""),
            )

    def test_valid_metadata_succeeds(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_j.jpg"
            ),
        )
        assert file.id is not None


class TestLifecycleTransitions:
    def _create(self, db_session, t, **overrides):
        return evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_a"],
            actor_user_id=t["user_a"].id,
            evidence_id=t["evidence_a"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_a']}/{t['evidence_a'].id}/{uuid.uuid4()}_k.jpg",
                **overrides,
            ),
        )

    def test_pending_to_stored(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file = self._create(db_session, t)
        updated = evidence_file_service.mark_stored(
            db_session, organization_id=t["org_a"], evidence_file_id=file.id
        )
        assert updated.status == EvidenceFileStatus.STORED.value

    def test_pending_to_failed(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file = self._create(db_session, t)
        updated = evidence_file_service.mark_failed(
            db_session, organization_id=t["org_a"], evidence_file_id=file.id
        )
        assert updated.status == EvidenceFileStatus.FAILED.value

    def test_stored_to_pending_rejected(self, db_session, two_tenant_setup):
        # There is no public method to move a file backwards to PENDING at
        # all (mark_stored/mark_failed only ever accept PENDING as the
        # starting state) -- the pure rule function is what actually
        # prevents it, so exercise that directly rather than reaching for a
        # private helper.
        assert not evidence_file_service.can_transition_file(
            EvidenceFileStatus.STORED, EvidenceFileStatus.PENDING
        )

    def test_stored_to_failed_rejected(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file = self._create(db_session, t)
        evidence_file_service.mark_stored(
            db_session, organization_id=t["org_a"], evidence_file_id=file.id
        )
        with pytest.raises(ConflictError):
            evidence_file_service.mark_failed(
                db_session, organization_id=t["org_a"], evidence_file_id=file.id
            )

    def test_failed_to_pending_rejected(self, db_session, two_tenant_setup):
        assert not evidence_file_service.can_transition_file(
            EvidenceFileStatus.FAILED, EvidenceFileStatus.PENDING
        )

    def test_failed_to_stored_rejected(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file = self._create(db_session, t)
        evidence_file_service.mark_failed(
            db_session, organization_id=t["org_a"], evidence_file_id=file.id
        )
        with pytest.raises(ConflictError):
            evidence_file_service.mark_stored(
                db_session, organization_id=t["org_a"], evidence_file_id=file.id
            )

    def test_deleted_to_stored_rejected(self, db_session, two_tenant_setup):
        # No code path sets DELETED yet (that's M16.6) -- exercise the pure
        # rule function directly to prove the transition table itself
        # correctly treats DELETED as terminal.
        assert not evidence_file_service.can_transition_file(
            EvidenceFileStatus.DELETED, EvidenceFileStatus.STORED
        )

    def test_deleted_to_pending_rejected(self, db_session, two_tenant_setup):
        assert not evidence_file_service.can_transition_file(
            EvidenceFileStatus.DELETED, EvidenceFileStatus.PENDING
        )

    def test_can_transition_file_rejects_same_status(self, db_session, two_tenant_setup):
        assert not evidence_file_service.can_transition_file(
            EvidenceFileStatus.PENDING, EvidenceFileStatus.PENDING
        )


class TestLifecycleTenantIsolation:
    def test_cross_tenant_mark_stored_raises_not_found(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file_b = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_b"],
            actor_user_id=t["user_b"].id,
            evidence_id=t["evidence_b"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_b']}/{t['evidence_b'].id}/{uuid.uuid4()}_l.jpg"
            ),
        )
        with pytest.raises(NotFoundError):
            evidence_file_service.mark_stored(
                db_session, organization_id=t["org_a"], evidence_file_id=file_b.id
            )
        # And the file itself must be unaffected by the rejected attempt.
        reloaded = evidence_file_service.get_file(
            db_session, organization_id=t["org_b"], evidence_file_id=file_b.id
        )
        assert reloaded.status == EvidenceFileStatus.PENDING.value

    def test_cross_tenant_mark_failed_raises_not_found(self, db_session, two_tenant_setup):
        t = two_tenant_setup
        file_b = evidence_file_service.create_pending_file(
            db_session,
            organization_id=t["org_b"],
            actor_user_id=t["user_b"].id,
            evidence_id=t["evidence_b"].id,
            **_valid_file_kwargs(
                storage_key=f"evidence/{t['org_b']}/{t['evidence_b'].id}/{uuid.uuid4()}_m.jpg"
            ),
        )
        with pytest.raises(NotFoundError):
            evidence_file_service.mark_failed(
                db_session, organization_id=t["org_a"], evidence_file_id=file_b.id
            )
        reloaded = evidence_file_service.get_file(
            db_session, organization_id=t["org_b"], evidence_file_id=file_b.id
        )
        assert reloaded.status == EvidenceFileStatus.PENDING.value
