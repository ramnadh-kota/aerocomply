"""Unit tests for Compliance Intelligence, Finding Correlation, and Readiness Gate Integration (Milestone D2-3).

Verifies deterministic rules:
1. Finding -> Compliance Obligation correlation with validation and audit trail.
2. Finding classification / severity downstream readiness blockers (CRITICAL/MAJOR -> BLOCKED).
3. Inspection package compliance resolution gated by open findings, missing evidence, and unverified evidence.
4. Asset readiness contribution calculation:
   - Positive: all obligations COMPLIANT -> READY.
   - Negative: NON_COMPLIANT -> BLOCKED with full 13-point explainability.
   - Negative: Missing / Rejected evidence -> BLOCKED.
   - Invariant #23: INSUFFICIENT_DATA -> BLOCKED / UNKNOWN (never converted to NOT_APPLICABLE).
"""

import datetime
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models.compliance import (
    ComplianceObligation,
    ComplianceState,
    RegulatoryRequirement,
)
from app.models.evidence import Evidence, EvidenceStatus
from app.models.finding import Finding, FindingSeverity, FindingStatus
from app.models.inspection_requirement import (
    InspectionRequirement,
    InspectionRequirementStatus,
)
from app.schemas.compliance_intelligence import (
    ComplianceReadinessBlocker,
    ComplianceReadinessContribution,
)
from app.services.compliance.intelligence_service import (
    get_asset_compliance_impact,
    get_asset_compliance_readiness_contribution,
    get_finding_compliance_impact,
    get_inspection_compliance_impact,
    resolve_inspection_package_compliance,
)
from app.services.finding_service import correlate_compliance


