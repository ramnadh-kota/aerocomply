"""M17.1: real object-storage end-to-end tests for the Evidence file lifecycle.

Every test here talks to an ACTUAL S3-compatible HTTP server via a real
StorageService instance (see conftest.py's `storage_service` fixture) --
never a StorageService double, never a mocked boto3 client. The only thing
"faked" per test is which StorageService instance the FastAPI app's router
uses for that one request (see `_use_real_storage` below), exactly the same
kind of dependency substitution the rest of this test suite already uses
(`patch.object(StorageService, "put", ...)`), just pointed at a real
endpoint instead of a Mock.

See README.md in this directory for how to start a real S3-compatible
endpoint and run these tests -- they are excluded from the default suite
(pyproject.toml's `addopts = "-m 'not real_storage'"`) since ordinary CI/dev
runs are not guaranteed to have one available.
"""

import hashlib
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select

from app.core.deps import get_db_session
from app.main import app
from app.models.evidence import EvidenceFile, EvidenceFileStatus
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.task import TaskCreateRequest
from app.schemas.work_order import WorkOrderCreateRequest
from app.services import (
    aircraft_service,
    evidence_service,
    work_order_service,
)
from app.services.evidence_reconciliation_service import (
    ReconciliationClassification,
    apply_repairs,
    scan_evidence_files,
)
from app.services.storage.exceptions import StorageUnavailableError
from app.services.storage.keys import build_object_key
from app.services.storage.service import StorageService

pytestmark = pytest.mark.real_storage

# A minimal, structurally-valid PDF -- deterministic test bytes, no external
# download, small enough to be a trivial upload.
_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 3 3]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
)


@contextmanager
def _use_real_storage(storage_service: StorageService):
    """The router (app/api/v1/evidence.py) calls get_storage_service()
    directly, not via FastAPI Depends -- so real-storage substitution works
    exactly like this suite's existing StorageService mocking, just
    returning a real, endpoint-pointed instance instead of a Mock."""
    with patch("app.api.v1.evidence.get_storage_service", return_value=storage_service):
        yield


def _register(client, org_name, email):
    from tests.integration.conftest import make_platform_admin_headers

    db_session = next(app.dependency_overrides[get_db_session]())
    headers = make_platform_admin_headers(client, db_session)
    resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": email,
            "admin_full_name": "Admin",
            "admin_password": "supersecret123",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _org_id(client, token):
    return uuid.UUID(client.get("/api/v1/auth/me", headers=_auth(token)).json()["organization_id"])


def _admin_id(db_session, org_id):
    admin = db_session.execute(select(User).where(User.organization_id == org_id)).scalars().first()
    assert admin is not None
    return admin.id


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


def _upload(client, evidence_id, token, storage_service, *, content=_PDF_BYTES):
    with _use_real_storage(storage_service):
        return client.post(
            f"/api/v1/evidence/{evidence_id}/files",
            headers=_auth(token),
            files={"file": ("report.pdf", content, "application/pdf")},
        )


class TestBucketConnectivity:
    def test_can_connect_to_configured_bucket(self, storage_service):
        # A HEAD check for a definitely-nonexistent key must cleanly return
        # False (not raise) -- proving the client can actually reach the
        # configured bucket/endpoint/credentials, not just that construction
        # succeeded (StorageService's own construction never touches the
        # network at all -- see tests/unit/test_storage_service.py).
        assert storage_service.object_exists(key=f"connectivity-check/{uuid.uuid4()}") is False


