"""M16.5: HTTP-level tests for GET /evidence/{evidence_id}/files and
GET /evidence/{evidence_id}/files/{file_id}/download.

Real end-to-end coverage over the actual FastAPI app + real Postgres (the
`client`/`db_session` fixtures), mocking only the StorageService/S3 boundary
(M16.1) so no test ever talks to real AWS or requires a running MinIO.
"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.evidence import EvidenceFile, EvidenceFileStatus
from app.models.user import User, UserRole
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import aircraft_service, evidence_service, work_order_service
from app.services.storage.exceptions import StoragePresignError
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


def _create_evidence_for_org(db_session, org_id, uploaded_by_user_id=None):
    if uploaded_by_user_id is None:
        admin = (
            db_session.execute(select(User).where(User.organization_id == org_id)).scalars().first()
        )
        assert admin is not None, "expected an admin user to already exist for this org"
        uploaded_by_user_id = admin.id

    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N400GH", msn="MSN-GH4", aircraft_type="A320"),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=uploaded_by_user_id,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-DL-1"),
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
    created_at=None,
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
    if created_at is not None:
        # created_at is server_default=func.now() (see app/db/base.py's
        # TimestampMixin), which returns the *transaction* start time in
        # Postgres, not per-statement time -- and this whole test runs
        # inside one outer transaction (see conftest.py's db_session
        # fixture), so two rows created moments apart in test wall-clock
        # time can otherwise get an identical created_at. Setting an
        # explicit value here (only where a test needs genuinely distinct
        # timestamps to exercise ORDER BY created_at) overrides that
        # default, the same way any explicit column value does.
        evidence_file.created_at = created_at
    db_session.add(evidence_file)
    db_session.commit()
    db_session.refresh(evidence_file)
    return evidence_file


def _admin_id(db_session, org_id):
    admin = db_session.execute(select(User).where(User.organization_id == org_id)).scalars().first()
    assert admin is not None
    return admin.id


def _list(client, evidence_id, token):
    return client.get(f"/api/v1/evidence/{evidence_id}/files", headers=_auth(token))


def _download(client, evidence_id, file_id, token):
    return client.get(
        f"/api/v1/evidence/{evidence_id}/files/{file_id}/download", headers=_auth(token)
    )


class TestListFiles:
    def test_authorized_tenant_can_list_files(self, client, db_session):
        tokens = _register(client, "List Org 1", "admin@list-org1.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        admin_id = _admin_id(db_session, org_id)
        f1 = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=admin_id,
        )

        resp = _list(client, evidence.id, tokens["access_token"])
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["id"] == str(f1.id)
        assert "storage_key" not in body[0]

    def test_empty_evidence_returns_empty_list(self, client, db_session):
        tokens = _register(client, "List Org Empty", "admin@list-empty.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)

        resp = _list(client, evidence.id, tokens["access_token"])
        assert resp.status_code == 200
        assert resp.json() == []

    def test_multiple_files_returned_correctly(self, client, db_session):
        tokens = _register(client, "List Org Multi", "admin@list-multi.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        admin_id = _admin_id(db_session, org_id)
        f1 = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=admin_id,
            filename="a.jpg",
        )
        f2 = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=admin_id,
            filename="b.jpg",
        )

        resp = _list(client, evidence.id, tokens["access_token"])
        assert resp.status_code == 200
        ids = {row["id"] for row in resp.json()}
        assert ids == {str(f1.id), str(f2.id)}

    def test_deterministic_ordering(self, client, db_session):
        tokens = _register(client, "List Org Order", "admin@list-order.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        admin_id = _admin_id(db_session, org_id)
        # Explicit, distinct created_at values: see _make_file's docstring --
        # Postgres's func.now() is transaction-scoped, and this whole test
        # runs inside one outer transaction, so two rows created via ordinary
        # inserts here could otherwise tie on created_at.
        base = datetime(2026, 1, 1, tzinfo=UTC)
        f1 = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=admin_id,
            filename="a.jpg",
            created_at=base,
        )
        f2 = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=admin_id,
            filename="b.jpg",
            created_at=base + timedelta(seconds=1),
        )

        resp1 = _list(client, evidence.id, tokens["access_token"])
        resp2 = _list(client, evidence.id, tokens["access_token"])
        assert [r["id"] for r in resp1.json()] == [str(f1.id), str(f2.id)]
        assert [r["id"] for r in resp1.json()] == [r["id"] for r in resp2.json()]

    def test_org_a_cannot_list_org_b_evidence(self, client, db_session):
        tokens_a = _register(client, "List Org A", "admin@list-a.com")
        tokens_b = _register(client, "List Org B", "admin@list-b.com")
        _org_id(client, tokens_a["access_token"])
        org_b = _org_id(client, tokens_b["access_token"])
        evidence_b = _create_evidence_for_org(db_session, org_b)
        _make_file(
            db_session,
            organization_id=org_b,
            evidence_id=evidence_b.id,
            uploaded_by_user_id=_admin_id(db_session, org_b),
        )

        resp = _list(client, evidence_b.id, tokens_a["access_token"])
        assert resp.status_code == 404

    def test_org_b_cannot_list_org_a_evidence(self, client, db_session):
        tokens_a = _register(client, "List Org A2", "admin@list-a2.com")
        tokens_b = _register(client, "List Org B2", "admin@list-b2.com")
        org_a = _org_id(client, tokens_a["access_token"])
        _org_id(client, tokens_b["access_token"])
        evidence_a = _create_evidence_for_org(db_session, org_a)
        _make_file(
            db_session,
            organization_id=org_a,
            evidence_id=evidence_a.id,
            uploaded_by_user_id=_admin_id(db_session, org_a),
        )

        resp = _list(client, evidence_a.id, tokens_b["access_token"])
        assert resp.status_code == 404

    def test_nonexistent_evidence_returns_safe_404(self, client, db_session):
        tokens = _register(client, "List Org NF", "admin@list-nf.com")
        resp = _list(client, uuid.uuid4(), tokens["access_token"])
        assert resp.status_code == 404

    def test_unauthorized_user_cannot_list(self, client, db_session):
        tokens = _register(client, "List Org Unauth", "admin@list-unauth.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)

        resp = client.get(f"/api/v1/evidence/{evidence.id}/files")
        assert resp.status_code == 401

    def test_storage_service_not_called_during_list(self, client, db_session):
        tokens = _register(client, "List Org NoStorage", "admin@list-nostorage.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with (
            patch.object(StorageService, "presign_get") as mock_presign,
            patch.object(StorageService, "put") as mock_put,
        ):
            resp = _list(client, evidence.id, tokens["access_token"])
            assert resp.status_code == 200
            mock_presign.assert_not_called()
            mock_put.assert_not_called()

    def test_storage_key_not_exposed_in_list_response(self, client, db_session):
        tokens = _register(client, "List Org NoKey", "admin@list-nokey.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        resp = _list(client, evidence.id, tokens["access_token"])
        assert resp.status_code == 200
        for row in resp.json():
            assert "storage_key" not in row
            assert "bucket" not in row


class TestDownload:
    def test_authorized_tenant_can_download_stored_file(self, client, db_session):
        tokens = _register(client, "DL Org 1", "admin@dl-org1.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(
            StorageService, "presign_get", return_value="https://example.com/signed"
        ) as mock_presign:
            resp = _download(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 200
            body = resp.json()
            assert body["url"] == "https://example.com/signed"
            assert body["expires_in"] == 300
            mock_presign.assert_called_once_with(key=f.storage_key)

    def test_presign_called_exactly_once_with_correct_key(self, client, db_session):
        tokens = _register(client, "DL Org Key", "admin@dl-key.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(
            StorageService, "presign_get", return_value="https://example.com/x"
        ) as mock_presign:
            _download(client, evidence.id, f.id, tokens["access_token"])
            assert mock_presign.call_count == 1
            assert mock_presign.call_args.kwargs == {"key": f.storage_key}

    def test_configured_expiry_used_and_matches_response(self, client, db_session):
        tokens = _register(client, "DL Org Expiry", "admin@dl-expiry.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(
            StorageService, "presign_get", return_value="https://example.com/x"
        ) as mock_presign:
            resp = _download(client, evidence.id, f.id, tokens["access_token"])
            # presign_get is called with no expires_in override -- the
            # StorageService itself applies s3_presigned_url_expire_seconds.
            assert "expires_in" not in mock_presign.call_args.kwargs
            assert resp.json()["expires_in"] == 300

    def test_org_a_cannot_download_org_b_file(self, client, db_session):
        tokens_a = _register(client, "DL Org A", "admin@dl-a.com")
        tokens_b = _register(client, "DL Org B", "admin@dl-b.com")
        org_b = _org_id(client, tokens_b["access_token"])
        evidence_b = _create_evidence_for_org(db_session, org_b)
        f_b = _make_file(
            db_session,
            organization_id=org_b,
            evidence_id=evidence_b.id,
            uploaded_by_user_id=_admin_id(db_session, org_b),
        )

        with patch.object(StorageService, "presign_get") as mock_presign:
            resp = _download(client, evidence_b.id, f_b.id, tokens_a["access_token"])
            assert resp.status_code == 404
            mock_presign.assert_not_called()

    def test_org_b_cannot_download_org_a_file(self, client, db_session):
        tokens_a = _register(client, "DL Org A2", "admin@dl-a2.com")
        tokens_b = _register(client, "DL Org B2", "admin@dl-b2.com")
        org_a = _org_id(client, tokens_a["access_token"])
        evidence_a = _create_evidence_for_org(db_session, org_a)
        f_a = _make_file(
            db_session,
            organization_id=org_a,
            evidence_id=evidence_a.id,
            uploaded_by_user_id=_admin_id(db_session, org_a),
        )

        with patch.object(StorageService, "presign_get") as mock_presign:
            resp = _download(client, evidence_a.id, f_a.id, tokens_b["access_token"])
            assert resp.status_code == 404
            mock_presign.assert_not_called()

    def test_cross_tenant_download_makes_zero_presign_calls(self, client, db_session):
        tokens_a = _register(client, "DL Org A3", "admin@dl-a3.com")
        tokens_b = _register(client, "DL Org B3", "admin@dl-b3.com")
        org_b = _org_id(client, tokens_b["access_token"])
        evidence_b = _create_evidence_for_org(db_session, org_b)
        f_b = _make_file(
            db_session,
            organization_id=org_b,
            evidence_id=evidence_b.id,
            uploaded_by_user_id=_admin_id(db_session, org_b),
        )

        with (
            patch.object(StorageService, "presign_get") as mock_presign,
            patch.object(StorageService, "put") as mock_put,
        ):
            _download(client, evidence_b.id, f_b.id, tokens_a["access_token"])
            mock_presign.assert_not_called()
            mock_put.assert_not_called()

    def test_nonexistent_file_returns_safe_404(self, client, db_session):
        tokens = _register(client, "DL Org NFFile", "admin@dl-nffile.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)

        resp = _download(client, evidence.id, uuid.uuid4(), tokens["access_token"])
        assert resp.status_code == 404

    def test_nonexistent_evidence_returns_safe_404(self, client, db_session):
        tokens = _register(client, "DL Org NFEv", "admin@dl-nfev.com")
        resp = _download(client, uuid.uuid4(), uuid.uuid4(), tokens["access_token"])
        assert resp.status_code == 404

    def test_wrong_evidence_correct_file_combination_fails_safely(self, client, db_session):
        tokens = _register(client, "DL Org Mismatch", "admin@dl-mismatch.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence_1 = _create_evidence_for_org(db_session, org_id)
        # Second evidence for the same org/task chain (new aircraft/WO/task).
        admin_id = _admin_id(db_session, org_id)
        aircraft = aircraft_service.create_aircraft(
            db_session,
            organization_id=org_id,
            payload=AircraftCreateRequest(
                registration="N401GH", msn="MSN-GH5", aircraft_type="A320"
            ),
        )
        work_order = work_order_service.create_work_order(
            db_session,
            organization_id=org_id,
            created_by_user_id=admin_id,
            payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-DL-2"),
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
        # File actually belongs to evidence_2, but request names evidence_1.
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence_2.id,
            uploaded_by_user_id=admin_id,
        )

        with patch.object(StorageService, "presign_get") as mock_presign:
            resp = _download(client, evidence_1.id, f.id, tokens["access_token"])
            assert resp.status_code == 404
            mock_presign.assert_not_called()

    def test_correct_evidence_wrong_tenant_file_fails_safely(self, client, db_session):
        tokens_a = _register(client, "DL Org A4", "admin@dl-a4.com")
        tokens_b = _register(client, "DL Org B4", "admin@dl-b4.com")
        org_a = _org_id(client, tokens_a["access_token"])
        org_b = _org_id(client, tokens_b["access_token"])
        evidence_a = _create_evidence_for_org(db_session, org_a)
        # A file with organization_id=org_b but (contrived) evidence_id pointing
        # at org_a's evidence -- must still fail via the org filter.
        f = _make_file(
            db_session,
            organization_id=org_b,
            evidence_id=evidence_a.id,
            uploaded_by_user_id=_admin_id(db_session, org_b),
        )

        with patch.object(StorageService, "presign_get") as mock_presign:
            resp = _download(client, evidence_a.id, f.id, tokens_a["access_token"])
            assert resp.status_code == 404
            mock_presign.assert_not_called()


class TestDownloadableStates:
    @pytest.mark.parametrize(
        "status",
        [EvidenceFileStatus.PENDING, EvidenceFileStatus.FAILED, EvidenceFileStatus.DELETED],
    )
    def test_non_stored_file_cannot_be_downloaded(self, client, db_session, status):
        tokens = _register(
            client, f"State Org {status.value}", f"admin@state-{status.value.lower()}.com"
        )
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
            status=status,
        )

        with patch.object(StorageService, "presign_get") as mock_presign:
            resp = _download(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 409
            mock_presign.assert_not_called()

    def test_stored_file_can_be_downloaded(self, client, db_session):
        tokens = _register(client, "State Org Stored", "admin@state-stored.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
            status=EvidenceFileStatus.STORED,
        )

        with patch.object(StorageService, "presign_get", return_value="https://example.com/ok"):
            resp = _download(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 200


class TestStorageFailure:
    def test_storage_presign_error_becomes_safe_api_error(self, client, db_session):
        tokens = _register(client, "Fail Org 1", "admin@fail-org1.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(
            StorageService,
            "presign_get",
            side_effect=StoragePresignError("boom: bucket=secret-bucket"),
        ):
            resp = _download(client, evidence.id, f.id, tokens["access_token"])
            assert resp.status_code == 502
            body = resp.json()
            assert "secret-bucket" not in body["error"]["message"]
            assert "boom" not in body["error"]["message"]

    def test_full_signed_url_never_logged(self, client, db_session, caplog):
        tokens = _register(client, "Fail Org Log", "admin@fail-log.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )
        secret_url = "https://example.com/signed?X-Amz-Signature=supersecretvalue12345"

        with patch.object(StorageService, "presign_get", return_value=secret_url):
            with caplog.at_level("DEBUG"):
                resp = _download(client, evidence.id, f.id, tokens["access_token"])
        assert resp.status_code == 200
        assert "supersecretvalue12345" not in caplog.text


class TestPresignedUrlSecurity:
    def test_client_cannot_override_expiry(self, client, db_session):
        tokens = _register(client, "Sec Org Expiry", "admin@sec-expiry.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(
            StorageService, "presign_get", return_value="https://example.com/x"
        ) as mock_presign:
            resp = client.get(
                f"/api/v1/evidence/{evidence.id}/files/{f.id}/download?expires_in=999999",
                headers=_auth(tokens["access_token"]),
            )
            assert resp.status_code == 200
            assert resp.json()["expires_in"] == 300
            assert "expires_in" not in mock_presign.call_args.kwargs

    def test_storage_key_not_returned_as_standalone_field(self, client, db_session):
        tokens = _register(client, "Sec Org Key", "admin@sec-key.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )

        with patch.object(StorageService, "presign_get", return_value="https://example.com/x"):
            resp = _download(client, evidence.id, f.id, tokens["access_token"])
            assert set(resp.json().keys()) == {"url", "expires_in"}

    def test_signed_url_generated_only_after_authorization(self, client, db_session):
        tokens = _register(client, "Sec Org Authz", "admin@sec-authz.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence_for_org(db_session, org_id)
        f = _make_file(
            db_session,
            organization_id=org_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=_admin_id(db_session, org_id),
        )
        _add_viewer(db_session, org_id, "viewer@sec-authz.com")
        # VIEWER still has EVIDENCE_READ, so use an unauthenticated call to
        # prove the presign never happens without any valid auth at all.
        with patch.object(StorageService, "presign_get") as mock_presign:
            resp = client.get(f"/api/v1/evidence/{evidence.id}/files/{f.id}/download")
            assert resp.status_code == 401
            mock_presign.assert_not_called()
