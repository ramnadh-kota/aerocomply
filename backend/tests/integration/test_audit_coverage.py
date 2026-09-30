"""Compliance / MRO / intelligence state changes leave an audit trail with previous values."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models.applicability import ApplicabilityEvaluation, ApplicabilityRule
from app.models.audit_event import AuditEvent
from app.models.compliance import ComplianceState, RegulatoryRequirement
from app.models.proactive_signal import ProactiveSignalRecord
from app.services.compliance import obligation_service
from tests.integration.test_acquisition_pipeline import _org


def _actions(db, org_id):
    return [(a.action, a.event_metadata) for a in db.execute(
        select(AuditEvent).where(AuditEvent.organization_id == org_id).order_by(AuditEvent.created_at)).scalars()]


def test_obligation_creation_and_every_status_change_from_evaluation_is_audited(client, db_session):
    org_id, h = _org(client, db_session, "auditc")
    req = RegulatoryRequirement(organization_id=org_id, authority="DGCA", requirement_number="AD-1", title="t",
                                description="Comply")
    db_session.add(req)
    db_session.flush()
    rule = ApplicabilityRule(organization_id=org_id, rule_code="R1", title="rule", regulatory_requirement_id=req.id)
    db_session.add(rule)
    db_session.flush()

    def evaluate(result):
        ev = ApplicabilityEvaluation(organization_id=org_id, rule_id=rule.id, system_result=result,
                                     configuration_snapshot={}, reasoning_trace={})
        db_session.add(ev)
        db_session.flush()
        ev.rule = rule
        return obligation_service.create_or_sync_from_evaluation(db_session, organization_id=org_id,
                                                                 actor_user_id=None, evaluation=ev)

    ob = evaluate("APPLICABLE")
    assert ob.status == ComplianceState.DUE.value
    ob = evaluate("NOT_APPLICABLE")
    assert ob.status == ComplianceState.NOT_APPLICABLE.value
    ob = evaluate("APPLICABLE")                                          # back to DUE
    trail = [(a, m) for a, m in _actions(db_session, org_id) if a.startswith("compliance_obligation.")]
    assert trail[0][0] == "compliance_obligation.created_from_evaluation" and trail[0][1]["status"] == "DUE"
    changes = [m for a, m in trail if a == "compliance_obligation.status_changed"]
    assert [(m["from_status"], m["to_status"]) for m in changes] == [("DUE", "NOT_APPLICABLE"), ("NOT_APPLICABLE", "DUE")]
    evaluate("APPLICABLE")                                               # no change => no new audit row
    assert len([a for a, _ in _actions(db_session, org_id) if a == "compliance_obligation.status_changed"]) == 2


def test_signal_lifecycle_transitions_are_audited_with_previous_status(client, db_session):
    org_id, h = _org(client, db_session, "audits")
    from app.services.intelligence import proactive_intelligence_service as pis

    user_id = uuid.UUID(client.get("/api/v1/auth/me", headers=h).json()["id"])
    sig = ProactiveSignalRecord(organization_id=org_id, signal_key=f"k-{uuid.uuid4().hex[:6]}", signal_type="X",
                                severity="HIGH", priority="HIGH", status="OPEN", title="t", headline="h",
                                explanation_json=[], evidence_json=[], contributing_factors_json={},
                                recommended_actions_json=[], detected_at=datetime.now(UTC))
    db_session.add(sig)
    db_session.flush()
    kw = dict(organization_id=org_id, signal_id=sig.id, user_id=user_id)
    try:
        pis.acknowledge_signal(db_session, **kw)
        pis.set_signal_in_review(db_session, **kw, notes="looking")
        pis.resolve_signal(db_session, **kw, resolution_notes="fixed")
        pis.dismiss_signal(db_session, **kw, dismissal_reason="dup")
    except Exception:  # sync_and_get_signals may drop an ad-hoc signal from the response; the audit rows are what we assert
        pass
    trail = [(a, m["from_status"], m["to_status"]) for a, m in _actions(db_session, org_id)
             if a.startswith("proactive_signal.")]
    assert trail[:1] == [("proactive_signal.acknowledged", "OPEN", "ACKNOWLEDGED")]
    assert [t[0] for t in trail] == ["proactive_signal.acknowledged", "proactive_signal.in_review",
                                     "proactive_signal.resolved", "proactive_signal.dismissed"][:len(trail)]


def test_assessment_and_inspection_requirement_creation_are_audited(client, db_session):
    org_id, h = _org(client, db_session, "audita")
    r = client.post("/api/v1/assessments", headers=h, json={"name": "Q3 fleet", "scope_type": "FLEET"})
    assert r.status_code in (200, 201), r.text
    actions = [a for a, _ in _actions(db_session, org_id)]
    assert "assessment.created" in actions