class TestUpload:
    def test_upload_succeeds_and_object_exists_with_expected_key_and_checksum(
        self, client, db_session, storage_service
    ):
        tokens = _register(client, "Real Storage Org 1", "admin@real-storage-1.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence(db_session, org_id, _admin_id(db_session, org_id), "WO-RS-1")

        resp = _upload(client, evidence.id, tokens["access_token"], storage_service)

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == EvidenceFileStatus.STORED.value

        db_session.expire_all()
        row = db_session.get(EvidenceFile, uuid.UUID(body["id"]))
        assert row is not None
        assert row.status == EvidenceFileStatus.STORED.value

        # Real object-existence check against the real endpoint.
        assert storage_service.object_exists(key=row.storage_key) is True

        # Storage key follows the canonical builder's namespace contract.
        expected_prefix = f"evidence/{org_id}/{evidence.id}/"
        assert row.storage_key.startswith(expected_prefix)
        assert row.storage_key.endswith("_report.pdf")

        # Checksum independently recomputed, not merely trusted from the DB.
        assert row.checksum_sha256 == hashlib.sha256(_PDF_BYTES).hexdigest()


class TestDownload:
    def test_download_url_is_real_and_bytes_match_upload(self, client, db_session, storage_service):
        tokens = _register(client, "Real Storage Org 2", "admin@real-storage-2.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence(db_session, org_id, _admin_id(db_session, org_id), "WO-RS-2")
        upload_resp = _upload(client, evidence.id, tokens["access_token"], storage_service)
        file_id = upload_resp.json()["id"]

        with _use_real_storage(storage_service):
            dl_resp = client.get(
                f"/api/v1/evidence/{evidence.id}/files/{file_id}/download",
                headers=_auth(tokens["access_token"]),
            )
        assert dl_resp.status_code == 200
        body = dl_resp.json()
        assert body["expires_in"] == storage_service._default_expires_in
        assert body["url"]

        # Actually fetch the presigned URL over real HTTP and compare bytes --
        # not merely asserting a URL string exists.
        downloaded = httpx.get(body["url"], timeout=10.0)
        assert downloaded.status_code == 200
        assert downloaded.content == _PDF_BYTES


class TestDelete:
    def test_delete_removes_real_object_and_marks_deleted(
        self, client, db_session, storage_service
    ):
        tokens = _register(client, "Real Storage Org 3", "admin@real-storage-3.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence(db_session, org_id, _admin_id(db_session, org_id), "WO-RS-3")
        upload_resp = _upload(client, evidence.id, tokens["access_token"], storage_service)
        file_id = upload_resp.json()["id"]
        db_session.expire_all()
        storage_key = db_session.get(EvidenceFile, uuid.UUID(file_id)).storage_key
        assert storage_service.object_exists(key=storage_key) is True

        with _use_real_storage(storage_service):
            del_resp = client.delete(
                f"/api/v1/evidence/{evidence.id}/files/{file_id}",
                headers=_auth(tokens["access_token"]),
            )
        assert del_resp.status_code == 204

        db_session.expire_all()
        row = db_session.get(EvidenceFile, uuid.UUID(file_id))
        assert row.status == EvidenceFileStatus.DELETED.value
        assert row.deleted_at is not None
        # The real object is actually gone, not just the DB row.
        assert storage_service.object_exists(key=storage_key) is False

    def test_download_rejected_after_delete_no_usable_url(
        self, client, db_session, storage_service
    ):
        tokens = _register(client, "Real Storage Org 4", "admin@real-storage-4.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence(db_session, org_id, _admin_id(db_session, org_id), "WO-RS-4")
        upload_resp = _upload(client, evidence.id, tokens["access_token"], storage_service)
        file_id = upload_resp.json()["id"]
        with _use_real_storage(storage_service):
            client.delete(
                f"/api/v1/evidence/{evidence.id}/files/{file_id}",
                headers=_auth(tokens["access_token"]),
            )
            dl_resp = client.get(
                f"/api/v1/evidence/{evidence.id}/files/{file_id}/download",
                headers=_auth(tokens["access_token"]),
            )
        assert dl_resp.status_code == 409
        assert "url" not in dl_resp.json()


class TestReconciliationAgainstRealStorage:
    def test_stored_with_real_object_is_consistent(self, db_session, storage_service):
        org_id, user_id, evidence = self._org_evidence(db_session, "WO-RS-R1")
        key = self._put_real_object(storage_service, org_id, evidence.id)
        row = self._file(db_session, evidence, user_id, key, EvidenceFileStatus.STORED)

        result = scan_evidence_files(db_session, storage_service, organization_id=org_id)
        assert result.consistent_count == 1
        assert result.anomaly_count == 0
        assert row.id not in {a.evidence_file_id for a in result.anomalies}

    def test_stored_with_missing_real_object_is_manual_review(self, db_session, storage_service):
        org_id, user_id, evidence = self._org_evidence(db_session, "WO-RS-R2")
        key = build_object_key(
            namespace="evidence",
            organization_id=org_id,
            resource_id=evidence.id,
            file_id=uuid.uuid4(),
            filename="never-uploaded.pdf",
        )
        # Deliberately never put an object at this key.
        row = self._file(db_session, evidence, user_id, key, EvidenceFileStatus.STORED)

        result = scan_evidence_files(db_session, storage_service, organization_id=org_id)
        anomaly = next(a for a in result.anomalies if a.evidence_file_id == row.id)
        assert anomaly.classification == ReconciliationClassification.MANUAL_REVIEW
        assert anomaly.object_exists is False

    def test_failed_with_missing_real_object_is_no_action(self, db_session, storage_service):
        org_id, user_id, evidence = self._org_evidence(db_session, "WO-RS-R3")
        key = build_object_key(
            namespace="evidence",
            organization_id=org_id,
            resource_id=evidence.id,
            file_id=uuid.uuid4(),
            filename="failed.pdf",
        )
        self._file(db_session, evidence, user_id, key, EvidenceFileStatus.FAILED)

        result = scan_evidence_files(db_session, storage_service, organization_id=org_id)
        assert result.anomaly_count == 0
        assert result.consistent_count == 1

    def test_failed_with_existing_real_object_is_manual_review(self, db_session, storage_service):
        org_id, user_id, evidence = self._org_evidence(db_session, "WO-RS-R4")
        key = self._put_real_object(storage_service, org_id, evidence.id)
        row = self._file(db_session, evidence, user_id, key, EvidenceFileStatus.FAILED)

        result = scan_evidence_files(db_session, storage_service, organization_id=org_id)
        anomaly = next(a for a in result.anomalies if a.evidence_file_id == row.id)
        assert anomaly.classification == ReconciliationClassification.MANUAL_REVIEW

    def test_deleted_with_existing_real_object_is_repaired_and_audited(
        self, db_session, storage_service
    ):
        org_id, user_id, evidence = self._org_evidence(db_session, "WO-RS-R5")
        key = self._put_real_object(storage_service, org_id, evidence.id)
        row = self._file(db_session, evidence, user_id, key, EvidenceFileStatus.DELETED)
        assert storage_service.object_exists(key=key) is True

        result = scan_evidence_files(db_session, storage_service, organization_id=org_id)
        anomaly = next(a for a in result.anomalies if a.evidence_file_id == row.id)
        assert anomaly.classification == ReconciliationClassification.SAFE_TO_REPAIR

        repaired = apply_repairs(
            db_session, storage_service, anomalies=result.anomalies, actor_user_id=user_id
        )
        assert repaired == 1
        # The real object is actually gone after repair.
        assert storage_service.object_exists(key=key) is False

        from app.models.audit_event import AuditEvent

        event = db_session.execute(
            select(AuditEvent).where(
                AuditEvent.action == "evidence_file.reconciliation_repaired",
                AuditEvent.entity_id == row.id,
            )
        ).scalar_one()
        assert event.organization_id == org_id

    def test_deleted_with_missing_real_object_is_no_action(self, db_session, storage_service):
        org_id, user_id, evidence = self._org_evidence(db_session, "WO-RS-R6")
        key = build_object_key(
            namespace="evidence",
            organization_id=org_id,
            resource_id=evidence.id,
            file_id=uuid.uuid4(),
            filename="already-gone.pdf",
        )
        self._file(db_session, evidence, user_id, key, EvidenceFileStatus.DELETED)

        result = scan_evidence_files(db_session, storage_service, organization_id=org_id)
        assert result.anomaly_count == 0

    def test_storage_unavailable_is_infrastructure_failure_not_missing(
        self, db_session, real_storage_settings
    ):
        org_id, user_id, evidence = self._org_evidence(db_session, "WO-RS-R7")
        row = self._file(
            db_session, evidence, user_id, "evidence/unreachable/key.pdf", EvidenceFileStatus.STORED
        )
        # An endpoint nothing is listening on -- a real, genuine connection
        # failure, not a StorageService double raising on command.
        unreachable = StorageService(
            real_storage_settings.model_copy(update={"s3_endpoint_url": "http://127.0.0.1:1"})
        )

        result = scan_evidence_files(db_session, unreachable, organization_id=org_id)
        anomaly = next(a for a in result.anomalies if a.evidence_file_id == row.id)
        assert anomaly.classification == ReconciliationClassification.INFRASTRUCTURE_FAILURE
        assert anomaly.object_exists is None
        assert result.anomaly_count == 0  # infrastructure failures are not counted as anomalies
        assert result.repaired_count == 0

    def test_object_exists_raises_unavailable_for_unreachable_endpoint(self, real_storage_settings):
        unreachable = StorageService(
            real_storage_settings.model_copy(update={"s3_endpoint_url": "http://127.0.0.1:1"})
        )
        with pytest.raises(StorageUnavailableError):
            unreachable.object_exists(key="does-not-matter")

    def test_reconciliation_does_not_cross_tenant_boundaries(self, db_session, storage_service):
        org_a, user_a, evidence_a = self._org_evidence(db_session, "WO-RS-T1")
        org_b, user_b, evidence_b = self._org_evidence(db_session, "WO-RS-T2")
        key_a = self._put_real_object(storage_service, org_a, evidence_a.id)
        # org_b's file has a missing object -- an anomaly that must never be
        # attributed to org_a, and must never even be checked when scanning
        # org_a only.
        key_b = build_object_key(
            namespace="evidence",
            organization_id=org_b,
            resource_id=evidence_b.id,
            file_id=uuid.uuid4(),
            filename="b-missing.pdf",
        )
        self._file(db_session, evidence_a, user_a, key_a, EvidenceFileStatus.STORED)
        self._file(db_session, evidence_b, user_b, key_b, EvidenceFileStatus.STORED)
        assert key_a != key_b
        assert str(org_a) in key_a
        assert str(org_b) in key_b

        result = scan_evidence_files(db_session, storage_service, organization_id=org_a)
        assert result.scanned_count == 1
        assert result.anomaly_count == 0  # org_a's own file is consistent
        assert all(a.organization_id == org_a for a in result.anomalies)

    # --- shared helpers ---

    def _org_evidence(self, db_session, wo_number):
        from app.models.organization import Organization

        org_id = uuid.uuid4()
        db_session.add(Organization(id=org_id, name=f"Real Storage Recon {org_id}"))
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
        evidence = _create_evidence(db_session, org_id, user.id, wo_number)
        return org_id, user.id, evidence

    def _put_real_object(self, storage_service, org_id, evidence_id) -> str:
        key = build_object_key(
            namespace="evidence",
            organization_id=org_id,
            resource_id=evidence_id,
            file_id=uuid.uuid4(),
            filename="orphan.pdf",
        )
        storage_service.put(key=key, body=_PDF_BYTES, content_type="application/pdf")
        return key

    def _file(self, db_session, evidence, uploaded_by_user_id, storage_key, status):
        evidence_file = EvidenceFile(
            organization_id=evidence.organization_id,
            evidence_id=evidence.id,
            uploaded_by_user_id=uploaded_by_user_id,
            original_filename="report.pdf",
            content_type="application/pdf",
            size_bytes=len(_PDF_BYTES),
            storage_key=storage_key,
            checksum_sha256=hashlib.sha256(_PDF_BYTES).hexdigest(),
            status=status.value,
        )
        db_session.add(evidence_file)
        db_session.commit()
        db_session.refresh(evidence_file)
        return evidence_file


class TestSecurity:
    def test_evidence_file_response_never_exposes_storage_key(
        self, client, db_session, storage_service
    ):
        tokens = _register(client, "Real Storage Org Sec", "admin@real-storage-sec.com")
        org_id = _org_id(client, tokens["access_token"])
        evidence = _create_evidence(db_session, org_id, _admin_id(db_session, org_id), "WO-RS-SEC1")
        resp = _upload(client, evidence.id, tokens["access_token"], storage_service)
        assert "storage_key" not in resp.json()

    def test_cross_tenant_download_rejected_against_real_storage(
        self, client, db_session, storage_service
    ):
        tokens_a = _register(client, "Real Storage Org A", "admin@real-storage-a.com")
        tokens_b = _register(client, "Real Storage Org B", "admin@real-storage-b.com")
        org_a = _org_id(client, tokens_a["access_token"])
        evidence_a = _create_evidence(db_session, org_a, _admin_id(db_session, org_a), "WO-RS-SEC2")
        upload_resp = _upload(client, evidence_a.id, tokens_a["access_token"], storage_service)
        file_id = upload_resp.json()["id"]

        with _use_real_storage(storage_service):
            resp = client.get(
                f"/api/v1/evidence/{evidence_a.id}/files/{file_id}/download",
                headers=_auth(tokens_b["access_token"]),
            )
        assert resp.status_code == 404
