"""Unit tests for Compliance Obligation lifecycle, state machine, and domain invariants.

Domain Invariants:
- UNKNOWN != FALSE: INSUFFICIENT_DATA from applicability produces BLOCKED, not NOT_APPLICABLE.
- REVIEW_REQUIRED remains review-required until authorized decision.
- Only verified, accepted evidence satisfies compliance resolution.
- Rejected evidence produces NON_COMPLIANT and prevents COMPLIANT state.
- Idempotent obligation creation prevents duplicate active obligations for same requirement & asset.
"""

import datetime
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.applicability import EvaluationResult
from app.models.compliance import (
    ComplianceObligation,
    ComplianceState,
    RegulatoryRequirement,
)
from app.models.evidence import Evidence, EvidenceStatus
from app.schemas.compliance import (
    ComplianceObligationCreateRequest,
    ComplianceObligationUpdateRequest,
)
from app.services.compliance.obligation_service import (
    create_obligation,
    evaluate_and_sync_obligation,
    resolve_obligation_compliance,
    update_obligation,
)


class TestComplianceStateTransitions:
    """Verify deterministic compliance state transitions."""

    def test_due_date_past_initiates_as_overdue(self):
        past_date = datetime.date.today() - datetime.timedelta(days=10)
        req = ComplianceObligationCreateRequest(
            requirement_id=uuid.uuid4(),
            aircraft_id=uuid.uuid4(),
            due_date=past_date,
        )

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            MagicMock(),  # req exists
            None,  # no existing obligation
        ]

        with patch("app.services.compliance.obligation_service.aircraft_service"):
            obligation = create_obligation(
                mock_db,
                organization_id=uuid.uuid4(),
                actor_user_id=uuid.uuid4(),
                payload=req,
            )
            assert obligation.status == ComplianceState.OVERDUE.value

    def test_due_date_future_initiates_as_due(self):
        future_date = datetime.date.today() + datetime.timedelta(days=30)
        req = ComplianceObligationCreateRequest(
            requirement_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            due_date=future_date,
        )

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            MagicMock(),  # req exists
            None,  # no existing obligation
        ]

        with patch("app.services.compliance.obligation_service.asset_service"):
            obligation = create_obligation(
                mock_db,
                organization_id=uuid.uuid4(),
                actor_user_id=uuid.uuid4(),
                payload=req,
            )
            assert obligation.status == ComplianceState.DUE.value

    def test_unknown_never_treated_as_not_applicable(self):
        """Domain Invariant #23: Missing configuration produces BLOCKED, not NOT_APPLICABLE."""
        obligation = ComplianceObligation(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            requirement_id=uuid.uuid4(),
            asset_id=uuid.uuid4(),
            status=ComplianceState.NOT_EVALUATED.value,
        )

        mock_rule = MagicMock()
        mock_rule.id = uuid.uuid4()

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            obligation,  # get_obligation
            mock_rule,  # rule exists
        ]

        mock_eval = MagicMock()
        mock_eval.id = uuid.uuid4()
        mock_eval.system_result = EvaluationResult.INSUFFICIENT_DATA.value
        mock_eval.reasoning_trace = {"missing_data": ["Engine serial record"]}

        with patch("app.services.compliance.obligation_service.evaluation_service.evaluate_applicability", return_value=mock_eval):
            result = evaluate_and_sync_obligation(
                mock_db,
                organization_id=obligation.organization_id,
                actor_user_id=uuid.uuid4(),
                obligation_id=obligation.id,
            )
            # Must be BLOCKED, never NOT_APPLICABLE
            assert result.status == ComplianceState.BLOCKED.value
            assert result.status != ComplianceState.NOT_APPLICABLE.value
            assert "Blocked by missing configuration data" in result.notes

    def test_review_required_preserved(self):
        obligation = ComplianceObligation(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            requirement_id=uuid.uuid4(),
            aircraft_id=uuid.uuid4(),
            status=ComplianceState.NOT_EVALUATED.value,
        )

        mock_rule = MagicMock()
        mock_rule.id = uuid.uuid4()

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            obligation,
            mock_rule,
        ]

        mock_eval = MagicMock()
        mock_eval.id = uuid.uuid4()
        mock_eval.system_result = EvaluationResult.REVIEW_REQUIRED.value
        mock_eval.reasoning_trace = {}

        with patch("app.services.compliance.obligation_service.evaluation_service.evaluate_applicability", return_value=mock_eval):
            result = evaluate_and_sync_obligation(
                mock_db,
                organization_id=obligation.organization_id,
                actor_user_id=uuid.uuid4(),
                obligation_id=obligation.id,
            )
            assert result.status == ComplianceState.REVIEW_REQUIRED.value



