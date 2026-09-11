"""Pure rule-based tests for reference_resolution_service — no DB needed:
LisaConversationContext instances here are plain in-memory objects, never
persisted, since this module only reads attributes off them.
"""

import uuid
from datetime import UTC, datetime

from app.models.lisa_conversation_context import LisaConversationContext
from app.services.lisa import reference_resolution_service as rr


def _context(**overrides) -> LisaConversationContext:
    defaults = {
        "organization_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "recent_entities": "[]",
        "recent_questions": "[]",
        "context_version": 1,
        "last_activity_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return LisaConversationContext(**defaults)


def test_is_reset_request_detects_phrases():
    assert rr.is_reset_request("Let's start over") is True
    assert rr.is_reset_request("Switch aircraft please") is True
    assert rr.is_reset_request("Why is VT-XYZ AOG?") is False


def test_extract_explicit_identifiers_work_order_and_po_and_aircraft():
    found = rr.extract_explicit_identifiers("Is WO-1042 blocked and did we order PO-9981?")
    assert found["work_order"] == "WO-1042"
    assert found["purchase_order"] == "PO-9981"
    assert "aircraft" not in found  # WO-/PO- numbers must never be misread as a registration


def test_extract_explicit_identifiers_aircraft_registration():
    found = rr.extract_explicit_identifiers("Why is VT-XYZ still AOG?")
    assert found["aircraft"] == "VT-XYZ"


def test_resolve_reference_this_aircraft_uses_context():
    aircraft_id = str(uuid.uuid4())
    context = _context(current_aircraft_id=uuid.UUID(aircraft_id))
    result = rr.resolve_reference("What is blocking this aircraft?", context)
    assert result == ("aircraft", aircraft_id)


def test_resolve_reference_bare_pronoun_uses_most_recent_entity():
    aircraft_id = str(uuid.uuid4())
    entities = (
        f'[{{"entity_type": "aircraft", "entity_id": "{aircraft_id}", "display": "VT-XYZ"}}]'
    )
    context = _context(recent_entities=entities)
    result = rr.resolve_reference("Why is it AOG?", context)
    assert result == ("aircraft", aircraft_id)


def test_resolve_reference_previous_one_uses_second_to_last():
    first_id = str(uuid.uuid4())
    second_id = str(uuid.uuid4())
    context = _context(
        recent_entities=(
            f'[{{"entity_type": "aircraft", "entity_id": "{first_id}", "display": "A"}}, '
            f'{{"entity_type": "work_order", "entity_id": "{second_id}", "display": "B"}}]'
        )
    )
    result = rr.resolve_reference("What about the previous one?", context)
    assert result == ("aircraft", first_id)


def test_resolve_reference_returns_none_when_context_field_empty():
    context = _context()  # nothing resolved yet
    result = rr.resolve_reference("What is blocking that work order?", context)
    assert result is None


def test_resolve_reference_returns_none_for_unrecognized_phrase():
    context = _context(current_aircraft_id=uuid.uuid4())
    result = rr.resolve_reference("What is the weather today?", context)
    assert result is None
