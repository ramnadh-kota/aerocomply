"""M16.6: HTTP-level tests for DELETE /evidence/{evidence_id}/files/{file_id}.

Real end-to-end coverage over the actual FastAPI app + real Postgres (the
`client`/`db_session` fixtures), mocking only the StorageService/S3 boundary
(M16.1) so no test ever talks to real AWS or requires a running MinIO.
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.audit_event import AuditEvent
from app.models.evidence import EvidenceFile, EvidenceFileStatus
from app.models.user import User, UserRole
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    evidence_file_service,
    evidence_service,
    work_order_service,
)
from app.services.storage.exceptions import StorageDeleteError
from app.services.storage.service import StorageService


def _register(client, org_name, email):
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _org_id(client, token):
    return uuid.UUID(client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"])


def _create_evidence_for_org(db_session, org_id, uploaded_by_user_id=None, wo_number="WO-DEL-1"):
    if uploaded_by_user_id is None:
        admin = (
            db_session.execute(select(User).where(User.organization_id == org_id)).scalars().first()
        )
        assert admin is not None, "expected an admin user to already exist for this org"
        uploaded_by_user_id = admin.id

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
        db_session,
        organization_id=org_id,
        task_id=task.id,
        uploaded_by_user_id=uploaded_by_user_id,
    )


def _add_viewer(db_session, org_id, email):
    user = User(
        organization_id=org_id,
        email=email,
        hashed_password=hash_password("supersecret123"),
        full_name="Viewer",
        is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_name="VIEWER", organization_id=org_id))
    db_session.commit()
    return user


def _make_file(
    db_session,
    *,
    organization_id,
    evidence_id,
    uploaded_by_user_id,
    status=EvidenceFileStatus.STORED,
    filename="photo.jpg",
    storage_key=None,
):
    evidence_file = EvidenceFile(
        organization_id=organization_id,
        evidence_id=evidence_id,
        uploaded_by_user_id=uploaded_by_user_id,
        original_filename=filename,
        content_type="image/jpeg",
        size_bytes=123,
        storage_key=storage_key
        or f"evidence/{organization_id}/{evidence_id}/{uuid.uuid4()}_{filename}",
        checksum_sha256="a" * 64,
        status=status.value,
    )
    db_session.add(evidence_file)
    db_session.commit()
    db_session.refresh(evidence_file)
    return evidence_file


def _admin_id(db_session, org_id):
    admin = db_session.execute(select(User).where(User.organization_id == org_id)).scalars().first()
    assert admin is not None
    return admin.id


def _delete(client, evidence_id, file_id, token):
    return client.delete(f"/api/v1/evidence/{evidence_id}/files/{file_id}", headers=_auth(token))


class TestAuthorization:
    def test_unauthenticated_delete_rejected(self, client, db_session):
        tokens = _register(client, "Del Org Unauth", "admin@del-unauth.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-U1")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = client.delete(f"/api/v1/evidence/{evidence.id}/files/{f.id}")
            assert resp.status_code == 401
            mock_delete.assert_not_called()

    def test_missing_permission_rejected(self, client, db_session):
        tokens = _register(client, "Del Org NoPerm", "admin@del-noperm.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-U2")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )
        viewer = _add_viewer(db_session, org_id, "viewer@del-noperm.com")
        login = client.post(
            "/api/v1/auth/login", json={"email": viewer.email, "password": "supersecret123"}
        )
        assert login.status_code == 200
        viewer_token = login.json()["access_token"]

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence.id, f.id, viewer_token)
            assert resp.status_code == 403
            mock_delete.assert_not_called()

    def test_authorized_tenant_user_can_delete_stored_file(self, client, db_session):
        tokens = _register(client, "Del Org OK", "admin@del-ok.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-U3")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 204
            mock_delete.assert_called_once_with(key=f.storage_key)


class TestTenantIsolation:
    def test_org_a_cannot_delete_org_b_file(self, client, db_session):
        tokens_a = _register(client, "Del Org A", "admin@del-a.com")
        tokens_b = _register(client, "Del Org B", "admin@del-b.com")
        org_b = _org_id(client, tokens_b["access_token"])
        evidence_b = _create_evidence_for_org(db_session, org_b, wo_number="WO-DEL-A1")
        f_b = _make_file(
            db_session,
            organization_id=org_b,
            evidence_id=evidence_b.id,
            uploaded_by_user_id=_admin_id(db_session, org_b),
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence_b.id, f_b.id, tokens_a["access_token"])
            assert resp.status_code == 404
            mock_delete.assert_not_called()

    def test_org_b_cannot_delete_org_a_file(self, client, db_session):
        tokens_a = _register(client, "Del Org A2", "admin@del-a2.com")
        tokens_b = _register(client, "Del Org B2", "admin@del-b2.com")
        org_a = _org_id(client, tokens_a["access_token"])
        evidence_a = _create_evidence_for_org(db_session, org_a, wo_number="WO-DEL-A2")
        f_a = _make_file(
            db_session,
            organization_id=org_a,
            evidence_id=evidence_a.id,
            uploaded_by_user_id=_admin_id(db_session, org_a),
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence_a.id, f_a.id, tokens_b["access_token"])
            assert resp.status_code == 404
            mock_delete.assert_not_called()

    def test_cross_tenant_delete_leaves_target_row_unchanged(self, client, db_session):
        tokens_a = _register(client, "Del Org A3", "admin@del-a3.com")
        tokens_b = _register(client, "Del Org B3", "admin@del-b3.com")
        org_b = _org_id(client, tokens_b["access_token"])
        evidence_b = _create_evidence_for_org(db_session, org_b, wo_number="WO-DEL-A3")
        f_b = _make_file(
            db_session,
            organization_id=org_b,
            evidence_id=evidence_b.id,
            uploaded_by_user_id=_admin_id(db_session, org_b),
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence_b.id, f_b.id, tokens_a["access_token"])
            assert resp.status_code == 404
            mock_delete.assert_not_called()

        db_session.refresh(f_b)
        assert f_b.status == EvidenceFileStatus.STORED.value
        assert f_b.deleted_at is None


class TestParentChildProtection:
    def test_wrong_evidence_correct_file_fails_safely(self, client, db_session):
        tokens = _register(client, "Del Org Mismatch", "admin@del-mismatch.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence_1 = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-M1")
        admin_id = _admin_id(db_session, org_id)
        aircraft = aircraft_service.create_aircraft(
            db_session,
            organization_id=org_id,
            payload=AircraftCreateRequest(
                registration="N999MM", msn="MSN-MM9", aircraft_type="A320"
            ),
        )
        work_order = work_order_service.create_work_order(
            db_session,
            organization_id=org_id,
            created_by_user_id=admin_id,
            payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-DEL-M2"),
        )
        task = work_order_service.create_task(
            db_session,
            organization_id=org_id,
            payload=TaskCreateRequest(
                work_order_id=work_order.id, description="Inspect other panel"
            ),
        )
        evidence_2 = evidence_service.create_evidence(
            db_session, organization_id=org_id, task_id=task.id, uploaded_by_user_id=admin_id
        )
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence_2.id,
            uploaded_by_user_id=admin_id,
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence_1.id, f.id, tokens["access_token"])
            assert resp.status_code == 404
            mock_delete.assert_not_called()

        db_session.refresh(f)
        assert f.status == EvidenceFileStatus.STORED.value

    def test_correct_evidence_wrong_tenant_file_fails_safely(self, client, db_session):
        tokens_a = _register(client, "Del Org A4", "admin@del-a4.com")
        tokens_b = _register(client, "Del Org B4", "admin@del-b4.com")
        org_a = _org_id(client, tokens_a["access_token"])
        org_b = _org_id(client, tokens_b["access_token"])
        evidence_a = _create_evidence_for_org(db_session, org_a, wo_number="WO-DEL-A4")
        f = _make_file(
            db_session,
            organization_id=org_b,
            evidence_id=evidence_a.id,
            uploaded_by_user_id=_admin_id(db_session, org_b),
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence_a.id, f.id, tokens_a["access_token"])
            assert resp.status_code == 404
            mock_delete.assert_not_called()


class TestSuccessfulDeletion:
    def test_storage_delete_called_exactly_once_with_correct_key(self, client, db_session):
        tokens = _register(client, "Del Org Once", "admin@del-once.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-O1")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 204
            assert mock_delete.call_count == 1
            assert mock_delete.call_args.kwargs == {"key": f.storage_key}

    def test_status_becomes_deleted_and_deleted_at_set_and_row_preserved(self, client, db_session):
        tokens = _register(client, "Del Org State", "admin@del-state.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-O2")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete"):
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 204

        db_session.expire_all()
        row = db_session.get(EvidenceFile, f.id)
        assert row is not None
        assert row.status == EvidenceFileStatus.DELETED.value
        assert row.deleted_at is not None
        assert row.storage_key == f.storage_key
        assert row.original_filename == f.original_filename

    def test_evidence_and_evidence_status_unchanged(self, client, db_session):
        tokens = _register(client, "Del Org EvUnchanged", "admin@del-evunchanged.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-O3")
        original_status = evidence.status
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete"):
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 204

        db_session.expire_all()
        resp2 = client.get(f"/api/v1/evidence/{evidence.id}", headers=_auth(tokens["access_token"]))
        assert resp2.status_code == 200
        assert resp2.json()["status"] == original_status


class TestStorageFailure:
    def test_storage_delete_error_handled_safely(self, client, db_session):
        tokens = _register(client, "Del Org Fail", "admin@del-fail.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-F1")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(
            StorageService, "delete", side_effect=StorageDeleteError("boom: bucket=secret-bucket")
        ):
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 502
            body = resp.json()
            assert "secret-bucket" not in body["error"]["message"]
            assert "boom" not in body["error"]["message"]

        db_session.expire_all()
        row = db_session.get(EvidenceFile, f.id)
        assert row.status == EvidenceFileStatus.STORED.value
        assert row.deleted_at is None

    def test_storage_failure_creates_no_deletion_audit_event(self, client, db_session):
        tokens = _register(client, "Del Org FailAudit", "admin@del-failaudit.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-F2")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete", side_effect=StorageDeleteError("boom")):
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 502

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "evidence_file.deleted",
                    AuditEvent.entity_id == f.id,
                )
            )
            .scalars()
            .all()
        )
        assert events == []


class TestDbFailureAfterSuccessfulStorageDelete:
    def test_db_update_failure_after_storage_delete_does_not_report_success(
        self, client, db_session
    ):
        tokens = _register(client, "Del Org DbFail", "admin@del-dbfail.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-D1")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        # Same pattern as M16.4's Case-C test (test_evidence_file_upload_api.py):
        # patch the service call the router makes AFTER the real storage
        # operation has already "succeeded", so the object is gone from
        # storage but the DB transition/audit never commits. The route
        # re-raises after logging (see app/api/v1/evidence.py) for the app's
        # own unhandled_error_handler to convert in production; under
        # Starlette's TestClient this surfaces as a raised Python exception
        # rather than a clean response (a known pre-existing
        # BaseHTTPMiddleware/RequestContextMiddleware limitation, unrelated
        # to M16.6) -- so assert on the propagation directly, and verify the
        # meaningful invariant (no false DELETED state, no false audit event)
        # via the DB row itself.
        with pytest.raises(RuntimeError, match="simulated DB failure"):
            with patch.object(StorageService, "delete"):
                with patch(
                    "app.api.v1.evidence.evidence_file_service.mark_deleted",
                    side_effect=RuntimeError("simulated DB failure"),
                ):
                    _delete(client, evidence.id, f.id, tokens["access_token"])

        row = evidence_file_service.get_file(
            db_session, organization_id=org_id, evidence_file_id=f.id
        )
        assert row.status == EvidenceFileStatus.STORED.value
        assert row.deleted_at is None

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "evidence_file.deleted",
                    AuditEvent.entity_id == f.id,
                )
            )
            .scalars()
            .all()
        )
        assert events == []


class TestStateRules:
    def test_pending_delete_rejected_without_storage_call(self, client, db_session):
        tokens = _register(client, "Del Org Pending", "admin@del-pending.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-S1")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
            status=EvidenceFileStatus.PENDING,
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 409
            mock_delete.assert_not_called()

    def test_failed_delete_rejected_without_storage_call(self, client, db_session):
        tokens = _register(client, "Del Org Failed", "admin@del-failed.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-S2")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
            status=EvidenceFileStatus.FAILED,
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 409
            mock_delete.assert_not_called()

    def test_repeated_delete_on_already_deleted_file_is_rejected_idempotently(
        self, client, db_session
    ):
        tokens = _register(client, "Del Org Repeat", "admin@del-repeat.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-S3")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp1 = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp1.status_code == 204
            assert mock_delete.call_count == 1

            resp2 = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp2.status_code == 409
            # The second attempt must not call StorageService.delete() again.
            assert mock_delete.call_count == 1

    def test_stored_to_deleted_works(self, client, db_session):
        tokens = _register(client, "Del Org StoredOk", "admin@del-storedok.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-S4")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
            status=EvidenceFileStatus.STORED,
        )

        with patch.object(StorageService, "delete"):
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 204

    @pytest.mark.parametrize(
        "status",
        [EvidenceFileStatus.PENDING, EvidenceFileStatus.FAILED, EvidenceFileStatus.DELETED],
    )
    def test_invalid_transitions_rejected(self, client, db_session, status):
        tokens = _register(
            client,
            f"Del Org Invalid {status.value}",
            f"admin@del-invalid-{status.value.lower()}.com",
        )
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(
            db_session, org_id, wo_number=f"WO-DEL-I-{status.value[:3]}"
        )
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
            status=status,
        )

        with patch.object(StorageService, "delete") as mock_delete:
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 409
            mock_delete.assert_not_called()


class TestAudit:
    def test_successful_deletion_creates_exactly_one_audit_event_with_correct_fields(
        self, client, db_session
    ):
        tokens = _register(client, "Del Org AuditOK", "admin@del-auditok.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-AU1")
        admin_id = _admin_id(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=admin_id,
            filename="report.pdf",
        )

        with patch.object(StorageService, "delete"):
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 204

        events = (
            db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "evidence_file.deleted",
                    AuditEvent.entity_id == f.id,
                )
            )
            .scalars()
            .all()
        )
        assert len(events) == 1
        event = events[0]
        assert event.organization_id == org_id
        assert event.user_id == admin_id
        assert event.entity_type == "EvidenceFile"
        assert event.entity_id == f.id
        assert event.event_metadata["evidence_id"] == str(evidence.id)
        assert event.event_metadata["original_filename"] == "report.pdf"
        assert event.event_metadata["previous_status"] == EvidenceFileStatus.STORED.value
        assert event.event_metadata["new_status"] == EvidenceFileStatus.DELETED.value

    def test_audit_event_does_not_contain_storage_secrets_or_signed_url_or_file_contents(
        self, client, db_session
    ):
        tokens = _register(client, "Del Org AuditSafe", "admin@del-auditsafe.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-AU2")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete"):
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 204

        event = db_session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "evidence_file.deleted", AuditEvent.entity_id == f.id
            )
        ).scalar_one()
        metadata_str = str(event.event_metadata)
        assert "storage_key" not in metadata_str
        assert f.storage_key not in metadata_str
        assert "https://" not in metadata_str
        assert "X-Amz" not in metadata_str


class TestExistingBehaviorPreserved:
    def test_deleted_file_remains_visible_in_list(self, client, db_session):
        tokens = _register(client, "Del Org ListVisible", "admin@del-listvisible.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-L1")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete"):
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 204

        list_resp = client.get(
            f"/api/v1/evidence/{evidence.id}/files", headers=_auth(tokens["access_token"])
        )
        assert list_resp.status_code == 200
        rows = list_resp.json()
        assert len(rows) == 1
        assert rows[0]["id"] == str(f.id)
        assert rows[0]["status"] == EvidenceFileStatus.DELETED.value
        assert rows[0]["deleted_at"] is not None

    def test_deleted_file_cannot_receive_download_url(self, client, db_session):
        tokens = _register(client, "Del Org NoDownload", "admin@del-nodownload.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id, wo_number="WO-DEL-L2")
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "delete"):
            resp = _delete(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 204

        with patch.object(StorageService, "presign_get") as mock_presign:
            dl_resp = client.get(
                f"/api/v1/evidence/{evidence.id}/files/{f.id}/download",
                headers=_auth(tokens["access_token"]),
            )
            assert dl_resp.status_code == 409
            mock_presign.assert_not_called()