class TestComplianceResolutionWithEvidence:
    """Verify evidence impact on obligation compliance resolution."""

    def test_verified_evidence_resolves_to_compliant(self):
        obligation = ComplianceObligation(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            requirement_id=uuid.uuid4(),
            status=ComplianceState.DUE.value,
            evidence_requirements=[{"type": "INSPECTION_RECORD"}],
        )

        evidence = Evidence(
            id=uuid.uuid4(),
            organization_id=obligation.organization_id,
            compliance_obligation_id=obligation.id,
            verification_status="VERIFIED",
            status=EvidenceStatus.ACCEPTED.value,
        )

        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = [evidence]

        resolved = resolve_obligation_compliance(mock_db, obligation, actor_user_id=uuid.uuid4())
        assert resolved.status == ComplianceState.COMPLIANT.value
        assert resolved.verified_at is not None

    def test_rejected_evidence_forces_non_compliant(self):
        """Even if some evidence is verified, any rejected evidence prevents COMPLIANT state."""
        obligation = ComplianceObligation(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            requirement_id=uuid.uuid4(),
            status=ComplianceState.DUE.value,
        )

        ev_good = Evidence(
            id=uuid.uuid4(),
            organization_id=obligation.organization_id,
            compliance_obligation_id=obligation.id,
            verification_status="VERIFIED",
            status=EvidenceStatus.ACCEPTED.value,
        )
        ev_bad = Evidence(
            id=uuid.uuid4(),
            organization_id=obligation.organization_id,
            compliance_obligation_id=obligation.id,
            verification_status="REJECTED",
            status=EvidenceStatus.REJECTED.value,
            rejection_reason="NDT scan calibration invalid",
        )

        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = [ev_good, ev_bad]

        resolved = resolve_obligation_compliance(mock_db, obligation, actor_user_id=uuid.uuid4())
        assert resolved.status == ComplianceState.NON_COMPLIANT.value
        assert resolved.status != ComplianceState.COMPLIANT.value

    def test_unverified_evidence_keeps_in_progress(self):
        obligation = ComplianceObligation(
            id=uuid.uuid4(),
            organization_id=uuid.uuid4(),
            requirement_id=uuid.uuid4(),
            status=ComplianceState.DUE.value,
        )

        ev_pending = Evidence(
            id=uuid.uuid4(),
            organization_id=obligation.organization_id,
            compliance_obligation_id=obligation.id,
            verification_status="UNVERIFIED",
            status=EvidenceStatus.UPLOADED.value,
        )

        mock_db = MagicMock()
        mock_db.execute.return_value.scalars.return_value.all.return_value = [ev_pending]

        resolved = resolve_obligation_compliance(mock_db, obligation, actor_user_id=uuid.uuid4())
        assert resolved.status == ComplianceState.IN_PROGRESS.value
        assert resolved.status != ComplianceState.COMPLIANT.value


class TestIdempotencyAndDuplicatePrevention:
    """Verify idempotent creation returns existing obligation without duplication."""

    def test_existing_obligation_is_updated_not_duplicated(self):
        req_id = uuid.uuid4()
        ac_id = uuid.uuid4()
        org_id = uuid.uuid4()

        existing = ComplianceObligation(
            id=uuid.uuid4(),
            organization_id=org_id,
            requirement_id=req_id,
            aircraft_id=ac_id,
            status=ComplianceState.DUE.value,
            priority="LOW",
        )

        payload = ComplianceObligationCreateRequest(
            requirement_id=req_id,
            aircraft_id=ac_id,
            priority="CRITICAL",
        )

        mock_db = MagicMock()
        mock_db.execute.return_value.scalar_one_or_none.side_effect = [
            MagicMock(),  # req exists
            existing,  # existing found!
        ]

        with patch("app.services.compliance.obligation_service.aircraft_service"):
            result = create_obligation(
                mock_db,
                organization_id=org_id,
                actor_user_id=uuid.uuid4(),
                payload=payload,
            )
            assert result.id == existing.id
            assert result.priority == "CRITICAL"
            # db.add called on existing, not creating a second row
            mock_db.add.assert_called_with(existing)
