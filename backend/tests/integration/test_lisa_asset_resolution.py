"""LISA resolves drones / other airframes by name -- exactly, tenant-scoped, never fuzzily.

Before M20 LISA could only resolve rows of the Aircraft table by an aircraft-shaped registration
(VT-ABC, N123AB). A drone customer asking "what is the telemetry status of DRN-001?" got
"I need an aircraft or drone".
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.core.security import hash_password
from app.models.asset import Asset
from app.models.organization import Organization
from app.models.user import User
from app.services.lisa.entity_resolution_service import AmbiguousMatch, NotFound, ResolvedEntity, resolve_aircraft
from app.services.lisa.message_resolution_service import resolve_message


def _tenant(db):
    org = Organization(name=f"lisa-{uuid.uuid4().hex[:6]}")
    db.add(org)
    db.flush()
    user = User(organization_id=org.id, email=f"l-{uuid.uuid4().hex[:6]}@example.com",
                hashed_password=hash_password("x" * 12), full_name="L", is_active=True, email_verified=True)
    db.add(user)
    db.flush()
    return org, user


def _asset(db, org, registration=None, serial=None, asset_type="DRONE", deleted=False):
    a = Asset(organization_id=org.id, asset_type=asset_type, registration=registration, serial_number=serial)
    if deleted:
        a.deleted_at = datetime.now(UTC)
    db.add(a)
    db.flush()
    return a


def _resolve(db, org, user, q):
    return resolve_message(db, organization_id=org.id, user_id=user.id, question=q)


def test_drone_is_resolved_by_registration_case_insensitively_and_by_serial(db_session):
    org, user = _tenant(db_session)
    d = _asset(db_session, org, registration="DRN-001", serial="SN-778899")
    for q in ("What is the status of DRN-001?", "status of drn-001 please", "telemetry for SN-778899"):
        res = _resolve(db_session, org, user, q)
        assert [e.entity_id for e in res.resolved] == [str(d.id)], q


def test_drone_is_resolved_by_uuid_and_pronoun_follows_context(db_session):
    org, user = _tenant(db_session)
    d = _asset(db_session, org, registration="DRN-002")
    assert isinstance(resolve_aircraft(db_session, organization_id=org.id, identifier=str(d.id)), ResolvedEntity)
    _resolve(db_session, org, user, "status of DRN-002")
    follow = _resolve(db_session, org, user, "what about this drone?")
    assert [e.entity_id for e in follow.resolved] == [str(d.id)]


def test_only_whole_tokens_match_never_substrings(db_session):
    org, user = _tenant(db_session)
    _asset(db_session, org, registration="DRN-001")
    for q in ("status of DRN-0011", "status of XDRN-001", "status of DRN-001A"):
        assert _resolve(db_session, org, user, q).resolved == [], q


def test_two_different_assets_in_one_message_are_not_guessed_between(db_session):
    org, user = _tenant(db_session)
    _asset(db_session, org, registration="DRN-010")
    _asset(db_session, org, registration="DRN-011")
    assert _resolve(db_session, org, user, "compare DRN-010 and DRN-011").resolved == []


def test_identifier_shared_by_two_assets_is_ambiguous_not_arbitrary(db_session):
    org, user = _tenant(db_session)
    _asset(db_session, org, registration="AB-123")
    _asset(db_session, org, serial="AB-123")               # another asset's SERIAL equals this registration
    res = _resolve(db_session, org, user, "status of AB-123")
    assert isinstance(res.ambiguous, AmbiguousMatch) and len(res.ambiguous.candidates) == 2


def test_other_tenants_asset_and_deleted_assets_are_never_resolved(db_session):
    org_a, user_a = _tenant(db_session)
    org_b, user_b = _tenant(db_session)
    a = _asset(db_session, org_a, registration="ONLY-A-1")
    gone = _asset(db_session, org_b, registration="GONE-B-1", deleted=True)
    assert _resolve(db_session, org_b, user_b, "status of ONLY-A-1").resolved == []
    assert isinstance(resolve_aircraft(db_session, organization_id=org_b.id, identifier=str(a.id)), NotFound)
    assert isinstance(resolve_aircraft(db_session, organization_id=org_b.id, identifier="ONLY-A-1"), NotFound)
    assert _resolve(db_session, org_b, user_b, "status of GONE-B-1").resolved == []
    assert isinstance(resolve_aircraft(db_session, organization_id=org_b.id, identifier=str(gone.id)), NotFound)


def test_wildcard_characters_in_identifiers_are_literal(db_session):
    org, user = _tenant(db_session)
    _asset(db_session, org, registration="X_Y%Z")
    _asset(db_session, org, registration="XAYBZ")
    res = _resolve(db_session, org, user, "status of XAYBZ")
    assert len(res.resolved) == 1 and res.resolved[0].display == "XAYBZ"


def test_short_identifiers_are_ignored(db_session):
    org, user = _tenant(db_session)
    _asset(db_session, org, registration="A1")           # below the minimum length: too ambiguous to match in prose
    assert _resolve(db_session, org, user, "is A1 ok").resolved == []
