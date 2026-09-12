"""Tests for the bulk CSV import pipeline (validate -> preview -> commit):
row-level validation outcomes, tenant isolation of import jobs, duplicate
detection (within-file and against existing tenant data), and that a
cross-tenant registration collision is never possible.
"""
import uuid

import pytest

from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.import_job import ImportDomain, ImportJobStatus
from app.schemas.aircraft import AircraftCreateRequest
from app.services import aircraft_service, import_service


def _csv(rows: list[str], header: str = "registration,msn,aircraft_type,status") -> bytes:
    return ("\n".join([header, *rows])).encode("utf-8")


def test_validate_all_valid_rows(db_session):
    org_id = uuid.uuid4()
    content = _csv(["N100AB,MSN-1,A320,ACTIVE", "N200CD,MSN-2,B737,ACTIVE"])
    job = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    assert job.rows_total == 2
    assert job.rows_valid == 2
    assert job.rows_invalid == 0
    assert job.status == ImportJobStatus.VALIDATED
    assert all(r["status"] == "VALID" for r in job.row_results)


def test_validate_missing_required_field_is_invalid(db_session):
    org_id = uuid.uuid4()
    content = _csv([",MSN-1,A320,ACTIVE"])  # missing registration
    job = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    assert job.rows_invalid == 1
    assert job.row_results[0]["status"] == "INVALID"
    assert "registration is required" in job.row_results[0]["errors"]


def test_validate_missing_optional_status_is_warning(db_session):
    org_id = uuid.uuid4()
    content = _csv(["N300EF,MSN-3,A321,"])
    job = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    assert job.row_results[0]["status"] == "WARNING"
    assert job.rows_valid == 1  # WARNING rows are still importable


def test_validate_duplicate_registration_within_file_is_invalid(db_session):
    org_id = uuid.uuid4()
    content = _csv(["N400GH,MSN-4,A320,ACTIVE", "N400GH,MSN-5,A320,ACTIVE"])
    job = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    assert job.row_results[0]["status"] == "VALID"
    assert job.row_results[1]["status"] == "INVALID"
    assert "Duplicate registration" in job.row_results[1]["errors"][0]


def test_validate_registration_colliding_with_existing_tenant_aircraft_is_invalid(db_session):
    org_id = uuid.uuid4()
    aircraft_service.create_aircraft(
        db_session,
        organization_id=org_id,
        payload=AircraftCreateRequest(
            registration="N500IJ", msn="MSN-EXISTING", aircraft_type="A320"
        ),
    )
    content = _csv(["N500IJ,MSN-6,A320,ACTIVE"])
    job = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    assert job.row_results[0]["status"] == "INVALID"
    assert "already exists" in job.row_results[0]["errors"][0]


def test_cross_tenant_registration_collision_does_not_block_import(db_session):
    """The same registration in a DIFFERENT tenant must never be treated as
    a duplicate — uniqueness is per-tenant, never global."""
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    aircraft_service.create_aircraft(
        db_session,
        organization_id=org_a,
        payload=AircraftCreateRequest(registration="N600KL", msn="MSN-A", aircraft_type="A320"),
    )
    content = _csv(["N600KL,MSN-B,A320,ACTIVE"])
    job = import_service.create_import_job(
        db_session,
        organization_id=org_b,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    assert job.row_results[0]["status"] == "VALID"


def test_missing_required_column_raises_before_any_row_processed(db_session):
    org_id = uuid.uuid4()
    content = b"registration,msn\nN700MN,MSN-7"  # missing aircraft_type column entirely
    with pytest.raises(AeroComplyError):
        import_service.create_import_job(
            db_session,
            organization_id=org_id,
            actor_user_id=None,
            domain=ImportDomain.AIRCRAFT,
            filename="aircraft.csv",
            file_content=content,
        )


def test_empty_file_produces_zero_rows(db_session):
    org_id = uuid.uuid4()
    content = b"registration,msn,aircraft_type,status\n"
    job = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    assert job.rows_total == 0


def test_commit_creates_real_aircraft_records_and_skips_invalid_rows(db_session):
    org_id = uuid.uuid4()
    content = _csv(["N800OP,MSN-8,A320,ACTIVE", ",MSN-9,A320,ACTIVE"])  # 1 valid, 1 invalid
    job = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    assert job.rows_valid == 1
    assert job.rows_invalid == 1

    completed = import_service.commit_import_job(
        db_session, organization_id=org_id, actor_user_id=None, job_id=job.id
    )
    assert completed.status == ImportJobStatus.COMPLETED
    assert completed.rows_created == 1

    aircraft = aircraft_service.list_aircraft(db_session, organization_id=org_id)
    assert len(aircraft) == 1
    assert aircraft[0].registration == "N800OP"


def test_commit_twice_is_rejected(db_session):
    org_id = uuid.uuid4()
    content = _csv(["N900QR,MSN-10,A320,ACTIVE"])
    job = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    import_service.commit_import_job(
        db_session, organization_id=org_id, actor_user_id=None, job_id=job.id
    )
    with pytest.raises(ConflictError):
        import_service.commit_import_job(
            db_session, organization_id=org_id, actor_user_id=None, job_id=job.id
        )


def test_import_job_is_tenant_isolated(db_session):
    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    content = _csv(["N100ZZ,MSN-11,A320,ACTIVE"])
    job = import_service.create_import_job(
        db_session,
        organization_id=org_a,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    with pytest.raises(NotFoundError):
        import_service.get_import_job(db_session, organization_id=org_b, job_id=job.id)
    assert import_service.list_import_jobs(db_session, organization_id=org_b) == []


def test_repeated_import_of_same_registration_is_invalid_second_time(db_session):
    org_id = uuid.uuid4()
    content = _csv(["N200YY,MSN-12,A320,ACTIVE"])
    job1 = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    import_service.commit_import_job(
        db_session, organization_id=org_id, actor_user_id=None, job_id=job1.id
    )

    job2 = import_service.create_import_job(
        db_session,
        organization_id=org_id,
        actor_user_id=None,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=content,
    )
    assert job2.row_results[0]["status"] == "INVALID"