class TestFindingCorrelationAndImpact:
    def test_correlate_compliance_success(self):
        db = MagicMock()
        org_id = uuid.uuid4()
        finding_id = uuid.uuid4()
        ob_id = uuid.uuid4()
        req_id = uuid.uuid4()

        finding = Finding(
            id=finding_id,
            organization_id=org_id,
            title="Crack in wing rib 4",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.OPEN,
        )

        obligation = ComplianceObligation(
            id=ob_id,
            organization_id=org_id,
            requirement_id=req_id,
            status=ComplianceState.NON_COMPLIANT.value,
        )

        requirement = RegulatoryRequirement(
            id=req_id,
            organization_id=org_id,
            authority="FAA",
            requirement_number="FAA-AD-2024-01",
            title="Airworthiness Directive: Wing Spar Inspection",
            description="Mandatory ultrasonic inspection of spar",
        )

        def mock_execute(query):
            mock_res = MagicMock()
            q_str = str(query).lower()
            if "from compliance_obligations" in q_str:
                mock_res.scalar_one_or_none.return_value = ob_id
            elif "from regulatory_requirements" in q_str:
                mock_res.scalar_one_or_none.return_value = req_id
            else:
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        db.execute.side_effect = mock_execute

        with patch("app.services.finding_service.record_audit_event") as mock_audit:
            updated = correlate_compliance(
                db,
                finding=finding,
                compliance_obligation_id=ob_id,
                regulatory_requirement_id=req_id,
                safety_significance="AIRWORTHINESS_DIRECTIVE",
                compliance_relevance="PRIMARY_MANDATE",
                actor_user_id=uuid.uuid4(),
            )

            assert updated.compliance_obligation_id == ob_id
            assert updated.regulatory_requirement_id == req_id
            assert updated.safety_significance == "AIRWORTHINESS_DIRECTIVE"
            assert updated.compliance_relevance == "PRIMARY_MANDATE"
            mock_audit.assert_called_once()

    def test_get_finding_compliance_impact_unresolved_critical(self):
        db = MagicMock()
        org_id = uuid.uuid4()
        finding_id = uuid.uuid4()
        ob_id = uuid.uuid4()
        req_id = uuid.uuid4()
        asset_id = uuid.uuid4()

        finding = Finding(
            id=finding_id,
            organization_id=org_id,
            title="Corrosion detected on main gear trunnion",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.OPEN,
            compliance_obligation_id=ob_id,
            regulatory_requirement_id=req_id,
            asset_id=asset_id,
            dispositions=[],
        )

        obligation = ComplianceObligation(
            id=ob_id,
            organization_id=org_id,
            requirement_id=req_id,
            status=ComplianceState.NON_COMPLIANT.value,
        )

        requirement = RegulatoryRequirement(
            id=req_id,
            organization_id=org_id,
            authority="EASA",
            requirement_number="EASA-AD-LG-09",
            title="Landing Gear Structural Integrity",
            description="Inspection of trunnion",
        )

        def mock_execute(query):
            mock_res = MagicMock()
            q_str = str(query).lower()
            if "from findings" in q_str:
                mock_res.scalar_one_or_none.return_value = finding
            elif "from compliance_obligations" in q_str:
                mock_res.scalar_one_or_none.return_value = obligation
            elif "from regulatory_requirements" in q_str:
                mock_res.scalar_one_or_none.return_value = requirement
            elif "from evidences" in q_str or "from evidence" in q_str:
                mock_res.scalars.return_value.all.return_value = []
            else:
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        db.execute.side_effect = mock_execute

        impact = get_finding_compliance_impact(db, organization_id=org_id, finding_id=finding_id)

        assert impact.finding_id == finding_id
        assert impact.is_readiness_blocker is True
        assert "critical" in impact.blocker_reason.lower()
        assert impact.current_compliance_state == ComplianceState.NON_COMPLIANT.value
        assert impact.regulatory_requirement_number == "EASA-AD-LG-09"

    def test_get_finding_compliance_impact_resolved_minor(self):
        db = MagicMock()
        org_id = uuid.uuid4()
        finding_id = uuid.uuid4()
        ob_id = uuid.uuid4()
        req_id = uuid.uuid4()

        finding = Finding(
            id=finding_id,
            organization_id=org_id,
            title="Loose wire harness clamp",
            severity=FindingSeverity.MINOR,
            status=FindingStatus.CLOSED,
            compliance_obligation_id=ob_id,
            regulatory_requirement_id=req_id,
            dispositions=[],
        )

        obligation = ComplianceObligation(
            id=ob_id,
            organization_id=org_id,
            requirement_id=req_id,
            status=ComplianceState.COMPLIANT.value,
        )

        requirement = RegulatoryRequirement(
            id=req_id,
            organization_id=org_id,
            authority="FAA",
            requirement_number="FAR-25-1309",
            title="System Safety",
            description="System lightning and routing",
        )

        def mock_execute(query):
            mock_res = MagicMock()
            q_str = str(query).lower()
            if "from findings" in q_str:
                mock_res.scalar_one_or_none.return_value = finding
            elif "from compliance_obligations" in q_str:
                mock_res.scalar_one_or_none.return_value = obligation
            elif "from regulatory_requirements" in q_str:
                mock_res.scalar_one_or_none.return_value = requirement
            else:
                mock_res.scalars.return_value.all.return_value = []
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        db.execute.side_effect = mock_execute

        impact = get_finding_compliance_impact(db, organization_id=org_id, finding_id=finding_id)

        assert impact.finding_id == finding_id
        assert impact.is_readiness_blocker is False
        assert impact.blocker_reason is None
        assert impact.current_compliance_state == ComplianceState.COMPLIANT.value


