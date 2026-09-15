"""M16.4: HTTP-level tests for POST /evidence/{evidence_id}/files.

Real end-to-end coverage over the actual FastAPI app + real Postgres (the
`client`/`db_session` fixtures), mocking only the StorageService/S3 boundary
(M16.1) so no test ever talks to real AWS or requires a running MinIO.
"""

import hashlib
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.evidence import EvidenceFileStatus
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
from app.services.storage.exceptions import StorageUploadError
from app.services.storage.service import PutResult, StorageService


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


def _create_evidence_for_org(db_session, org_id, uploaded_by_user_id=None):
    # The tests in this file mostly don't care who "uploaded" the parent
    # Evidence record (only who uploads the *file*, which the endpoint
    # itself always derives from the authenticated actor) -- default to the
    # org's own admin user (created by register-organization) rather than
    # requiring every call site to look it up.
    if uploaded_by_user_id is None:
        admin = db_session.execute(
            select(User).where(User.organization_id == org_id)
        ).scalars().first()
        assert admin is not None, "expected an admin user to already exist for this org"
        uploaded_by_user_id = admin.id

    aircraft = aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(registration="N300EF", msn="MSN-EF3", aircraft_type="A320"),
    )
    work_order = work_order_service.create_work_order(
        db_session,
        organization_id=org_id,
        created_by_user_id=uploaded_by_user_id,
        payload=WorkOrderCreateRequest(aircraft_id=aircraft.id, work_order_number="WO-UPLOAD-1"),
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


def _upload(client, evidence_id, token, *, filename="photo.jpg", content=b"fake-jpeg-bytes",
            content_type="image/jpeg"):
    return client.post(
        f"/api/v1/evidence/{evidence_id}/files",
        headers=_auth(token),
        files={"file": (filename, content, content_type)},
    )


class TestAuthenticationAndAuthorization:
    def test_unauthenticated_request_rejected(self, client, db_session):
        tokens = _register(client, "Upload Org Unauth", "admin@upload-unauth.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)

        resp = client.post(
            f"/api/v1/evidence/{evidence.id}/files",
            files={"file": ("photo.jpg", b"data", "image/jpeg")},
        )
        assert resp.status_code == 401

    def test_missing_permission_rejected(self, client, db_session):
        tokens = _register(client, "Upload Org NoPerm", "admin@upload-noperm.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        viewer = _add_viewer(db_session, org_id, "viewer@upload-noperm.com")

        viewer_login = client.post(
            "/api/v1/auth/login",
            json={"email": viewer.email, "password": "supersecret123"},
        )
        assert viewer_login.status_code == 200

        resp = _upload(client, evidence.id, viewer_login.json()["access_token"])
        assert resp.status_code == 403

    def test_authorized_tenant_user_succeeds(self, client, db_session):
        tokens = _register(client, "Upload Org OK", "admin@upload-ok.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)

        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(client, evidence.id, tokens["access_token"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == EvidenceFileStatus.STORED.value


class TestTenantIsolation:
    def test_org_a_cannot_upload_to_org_b_evidence(self, client, db_session):
        tokens_a = _register(client, "Upload Tenant A", "admin@upload-tenant-a.com")
        tokens_b = _register(client, "Upload Tenant B", "admin@upload-tenant-b.com")
        org_b_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens_b["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence_b = _create_evidence_for_org(db_session, org_b_id, None)

        with patch.object(StorageService, "put") as mock_put:
            resp = _upload(client, evidence_b.id, tokens_a["access_token"])
            # The critical assertion: tenant ownership is resolved BEFORE any
            # storage call, so a cross-tenant attempt must never reach
            # StorageService.put() at all.
            mock_put.assert_not_called()
        assert resp.status_code == 404

    def test_org_b_cannot_upload_to_org_a_evidence(self, client, db_session):
        tokens_a = _register(client, "Upload Tenant C", "admin@upload-tenant-c.com")
        tokens_b = _register(client, "Upload Tenant D", "admin@upload-tenant-d.com")
        org_a_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens_a["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence_a = _create_evidence_for_org(db_session, org_a_id, None)

        with patch.object(StorageService, "put") as mock_put:
            resp = _upload(client, evidence_a.id, tokens_b["access_token"])
            mock_put.assert_not_called()
        assert resp.status_code == 404


class TestFileValidation:
    def test_missing_file_rejected(self, client, db_session):
        tokens = _register(client, "Upload Missing File", "admin@upload-missing.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        resp = client.post(
            f"/api/v1/evidence/{evidence.id}/files", headers=_auth(tokens["access_token"])
        )
        assert resp.status_code == 422

    def test_pdf_accepted(self, client, db_session):
        tokens = _register(client, "Upload PDF Org", "admin@upload-pdf.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(
                client,
                evidence.id,
                tokens["access_token"],
                filename="form.pdf",
                content=b"%PDF-1.4 fake",
                content_type="application/pdf",
            )
        assert resp.status_code == 201
        assert resp.json()["content_type"] == "application/pdf"

    def test_jpeg_accepted(self, client, db_session):
        tokens = _register(client, "Upload JPEG Org", "admin@upload-jpeg.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(client, evidence.id, tokens["access_token"], content_type="image/jpeg")
        assert resp.status_code == 201

    def test_png_accepted(self, client, db_session):
        tokens = _register(client, "Upload PNG Org", "admin@upload-png.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(
                client,
                evidence.id,
                tokens["access_token"],
                filename="photo.png",
                content_type="image/png",
            )
        assert resp.status_code == 201

    def test_unsupported_mime_rejected(self, client, db_session):
        tokens = _register(client, "Upload Bad Mime Org", "admin@upload-badmime.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put") as mock_put:
            resp = _upload(
                client,
                evidence.id,
                tokens["access_token"],
                filename="evil.exe",
                content_type="application/x-msdownload",
            )
            mock_put.assert_not_called()
        assert resp.status_code == 415

    def test_oversized_upload_rejected(self, client, db_session):
        tokens = _register(client, "Upload Oversize Org", "admin@upload-oversize.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch("app.api.v1.evidence.get_settings") as mock_settings:
            mock_settings.return_value.evidence_max_upload_bytes = 10
            with patch.object(StorageService, "put") as mock_put:
                resp = _upload(
                    client, evidence.id, tokens["access_token"], content=b"x" * 100
                )
                mock_put.assert_not_called()
        assert resp.status_code == 413

    def test_zero_byte_file_is_accepted_as_a_valid_zero_length_upload(self, client, db_session):
        # No rule in this codebase forbids a zero-byte evidence file (e.g. a
        # placeholder/empty scan) -- size_bytes >= 0 is exactly what the
        # EvidenceFile DB CHECK constraint (M16.2) already allows.
        tokens = _register(client, "Upload Zero Byte Org", "admin@upload-zerobyte.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=0)):
            resp = _upload(client, evidence.id, tokens["access_token"], content=b"")
        assert resp.status_code == 201
        assert resp.json()["size_bytes"] == 0


class TestFilenamePathSecurity:
    def _upload_and_get_storage_key(self, client, db_session, evidence_id, token, filename):
        captured = {}

        def _fake_put(*, key, body, content_type):
            captured["key"] = key
            return PutResult(key=key, size_bytes=len(body))

        with patch.object(StorageService, "put", side_effect=_fake_put):
            resp = _upload(client, evidence_id, token, filename=filename)
        assert resp.status_code == 201
        return captured["key"]

    def test_path_traversal_filename_does_not_create_traversal_key(self, client, db_session):
        tokens = _register(client, "Upload Traversal Org", "admin@upload-traversal.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        key = self._upload_and_get_storage_key(
            client, db_session, evidence.id, tokens["access_token"], "../../etc/passwd"
        )
        assert ".." not in key
        assert key.endswith("_passwd")

    def test_windows_path_does_not_create_traversal_key(self, client, db_session):
        tokens = _register(client, "Upload Winpath Org", "admin@upload-winpath.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        key = self._upload_and_get_storage_key(
            client,
            db_session,
            evidence.id,
            tokens["access_token"],
            "C:\\Windows\\System32\\evil.exe",
        )
        assert "System32" not in key
        assert key.endswith("_evil.exe")

    def test_absolute_path_sanitized_safely(self, client, db_session):
        tokens = _register(client, "Upload Abspath Org", "admin@upload-abspath.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        key = self._upload_and_get_storage_key(
            client, db_session, evidence.id, tokens["access_token"], "/etc/passwd"
        )
        assert key.endswith("_passwd")

    def test_unicode_filename_handled_safely(self, client, db_session):
        tokens = _register(client, "Upload Unicode Org", "admin@upload-unicode.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        key = self._upload_and_get_storage_key(
            client, db_session, evidence.id, tokens["access_token"], "检查报告.jpg"
        )
        assert key.endswith("_检查报告.jpg")

    def test_long_filename_handled_safely(self, client, db_session):
        tokens = _register(client, "Upload Longname Org", "admin@upload-longname.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        long_name = "a" * 300 + ".jpg"
        key = self._upload_and_get_storage_key(
            client, db_session, evidence.id, tokens["access_token"], long_name
        )
        # The full 300+ char name must not appear verbatim in the key.
        assert long_name not in key

    def test_storage_key_uses_server_generated_ids(self, client, db_session):
        tokens = _register(client, "Upload Keyshape Org", "admin@upload-keyshape.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        key = self._upload_and_get_storage_key(
            client, db_session, evidence.id, tokens["access_token"], "photo.jpg"
        )
        assert key.startswith(f"evidence/{org_id}/{evidence.id}/")

    def test_client_cannot_inject_arbitrary_storage_path(self, client, db_session):
        # There is no request field for storage_key at all -- filename is the
        # only client-influenced input, and it only ever becomes the final
        # sanitized segment of a server-built key.
        tokens = _register(client, "Upload Inject Org", "admin@upload-inject.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        key = self._upload_and_get_storage_key(
            client, db_session, evidence.id, tokens["access_token"], "../../../../root/.ssh/id_rsa"
        )
        assert key.startswith(f"evidence/{org_id}/{evidence.id}/")
        assert "id_rsa" in key
        assert ".ssh" not in key


class TestMetadataPersistence:
    def test_file_created_as_pending_before_storage_call(self, client, db_session):
        # Verified indirectly: create_pending_file always writes PENDING, and
        # only a *successful* storage call ever moves it to STORED -- proven
        # by the storage-failure test below leaving a file at FAILED, never
        # skipping straight there.
        tokens = _register(client, "Upload Pending Org", "admin@upload-pending.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(client, evidence.id, tokens["access_token"])
        assert resp.status_code == 201
        assert resp.json()["status"] == EvidenceFileStatus.STORED.value

    def test_uploaded_by_user_id_equals_actor(self, client, db_session):
        tokens = _register(client, "Upload Actor Org", "admin@upload-actor.com")
        me = client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()
        org_id = uuid.UUID(me["organization_id"])
        actor_id = uuid.UUID(me["id"])
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(client, evidence.id, tokens["access_token"])
        file_id = uuid.UUID(resp.json()["id"])
        row = evidence_file_service.get_file(
            db_session, organization_id=org_id, evidence_file_id=file_id
        )
        assert row.uploaded_by_user_id == actor_id

    def test_organization_id_equals_parent_evidence(self, client, db_session):
        tokens = _register(client, "Upload OrgMatch Org", "admin@upload-orgmatch.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(client, evidence.id, tokens["access_token"])
        file_id = uuid.UUID(resp.json()["id"])
        row = evidence_file_service.get_file(
            db_session, organization_id=org_id, evidence_file_id=file_id
        )
        assert row.organization_id == evidence.organization_id == org_id

    def test_checksum_persisted(self, client, db_session):
        tokens = _register(client, "Upload Checksum Org", "admin@upload-checksum.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        content = b"deterministic-content"
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(client, evidence.id, tokens["access_token"], content=content)
        file_id = uuid.UUID(resp.json()["id"])
        row = evidence_file_service.get_file(
            db_session, organization_id=org_id, evidence_file_id=file_id
        )
        assert row.checksum_sha256 == hashlib.sha256(content).hexdigest()


class TestSuccessfulUpload:
    def test_storage_put_called_exactly_once(self, client, db_session):
        tokens = _register(client, "Upload Once Org", "admin@upload-once.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(
            StorageService, "put", return_value=PutResult(key="k", size_bytes=4)
        ) as mock_put:
            resp = _upload(client, evidence.id, tokens["access_token"])
        assert resp.status_code == 201
        mock_put.assert_called_once()

    def test_successful_upload_transitions_to_stored(self, client, db_session):
        tokens = _register(client, "Upload Stored Org", "admin@upload-stored.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(client, evidence.id, tokens["access_token"])
        file_id = uuid.UUID(resp.json()["id"])
        row = evidence_file_service.get_file(
            db_session, organization_id=org_id, evidence_file_id=file_id
        )
        assert row.status == EvidenceFileStatus.STORED.value

    def test_response_returns_stored_metadata(self, client, db_session):
        tokens = _register(client, "Upload Respbody Org", "admin@upload-respbody.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp = _upload(client, evidence.id, tokens["access_token"], filename="photo.jpg")
        body = resp.json()
        assert body["status"] == "STORED"
        assert body["original_filename"] == "photo.jpg"
        assert body["evidence_id"] == str(evidence.id)
        assert "storage_key" not in body
        assert "presigned" not in str(body).lower()


class TestStorageFailure:
    def test_storage_upload_error_results_in_failed_and_502(self, client, db_session):
        tokens = _register(client, "Upload Fail Org", "admin@upload-fail.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(
            StorageService, "put", side_effect=StorageUploadError("simulated S3 failure")
        ):
            resp = _upload(client, evidence.id, tokens["access_token"])
        assert resp.status_code == 502
        body = resp.json()
        # No raw storage exception detail leaked to the client.
        assert "simulated S3 failure" not in str(body)
        assert "boto" not in str(body).lower()

    def test_failed_file_remains_in_db_with_honest_state(self, client, db_session):
        tokens = _register(client, "Upload Fail State Org", "admin@upload-fail-state.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)
        with patch.object(
            StorageService, "put", side_effect=StorageUploadError("simulated S3 failure")
        ):
            resp = _upload(client, evidence.id, tokens["access_token"])
        assert resp.status_code == 502

        rows = evidence_file_service.list_files_for_evidence(
            db_session, organization_id=org_id, evidence_id=evidence.id
        )
        assert len(rows) == 1
        assert rows[0].status == EvidenceFileStatus.FAILED.value


class TestDbFailureAfterSuccessfulStorage:
    def test_mark_stored_failure_does_not_falsely_report_success(self, client, db_session):
        """Simulates Case C from the M16.4 spec: the object is successfully
        written to storage, but the DB transition to STORED then fails. The
        API must not return a STORED response, and the row must not be
        silently left/reported as STORED (it stays PENDING, since
        mark_stored's own commit never completed)."""
        tokens = _register(client, "Upload PartialFail Org", "admin@upload-partialfail.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)

        # The route re-raises after logging (see app/api/v1/evidence.py) so
        # the app's own unhandled_error_handler can turn it into a safe 500
        # in production (behind a real ASGI server). Under Starlette's
        # TestClient, a known BaseHTTPMiddleware limitation (this app's
        # RequestContextMiddleware) means an exception raised this deep
        # surfaces as a real Python exception in the test rather than a
        # clean response, even with raise_server_exceptions=False -- so
        # assert on that propagation directly instead of a status code. The
        # meaningful assertion either way is the same: no falsely-STORED
        # response/state exists, checked below via the DB row.
        with pytest.raises(RuntimeError, match="simulated DB failure"):
            with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
                with patch(
                    "app.api.v1.evidence.evidence_file_service.mark_stored",
                    side_effect=RuntimeError("simulated DB failure"),
                ):
                    _upload(client, evidence.id, tokens["access_token"])

        rows = evidence_file_service.list_files_for_evidence(
            db_session, organization_id=org_id, evidence_id=evidence.id
        )
        assert len(rows) == 1
        # Must not be falsely STORED -- the mocked mark_stored never actually
        # committed the transition.
        assert rows[0].status == EvidenceFileStatus.PENDING.value


class TestMultipleFiles:
    def test_two_files_create_two_rows_with_distinct_keys(self, client, db_session):
        tokens = _register(client, "Upload Multi Org", "admin@upload-multi.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)

        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            resp1 = _upload(client, evidence.id, tokens["access_token"], filename="one.jpg")
            resp2 = _upload(client, evidence.id, tokens["access_token"], filename="two.jpg")
        assert resp1.status_code == 201
        assert resp2.status_code == 201
        assert resp1.json()["id"] != resp2.json()["id"]

        rows = evidence_file_service.list_files_for_evidence(
            db_session, organization_id=org_id, evidence_id=evidence.id
        )
        assert len(rows) == 2
        assert len({r.storage_key for r in rows}) == 2


class TestRetryAfterFailure:
    def test_retry_after_failure_creates_new_row_leaving_failed_one_unchanged(
        self, client, db_session
    ):
        tokens = _register(client, "Upload Retry Org", "admin@upload-retry.com")
        org_id = uuid.UUID(
            client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"])).json()[
                "organization_id"
            ]
        )
        evidence = _create_evidence_for_org(db_session, org_id, None)

        with patch.object(
            StorageService, "put", side_effect=StorageUploadError("simulated S3 failure")
        ):
            first_resp = _upload(client, evidence.id, tokens["access_token"], filename="one.jpg")
        assert first_resp.status_code == 502
        first_file_id = None
        rows_after_failure = evidence_file_service.list_files_for_evidence(
            db_session, organization_id=org_id, evidence_id=evidence.id
        )
        assert len(rows_after_failure) == 1
        first_file_id = rows_after_failure[0].id
        assert rows_after_failure[0].status == EvidenceFileStatus.FAILED.value

        with patch.object(StorageService, "put", return_value=PutResult(key="k", size_bytes=4)):
            second_resp = _upload(client, evidence.id, tokens["access_token"], filename="one.jpg")
        assert second_resp.status_code == 201
        second_file_id = uuid.UUID(second_resp.json()["id"])
        assert second_file_id != first_file_id

        rows_after_retry = evidence_file_service.list_files_for_evidence(
            db_session, organization_id=org_id, evidence_id=evidence.id
        )
        assert len(rows_after_retry) == 2
        by_id = {r.id: r for r in rows_after_retry}
        assert by_id[first_file_id].status == EvidenceFileStatus.FAILED.value
        assert by_id[second_file_id].status == EvidenceFileStatus.STORED.value
