"""Deterministic entity resolution for Lisa: turn a human-supplied identifier
(a UUID, an aircraft registration, a work order number, a part number, a
vendor name, a PO number, or a user's name/email) into a real backend
record — or an explicit ambiguous/not-found result. Never guesses.

Reuses each domain service's existing tenant-scoped list_* functions —
this module adds no new query logic to those services and performs no
writes. Matching is case-insensitive exact-match only (Rule: "Exact
authoritative ID > exact unique business identifier > exact unique name" —
no fuzzy/substring search, since a substring match could silently pick the
wrong real record).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.aog_event import AogEvent
from app.models.user import User
from app.services import (
    aircraft_service,
    aog_service,
    part_service,
    purchase_order_service,
    vendor_service,
    work_order_service,
)

ENTITY_TYPES = (
    "aircraft",
    "work_order",
    "task",
    "part",
    "vendor",
    "purchase_order",
    "technician",
    "aog_event",
)


@dataclass
class ResolvedEntity:
    entity_type: str
    entity_id: str
    display: str


@dataclass
class AmbiguousMatch:
    entity_type: str
    candidates: list[ResolvedEntity]


@dataclass
class NotFound:
    entity_type: str
    identifier: str


ResolutionResult = ResolvedEntity | AmbiguousMatch | NotFound


def _try_uuid(identifier: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(identifier)
    except (ValueError, AttributeError):
        return None


def resolve_aircraft(
    db: Session, *, organization_id: uuid.UUID, identifier: str
) -> ResolutionResult:
    as_uuid = _try_uuid(identifier)
    if as_uuid is not None:
        try:
            aircraft = aircraft_service.get_aircraft(
                db, organization_id=organization_id, aircraft_id=as_uuid
            )
            return ResolvedEntity("aircraft", str(aircraft.id), aircraft.registration)
        except Exception:
            return NotFound("aircraft", identifier)

    needle = identifier.strip().upper()
    matches = [
        a
        for a in aircraft_service.list_aircraft(db, organization_id=organization_id)
        if a.registration.strip().upper() == needle
    ]
    if not matches:
        return NotFound("aircraft", identifier)
    if len(matches) > 1:
        return AmbiguousMatch(
            "aircraft",
            [
                ResolvedEntity("aircraft", str(a.id), f"{a.registration} — Aircraft {a.id}")
                for a in matches
            ],
        )
    a = matches[0]
    return ResolvedEntity("aircraft", str(a.id), a.registration)


def resolve_work_order(
    db: Session, *, organization_id: uuid.UUID, identifier: str
) -> ResolutionResult:
    as_uuid = _try_uuid(identifier)
    if as_uuid is not None:
        try:
            wo = work_order_service.get_work_order(
                db, organization_id=organization_id, work_order_id=as_uuid
            )
            return ResolvedEntity("work_order", str(wo.id), wo.work_order_number)
        except Exception:
            return NotFound("work_order", identifier)

    needle = identifier.strip().upper()
    matches = [
        w
        for w in work_order_service.list_work_orders(db, organization_id=organization_id)
        if w.work_order_number.strip().upper() == needle
    ]
    if not matches:
        return NotFound("work_order", identifier)
    if len(matches) > 1:
        return AmbiguousMatch(
            "work_order",
            [
                ResolvedEntity(
                    "work_order", str(w.id), f"{w.work_order_number} — Work Order {w.id}"
                )
                for w in matches
            ],
        )
    w = matches[0]
    return ResolvedEntity("work_order", str(w.id), w.work_order_number)


def resolve_part(db: Session, *, organization_id: uuid.UUID, identifier: str) -> ResolutionResult:
    as_uuid = _try_uuid(identifier)
    if as_uuid is not None:
        try:
            part = part_service.get_part(db, organization_id=organization_id, part_id=as_uuid)
            return ResolvedEntity("part", str(part.id), part.part_number)
        except Exception:
            return NotFound("part", identifier)

    needle = identifier.strip().upper()
    matches = [
        p
        for p in part_service.list_parts(db, organization_id=organization_id)
        if p.part_number.strip().upper() == needle
    ]
    if not matches:
        return NotFound("part", identifier)
    if len(matches) > 1:
        return AmbiguousMatch(
            "part",
            [ResolvedEntity("part", str(p.id), f"{p.part_number} — Part {p.id}") for p in matches],
        )
    p = matches[0]
    return ResolvedEntity("part", str(p.id), p.part_number)


def resolve_vendor(db: Session, *, organization_id: uuid.UUID, identifier: str) -> ResolutionResult:
    as_uuid = _try_uuid(identifier)
    if as_uuid is not None:
        try:
            vendor = vendor_service.get_vendor(
                db, organization_id=organization_id, vendor_id=as_uuid
            )
            return ResolvedEntity("vendor", str(vendor.id), vendor.name)
        except Exception:
            return NotFound("vendor", identifier)

    needle = identifier.strip().upper()
    matches = [
        v
        for v in vendor_service.list_vendors(db, organization_id=organization_id)
        if v.name.strip().upper() == needle
    ]
    if not matches:
        return NotFound("vendor", identifier)
    if len(matches) > 1:
        return AmbiguousMatch(
            "vendor",
            [ResolvedEntity("vendor", str(v.id), f"{v.name} — Vendor {v.id}") for v in matches],
        )
    v = matches[0]
    return ResolvedEntity("vendor", str(v.id), v.name)


def resolve_purchase_order(
    db: Session, *, organization_id: uuid.UUID, identifier: str
) -> ResolutionResult:
    as_uuid = _try_uuid(identifier)
    if as_uuid is not None:
        try:
            po = purchase_order_service.get_purchase_order(
                db, organization_id=organization_id, purchase_order_id=as_uuid
            )
            return ResolvedEntity("purchase_order", str(po.id), po.po_number)
        except Exception:
            return NotFound("purchase_order", identifier)

    needle = identifier.strip().upper()
    matches = [
        po
        for po in purchase_order_service.list_purchase_orders(db, organization_id=organization_id)
        if po.po_number.strip().upper() == needle
    ]
    if not matches:
        return NotFound("purchase_order", identifier)
    if len(matches) > 1:
        return AmbiguousMatch(
            "purchase_order",
            [
                ResolvedEntity("purchase_order", str(po.id), f"{po.po_number} — PO {po.id}")
                for po in matches
            ],
        )
    po = matches[0]
    return ResolvedEntity("purchase_order", str(po.id), po.po_number)


def resolve_technician(
    db: Session, *, organization_id: uuid.UUID, identifier: str
) -> ResolutionResult:
    as_uuid = _try_uuid(identifier)
    if as_uuid is not None:
        user = db.execute(
            select(User).where(User.id == as_uuid, User.organization_id == organization_id)
        ).scalar_one_or_none()
        if user is None:
            return NotFound("technician", identifier)
        return ResolvedEntity("technician", str(user.id), user.full_name)

    needle = identifier.strip().lower()
    users = list(
        db.execute(select(User).where(User.organization_id == organization_id)).scalars().all()
    )
    matches = [
        u
        for u in users
        if u.full_name.strip().lower() == needle or u.email.strip().lower() == needle
    ]
    if not matches:
        return NotFound("technician", identifier)
    if len(matches) > 1:
        return AmbiguousMatch(
            "technician",
            [
                ResolvedEntity("technician", str(u.id), f"{u.full_name} — {u.email}")
                for u in matches
            ],
        )
    u = matches[0]
    return ResolvedEntity("technician", str(u.id), u.full_name)


def resolve_aog_event(
    db: Session, *, organization_id: uuid.UUID, identifier: str
) -> ResolutionResult:
    as_uuid = _try_uuid(identifier)
    if as_uuid is None:
        return NotFound("aog_event", identifier)
    try:
        event = aog_service.get_aog_event(db, organization_id=organization_id, event_id=as_uuid)
        return ResolvedEntity("aog_event", str(event.id), f"AOG {event.id} ({event.status})")
    except Exception:
        return NotFound("aog_event", identifier)


def active_aog_event_for_aircraft(
    db: Session, *, organization_id: uuid.UUID, aircraft_id: uuid.UUID
) -> AogEvent | None:
    """Real helper reused by the deterministic message-level resolver below —
    not duplicated business logic: aog_service already exposes list_aog_events;
    this only picks the active one, same rule aog_recovery_service uses.
    """
    events = aog_service.list_aog_events(
        db, organization_id=organization_id, aircraft_id=aircraft_id
    )
    for event in events:
        if event.status in ("DECLARED", "IN_RECOVERY"):
            return event
    return None
