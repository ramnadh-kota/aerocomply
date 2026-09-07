"""Pure logic tests for the deterministic AI safety layer — no LLM/DB needed."""

from app.services.ai.safety import is_safety_restricted, safety_refusal_response


def test_airworthiness_question_is_restricted():
    assert is_safety_restricted("Is this aircraft airworthy?")


def test_safe_to_dispatch_is_restricted():
    assert is_safety_restricted("Is N412MX safe to dispatch today?")


def test_release_to_service_is_restricted():
    assert is_safety_restricted("Can we release the aircraft to service now?")


def test_release_question_variants_are_restricted():
    assert is_safety_restricted("Should we release this aircraft?")
    assert is_safety_restricted("Can this aircraft be released?")


def test_bypass_inspection_is_restricted():
    assert is_safety_restricted("Can we skip the RII on this task?")
    assert is_safety_restricted("Can we bypass the safety gate for this work order?")


def test_release_without_evidence_is_restricted():
    assert is_safety_restricted("Can we release this work order without evidence?")


def test_release_despite_blocker_is_restricted():
    assert is_safety_restricted("Can we release despite the open discrepancy?")


def test_ordinary_status_question_is_not_restricted():
    assert not is_safety_restricted("What is the status of work order WO-1042?")
    assert not is_safety_restricted("List open evidence for task T-99.")
    assert not is_safety_restricted("Which tasks are on this work order?")


def test_refusal_response_shape():
    resp = safety_refusal_response()
    assert resp["actionCategory"] == "SAFETY_RESTRICTED"
    assert resp["priority"] == "CRITICAL"
    assert resp["confidenceState"] == "CONFIRMED"
    assert "SAFETY_REFUSAL" in resp["headline"]
    assert len(resp["narrative"]) >= 1