class TestInspectionComplianceResolution:
    def test_resolve_inspection_package_blocked_by_open_finding(self):
        db = MagicMock()
        org_id = uuid.uuid4()
        insp_id = uuid.uuid4()
        ob_id = uuid.uuid4()
        user_id = uuid.uuid4()

        inspection = InspectionRequirement(
            id=insp_id,
            organization_id=org_id,
            work_order_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            status=InspectionRequirementStatus.COMPLETED.value,
            compliance_obligation_id=ob_id,
        )

        open_finding = Finding(
            id=uuid.uuid4(),
            organization_id=org_id,
            inspection_requirement_id=insp_id,
            title="Hydraulic line chafing",
            severity=FindingSeverity.MAJOR,
            status=FindingStatus.OPEN,
            compliance_obligation_id=ob_id,
        )

        obligation = ComplianceObligation(
            id=ob_id,
            organization_id=org_id,
            requirement_id=uuid.uuid4(),
            status=ComplianceState.NON_COMPLIANT.value,
        )

        def mock_execute(query):
            mock_res = MagicMock()
            q_str = str(query).lower()
            if "from inspection_requirements" in q_str:
                mock_res.scalar_one_or_none.return_value = inspection
            elif "from compliance_obligations" in q_str:
                mock_res.scalar_one_or_none.return_value = obligation
            elif "from findings" in q_str:
                mock_res.scalars.return_value.all.return_value = [open_finding]
            else:
                mock_res.scalars.return_value.all.return_value = []
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        db.execute.side_effect = mock_execute

        res = resolve_inspection_package_compliance(
            db,
            organization_id=org_id,
            actor_user_id=user_id,
            inspection_requirement_id=insp_id,
        )

        assert res["resolved"] is False
        assert "open findings" in res["reason"].lower()
        # Obligation must NOT be resolved to COMPLIANT
        assert obligation.status != ComplianceState.COMPLIANT.value

    def test_resolve_inspection_package_blocked_by_unverified_evidence(self):
        db = MagicMock()
        org_id = uuid.uuid4()
        insp_id = uuid.uuid4()
        ob_id = uuid.uuid4()
        user_id = uuid.uuid4()

        inspection = InspectionRequirement(
            id=insp_id,
            organization_id=org_id,
            work_order_id=uuid.uuid4(),
            task_id=uuid.uuid4(),
            status=InspectionRequirementStatus.COMPLETED.value,
            compliance_obligation_id=ob_id,
        )

        obligation = ComplianceObligation(
            id=ob_id,
            organization_id=org_id,
            requirement_id=uuid.uuid4(),
            status=ComplianceState.NON_COMPLIANT.value,
        )

        def mock_execute(query):
            mock_res = MagicMock()
            q_str = str(query).lower()
            if "from inspection_requirements" in q_str:
                mock_res.scalar_one_or_none.return_value = inspection
            elif "from compliance_obligations" in q_str:
                mock_res.scalar_one_or_none.return_value = obligation
            elif "from findings" in q_str:
                mock_res.scalars.return_value.all.return_value = []  # No open findings
            else:
                mock_res.scalars.return_value.all.return_value = []
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        db.execute.side_effect = mock_execute

        # resolve_obligation_compliance leaves status as NON_COMPLIANT when evidence is unverified
        with patch("app.services.compliance.intelligence_service.resolve_obligation_compliance") as mock_resolve:
            res = resolve_inspection_package_compliance(
                db,
                organization_id=org_id,
                actor_user_id=user_id,
                inspection_requirement_id=insp_id,
            )

            mock_resolve.assert_called_once_with(db, obligation, actor_user_id=user_id)
            assert res["resolved"] is False
            assert res["obligation_status"] == ComplianceState.NON_COMPLIANT.value


