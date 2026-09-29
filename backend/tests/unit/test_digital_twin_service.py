"""H6 Unit Tests: pure/structural behavior of the digital twin schemas and
consistency-warning shape (the service functions themselves are DB-backed
and covered by tests/integration/test_digital_twin.py; this file covers
what can be verified without a database).
"""

import uuid
from datetime import UTC, datetime

from app.schemas.digital_twin import (
    DigitalTwinConsistencyWarning,
    DigitalTwinGenealogyEntry,
    DigitalTwinTimelineEvent,
)


def test_genealogy_entry_is_current_when_not_removed():
    entry = DigitalTwinGenealogyEntry(
        installation_id=uuid.uuid4(), asset_id=uuid.uuid4(), asset_registration="KA-1",
        installed_at=datetime.now(UTC), removed_at=None, is_current=True,
    )
    assert entry.is_current is True
    assert entry.removed_at is None


def test_timeline_events_sort_descending_by_occurred_at():
    now = datetime.now(UTC)
    events = [
        DigitalTwinTimelineEvent(occurred_at=now, event_type="A", summary="latest", source_type="X", source_id=uuid.uuid4()),
        DigitalTwinTimelineEvent(occurred_at=now.replace(year=now.year - 1), event_type="B", summary="oldest", source_type="X", source_id=uuid.uuid4()),
    ]
    sorted_events = sorted(events, key=lambda e: e.occurred_at, reverse=True)
    assert sorted_events[0].summary == "latest"
    assert sorted_events[1].summary == "oldest"


def test_consistency_warning_requires_severity_and_source():
    warning = DigitalTwinConsistencyWarning(
        check="DUPLICATE_OPEN_INSTALLATION", severity="ERROR", message="test",
        entity_type="Component", entity_id=uuid.uuid4(),
    )
    assert warning.severity == "ERROR"
    assert warning.entity_type == "Component"


def test_consistency_warning_severity_is_constrained():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        DigitalTwinConsistencyWarning(
            check="X", severity="NOT_A_REAL_SEVERITY", message="test", entity_type="Component", entity_id=uuid.uuid4()
        )
