"""Bulk CSV import pipeline: validate -> preview -> confirm -> commit.

Only one domain is wired up (Aircraft) — this is the reference
implementation of the pipeline architecture, not a claim that every MRO
domain is import-ready. Adding another domain means adding another
_validate_<domain>_rows/_commit_<domain>_row pair and a DOMAIN_VALIDATORS
entry; the job model, validation/preview/commit flow, and audit trail are
already domain-agnostic.

Row-level validation happens BEFORE anything is written to the database
(create_import_job only ever INSERTs the ImportJob record itself). Commit
replays exactly the rows already marked VALID/WARNING in that job's
row_results — never re-validates against a file the caller could swap.
"""

import csv
import io
import uuid
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.import_job import ImportDomain, ImportJob, ImportJobStatus
from app.schemas.aircraft import AircraftCreateRequest
from app.services import aircraft_service
from app.services.audit_service import record_audit_event

MAX_IMPORT_ROWS = 5000  # bounds in-memory parsing for a single onboarding batch

AIRCRAFT_REQUIRED_COLUMNS = ("registration", "msn", "aircraft_type")
AIRCRAFT_OPTIONAL_COLUMNS = ("status",)


def parse_csv(content: bytes) -> list[dict[str, str]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AeroComplyError("File is not valid UTF-8 text", code="invalid_file_encoding") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise AeroComplyError("File has no header row", code="invalid_file_format")

    rows = []
    for row in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
        if len(rows) > MAX_IMPORT_ROWS:
            raise AeroComplyError(
                f"File exceeds the maximum of {MAX_IMPORT_ROWS} rows per import",
                code="file_too_large",
            )
    return rows


def _validate_aircraft_rows(
    db: Session, *, organization_id: uuid.UUID, rows: list[dict[str, str]]
) -> list[dict[str, Any]]:
    existing_registrations = {
        r.upper()
        for r in db.execute(
            select(Aircraft.registration).where(Aircraft.organization_id == organization_id)
        ).scalars()
    }
    seen_in_file: set[str] = set()
    results: list[dict[str, Any]] = []

    for i, row in enumerate(rows, start=1):
        errors: list[str] = []
        warnings: list[str] = []

        registration = row.get("registration", "")
        msn = row.get("msn", "")
        aircraft_type = row.get("aircraft_type", "")

        if not registration:
            errors.append("registration is required")
        if not msn:
            errors.append("msn is required")
        if not aircraft_type:
            errors.append("aircraft_type is required")

        reg_key = registration.upper()
        if registration and reg_key in existing_registrations:
            errors.append(
                f"Aircraft registration {registration!r} already exists in this organization"
            )
        elif registration and reg_key in seen_in_file:
            errors.append(f"Duplicate registration {registration!r} within this file")

        status = row.get("status", "")
        if not status:
            warnings.append("status not provided — will default to ACTIVE")

        if registration:
            seen_in_file.add(reg_key)

        if errors:
            row_status = "INVALID"
        elif warnings:
            row_status = "WARNING"
        else:
            row_status = "VALID"

        results.append(
            {
                "row_number": i,
                "status": row_status,
                "errors": errors,
                "warnings": warnings,
                "data": {
                    "registration": registration,
                    "msn": msn,
                    "aircraft_type": aircraft_type,
                    "status": status or "ACTIVE",
                },
            }
        )
    return results


_DOMAIN_VALIDATORS = {
    ImportDomain.AIRCRAFT: _validate_aircraft_rows,
}
_DOMAIN_REQUIRED_COLUMNS = {
    ImportDomain.AIRCRAFT: AIRCRAFT_REQUIRED_COLUMNS,
}


def create_import_job(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    domain: str,
    filename: str,
    file_content: bytes,
) -> ImportJob:
    if domain not in _DOMAIN_VALIDATORS:
        raise AeroComplyError(f"Unsupported import domain: {domain}", code="unsupported_domain")

    rows = parse_csv(file_content)
    required = _DOMAIN_REQUIRED_COLUMNS[domain]
    if rows:
        missing_columns = [c for c in required if c not in rows[0]]
        if missing_columns:
            raise AeroComplyError(
                f"File is missing required column(s): {', '.join(missing_columns)}",
                code="missing_columns",
            )

    row_results = _DOMAIN_VALIDATORS[domain](db, organization_id=organization_id, rows=rows)
    rows_valid = sum(1 for r in row_results if r["status"] in ("VALID", "WARNING"))
    rows_invalid = sum(1 for r in row_results if r["status"] == "INVALID")

    job = ImportJob(
        organization_id=organization_id,
        domain=domain,
        filename=filename,
        status=ImportJobStatus.VALIDATED,
        created_by_user_id=actor_user_id,
        rows_total=len(rows),
        rows_valid=rows_valid,
        rows_invalid=rows_invalid,
        row_results=row_results,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def list_import_jobs(db: Session, *, organization_id: uuid.UUID) -> list[ImportJob]:
    return list(
        db.execute(
            select(ImportJob)
            .where(ImportJob.organization_id == organization_id)
            .order_by(ImportJob.created_at.desc())
        )
        .scalars()
        .all()
    )


def get_import_job(
    db: Session, *, organization_id: uuid.UUID, job_id: uuid.UUID, for_update: bool = False
) -> ImportJob:
    query = select(ImportJob).where(
        ImportJob.id == job_id, ImportJob.organization_id == organization_id
    )
    if for_update:
        query = query.with_for_update()
    job = db.execute(query).scalar_one_or_none()
    if job is None:
        raise NotFoundError("Import job not found")
    return job


def commit_import_job(
    db: Session, *, organization_id: uuid.UUID, actor_user_id: uuid.UUID | None, job_id: uuid.UUID
) -> ImportJob:
    # Atomically claim the job before doing any work: a plain SELECT (even
    # with_for_update) is not enough here because aircraft_service.
    # create_aircraft commits per row internally, which would release a
    # row lock held only across this function's own (uncommitted) span.
    # This conditional UPDATE is the actual compare-and-swap that makes two
    # concurrent commit_import_job calls on the same job mutually exclusive
    # — only one can move status off VALIDATED.
    claim = cast(
        CursorResult[Any],
        db.execute(
            sa_update(ImportJob)
            .where(
                ImportJob.id == job_id,
                ImportJob.organization_id == organization_id,
                ImportJob.status == ImportJobStatus.VALIDATED,
            )
            .values(status=ImportJobStatus.COMPLETED)
        ),
    )
    db.commit()
    if claim.rowcount == 0:
        job = get_import_job(db, organization_id=organization_id, job_id=job_id)
        raise ConflictError(f"Import job is already {job.status}; it cannot be committed again")

    job = get_import_job(db, organization_id=organization_id, job_id=job_id)

    importable_rows = [r for r in job.row_results if r["status"] in ("VALID", "WARNING")]
    created = 0
    failed = 0
    failure_messages: list[str] = []

    for row in importable_rows:
        try:
            if job.domain == ImportDomain.AIRCRAFT:
                aircraft_service.create_aircraft(
                    db,
                    organization_id=organization_id,
                    payload=AircraftCreateRequest(**row["data"]),
                )
                created += 1
        except AeroComplyError as exc:
            # Safe to surface: AeroComplyError messages are already
            # user-facing (e.g. "registration already exists"), never raw
            # database/internal detail.
            db.rollback()
            failed += 1
            failure_messages.append(f"Row {row['row_number']}: {exc.message}")
        except Exception:  # noqa: BLE001 - one bad row must not abort the whole batch
            # Anything else (e.g. a raw IntegrityError) is NOT put into
            # error_summary verbatim — that would leak internal
            # table/constraint details through a customer-visible API
            # response (see app/core/errors.py's own unhandled_error_handler
            # policy, applied here at the row level).
            db.rollback()
            failed += 1
            failure_messages.append(f"Row {row['row_number']}: could not be imported")

    job.status = ImportJobStatus.COMPLETED if failed == 0 else ImportJobStatus.FAILED
    job.rows_created = created
    job.rows_failed = failed
    job.error_summary = "; ".join(failure_messages) if failure_messages else None
    db.add(job)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="import.commit",
        entity_type="ImportJob",
        entity_id=job.id,
        metadata={"domain": job.domain, "rows_created": created, "rows_failed": failed},
    )
    db.commit()
    db.refresh(job)
    return job