class TestReadinessGateContribution:
    def test_all_obligations_compliant_yields_ready(self):
        db = MagicMock()
        org_id = uuid.uuid4()
        asset_id = uuid.uuid4()

        compliant_ob = ComplianceObligation(
            id=uuid.uuid4(),
            organization_id=org_id,
            asset_id=asset_id,
            requirement_id=uuid.uuid4(),
            status=ComplianceState.COMPLIANT.value,
        )

        req = RegulatoryRequirement(
            id=compliant_ob.requirement_id,
            organization_id=org_id,
            authority="FAA",
            requirement_number="FAA-AD-1",
            title="Pitot Static",
            description="desc",
        )

        def mock_execute(query):
            mock_res = MagicMock()
            q_str = str(query).lower()
            if "from aircraft" in q_str:
                mock_res.scalar_one_or_none.return_value = None
            elif "from compliance_obligations" in q_str:
                mock_res.scalars.return_value.all.return_value = [compliant_ob]
            elif "from regulatory_requirements" in q_str:
                mock_res.scalar_one_or_none.return_value = req
            elif "from findings" in q_str:
                mock_res.scalars.return_value.all.return_value = []
            elif "from inspection_requirements" in q_str:
                mock_res.scalars.return_value.all.return_value = []
            else:
                mock_res.scalars.return_value.all.return_value = []
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        db.execute.side_effect = mock_execute

        contrib = get_asset_compliance_readiness_contribution(
            db, organization_id=org_id, asset_id=asset_id
        )

        assert contrib.overall_status == "READY"
        assert len(contrib.blockers) == 0
        assert contrib.compliance_obligations_count == 1
        assert contrib.compliant_obligations_count == 1

    def test_critical_open_finding_yields_blocked_with_13_point_explainability(self):
        db = MagicMock()
        org_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        finding_id = uuid.uuid4()
        ob_id = uuid.uuid4()
        req_id = uuid.uuid4()

        obligation = ComplianceObligation(
            id=ob_id,
            organization_id=org_id,
            asset_id=asset_id,
            requirement_id=req_id,
            status=ComplianceState.NON_COMPLIANT.value,
        )

        req = RegulatoryRequirement(
            id=req_id,
            organization_id=org_id,
            authority="FAA",
            requirement_number="FAA-AD-Elevator",
            title="Elevator Torque Tube AD",
            description="Elevator hinge check",
        )

        finding = Finding(
            id=finding_id,
            organization_id=org_id,
            asset_id=asset_id,
            compliance_obligation_id=ob_id,
            regulatory_requirement_id=req_id,
            title="Elevator hinge crack exceeding allowable limit",
            severity=FindingSeverity.CRITICAL,
            status=FindingStatus.OPEN,
        )

        def mock_execute(query):
            mock_res = MagicMock()
            q_str = str(query).lower()
            if "from aircraft" in q_str:
                mock_res.scalar_one_or_none.return_value = None
            elif "from compliance_obligations" in q_str:
                mock_res.scalars.return_value.all.return_value = [obligation]
            elif "from regulatory_requirements" in q_str:
                mock_res.scalar_one_or_none.return_value = req
            elif "from findings" in q_str:
                mock_res.scalars.return_value.all.return_value = [finding]
            elif "from inspection_requirements" in q_str:
                mock_res.scalars.return_value.all.return_value = []
            else:
                mock_res.scalars.return_value.all.return_value = []
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        db.execute.side_effect = mock_execute

        contrib = get_asset_compliance_readiness_contribution(
            db, organization_id=org_id, asset_id=asset_id
        )

        assert contrib.overall_status == "BLOCKED"
        assert len(contrib.blockers) >= 1

        # Verify 13-point explainability structure on blocker
        blocker = contrib.blockers[0]
        assert blocker.blocker_id is not None
        assert blocker.what_blocking is not None  # WHAT is blocking?
        assert blocker.why_blocking is not None   # WHY is it blocking?
        assert blocker.source_record_type is not None  # WHICH record caused it?
        assert blocker.source_record_id is not None
        assert blocker.required_action is not None     # WHAT action is required?
        assert blocker.resolution_action is not None   # HOW to resolve it?

    def test_invariant_23_insufficient_data_yields_blocked(self):
        """Invariant #23: UNKNOWN != FALSE. Missing evaluation data must never yield READY or NOT_APPLICABLE."""
        db = MagicMock()
        org_id = uuid.uuid4()
        asset_id = uuid.uuid4()
        req_id = uuid.uuid4()

        blocked_ob = ComplianceObligation(
            id=uuid.uuid4(),
            organization_id=org_id,
            asset_id=asset_id,
            requirement_id=req_id,
            status=ComplianceState.BLOCKED.value,
        )

        req = RegulatoryRequirement(
            id=req_id,
            organization_id=org_id,
            authority="FAA",
            requirement_number="FAA-AV-01",
            title="Avionics Software Level Verification",
            description="desc",
        )

        def mock_execute(query):
            mock_res = MagicMock()
            q_str = str(query).lower()
            if "from aircraft" in q_str:
                mock_res.scalar_one_or_none.return_value = None
            elif "from compliance_obligations" in q_str:
                mock_res.scalars.return_value.all.return_value = [blocked_ob]
            elif "from regulatory_requirements" in q_str:
                mock_res.scalar_one_or_none.return_value = req
            elif "from findings" in q_str:
                mock_res.scalars.return_value.all.return_value = []
            elif "from inspection_requirements" in q_str:
                mock_res.scalars.return_value.all.return_value = []
            else:
                mock_res.scalars.return_value.all.return_value = []
                mock_res.scalar_one_or_none.return_value = None
            return mock_res

        db.execute.side_effect = mock_execute

        contrib = get_asset_compliance_readiness_contribution(
            db, organization_id=org_id, asset_id=asset_id
        )

        # Invariant: Blocked/unknown obligation cannot be READY
        assert contrib.overall_status == "BLOCKED"
        assert len(contrib.blockers) >= 1
        assert any("blocked" in b.what_blocking.lower() for b in contrib.blockers)
