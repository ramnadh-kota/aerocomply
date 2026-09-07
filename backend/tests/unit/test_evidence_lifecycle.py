from app.models.evidence import EvidenceStatus
from app.services.evidence_service import can_transition, satisfies_completion_gate

S = EvidenceStatus


def test_forward_sequence_is_allowed():
    assert can_transition(S.REQUIRED, S.UPLOADED)
    assert can_transition(S.UPLOADED, S.SUBMITTED)
    assert can_transition(S.SUBMITTED, S.AWAITING_REVIEW)
    assert can_transition(S.AWAITING_REVIEW, S.ACCEPTED)


def test_cannot_skip_states():
    assert not can_transition(S.REQUIRED, S.SUBMITTED)
    assert not can_transition(S.REQUIRED, S.ACCEPTED)
    assert not can_transition(S.UPLOADED, S.AWAITING_REVIEW)
    assert not can_transition(S.UPLOADED, S.ACCEPTED)
    assert not can_transition(S.SUBMITTED, S.ACCEPTED)


def test_cannot_move_backwards():
    assert not can_transition(S.UPLOADED, S.REQUIRED)
    assert not can_transition(S.SUBMITTED, S.UPLOADED)
    assert not can_transition(S.AWAITING_REVIEW, S.SUBMITTED)
    assert not can_transition(S.ACCEPTED, S.AWAITING_REVIEW)


def test_cannot_transition_to_self():
    for status in S:
        assert not can_transition(status, status)


def test_accepted_is_terminal():
    for status in S:
        assert not can_transition(S.ACCEPTED, status)


def test_rejected_reachable_from_submitted_and_awaiting_review():
    assert can_transition(S.SUBMITTED, S.REJECTED)
    assert can_transition(S.AWAITING_REVIEW, S.REJECTED)
    assert not can_transition(S.REQUIRED, S.REJECTED)
    assert not can_transition(S.UPLOADED, S.REJECTED)


def test_rejected_can_be_resubmitted_but_not_directly_accepted():
    assert can_transition(S.REJECTED, S.UPLOADED)
    assert can_transition(S.REJECTED, S.SUBMITTED)
    assert not can_transition(S.REJECTED, S.ACCEPTED)
    assert not can_transition(S.REJECTED, S.AWAITING_REVIEW)
    assert not can_transition(S.REJECTED, S.REQUIRED)


def test_only_accepted_satisfies_completion_gate():
    for status in S:
        expected = status == S.ACCEPTED
        assert satisfies_completion_gate(status) is expected


def test_submitted_and_awaiting_review_never_satisfy_gate():
    assert satisfies_completion_gate(S.SUBMITTED) is False
    assert satisfies_completion_gate(S.AWAITING_REVIEW) is False


def test_satisfies_completion_gate_accepts_plain_string():
    assert satisfies_completion_gate("ACCEPTED") is True
    assert satisfies_completion_gate("SUBMITTED") is False
