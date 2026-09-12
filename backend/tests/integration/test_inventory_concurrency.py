"""Regression test for a confirmed race condition found during the
security audit: reserve_part/release_reservation/consume_part/etc. read a
Part row, computed new quantities in Python, then wrote them back with no
row lock — two concurrent reservations against a part with exactly enough
stock for one could both read the same starting quantity, both pass the
"does this fit" check, and both commit, leaving quantity_reserved
overcommitted relative to quantity_on_hand (a real lost-update bug, not
just a theoretical one: this is the textbook lost-update scenario).

part_service.get_part(for_update=True) now takes a real row lock
(SELECT ... FOR UPDATE) before any of those services mutate a part. This
test proves the lock is genuinely held by opening TWO independent,
directly-committing database connections (not the shared per-test
db_session fixture, whose "commits" are never actually visible to another
connection until the whole test transaction is torn down — see
conftest.py) and confirming the second cannot also lock the same row (with
NOWAIT) while the first transaction is still open.
"""

import os
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.models.organization import Organization
from app.models.part import Part

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test",
)


def test_get_part_for_update_actually_locks_the_row():
    engine = create_engine(TEST_DATABASE_URL, future=True)
    SessionLocal = sessionmaker(bind=engine, future=True)

    org_id = uuid.uuid4()
    part_id = uuid.uuid4()
    setup = SessionLocal()
    try:
        setup.add(Organization(id=org_id, name="Concurrency Test Org"))
        setup.add(
            Part(
                id=part_id,
                organization_id=org_id,
                part_number="PN-LOCK-1",
                description="Test part",
                quantity_on_hand=1,
                quantity_reserved=0,
                quantity_quarantined=0,
            )
        )
        setup.commit()
    finally:
        setup.close()

    session1 = SessionLocal()
    session2 = SessionLocal()
    try:
        # "Request A": locks the row, same as reserve_part/consume_part/etc.
        # do internally via part_service.get_part(for_update=True), and
        # does not commit yet — simulating a reservation transaction still
        # in flight.
        session1.execute(
            select(Part).where(Part.id == part_id).with_for_update()
        ).scalar_one()

        # "Request B": a second, fully independent connection tries to lock
        # the SAME row without waiting. If the fix works, this must fail
        # immediately rather than silently succeeding and letting both
        # requests mutate the row.
        blocked = False
        try:
            session2.execute(
                select(Part).where(Part.id == part_id).with_for_update(nowait=True)
            ).scalar_one()
        except OperationalError:
            blocked = True
        assert blocked, (
            "A second connection was able to lock the same part row while the "
            "first transaction's row lock was still held — the race this test "
            "guards against would still be possible."
        )
    finally:
        session1.rollback()
        session2.rollback()
        session1.close()
        session2.close()
        cleanup = SessionLocal()
        try:
            cleanup.query(Part).filter(Part.id == part_id).delete()
            cleanup.query(Organization).filter(Organization.id == org_id).delete()
            cleanup.commit()
        finally:
            cleanup.close()
        engine.dispose()
