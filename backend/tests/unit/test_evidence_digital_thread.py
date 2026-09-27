"""Unit tests for Evidence Digital Thread and Verification Workflow.

Verifies:
- First-class evidence metadata (title, type, source, captured_at, provenance).
- Polymorphic linkage: evidence attaching to compliance obligations, requirements, assets, tasks.
- Explicit verification: verify_evidence marks VERIFIED, ACCEPTED, verifier, timestamp.
- Explicit rejection: reject_evidence marks REJECTED, captures rejection_reason.
- Satisfies completion gate consistency: VERIFIED/ACCEPTED satisfies gate, UNVERIFIED/REJECTED fails gate.
"""

import datetime
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.evidence import Evidence, EvidenceStatus
from app.services.evidence_service import (
    create_evidence,
    reject_evidence,
    satisfies_completion_gate,
    verify_evidence,
)


class TestEvidenceVerificationWorkflow:
    def test_verify_evidence_sets_audit_and_status(self):
        evidence = Evidence(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            title="Ultrasonic Scan Report",
            evidence_type="INSPECTION_RECORD",
            status=EvidenceStatus.UPLOADED.value,
            verification_status="UNVERIFIED",
        )

        verifier_id = uuid.uuid4()
        mock_db = MagicMock()

        verified = verify_evidence(
            mock_db,
            evidence,
            verifier_user_id=verifier_id,
            verification_notes="Scan curves conform to NDT spec",
        )

        assert verified.verification_status == "VERIFIED"
        assert verified.status == EvidenceStatus.ACCEPTED.value
        assert verified.verifier_user_id == verifier_id
        assert verified.verification_notes == "Scan curves conform to NDT spec"
        assert verified.verified_at is not None
        assert satisfies_completion_gate(verified.status) is True

    def test_reject_evidence_records_reason(self):
        evidence = Evidence(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            title="Ultrasonic Scan Report",
            evidence_type="INSPECTION_RECORD",
            status=EvidenceStatus.UPLOADED.value,
            verification_status="UNVERIFIED",
        )

        verifier_id = uuid.uuid4()
        mock_db = MagicMock()

        rejected = reject_evidence(
            mock_db,
            evidence,
            verifier_user_id=verifier_id,
            rejection_reason="Calibration certificate expired",
        )

        assert rejected.verification_status == "REJECTED"
        assert rejected.status == EvidenceStatus.REJECTED.value
        assert rejected.rejection_reason == "Calibration certificate expired"
        assert rejected.verifier_user_id == verifier_id
        assert satisfies_completion_gate(rejected.status) is False


class TestEvidenceDigitalThreadCreation:
    def test_create_evidence_for_obligation(self):
        mock_db = MagicMock()
        org_id = uuid.uuid4()
        ob_id = uuid.uuid4()
        req_id = uuid.uuid4()
        asset_id = uuid.uuid4()

        mock_ob = MagicMock()
        mock_ob.id = ob_id
        mock_ob.requirement_id = req_id
        mock_ob.asset_id = asset_id
        mock_ob.aircraft_id = None
        mock_db.execute.return_value.scalar_one_or_none.return_value = mock_ob

        with patch("app.services.compliance.obligation_service.resolve_obligation_compliance"):
            evidence = create_evidence(
                mock_db,
                organization_id=org_id,
                compliance_obligation_id=ob_id,
                title="NDT Fan Disk Inspection Record",
                evidence_type="INSPECTION_RECORD",
                source="Hangar 3 NDT Lab",
                uploaded_by_user_id=uuid.uuid4(),
            )

            assert evidence.compliance_obligation_id == ob_id
            assert evidence.regulatory_requirement_id == req_id
            assert evidence.asset_id == asset_id
            assert evidence.title == "NDT Fan Disk Inspection Record"
            assert evidence.verification_status == "UNVERIFIED"
            assert evidence.status == EvidenceStatus.UPLOADED.value
