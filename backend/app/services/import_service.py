"""M5 Customer Data Onboarding & Import Center Service.

Architectural Rule (M5.14):
Manual flight entry and bulk import MUST use the same domain path.
This service parses, normalizes, maps, validates, stages, reviews, and
commits data through the authoritative domain services (aircraft_service,
drone_service, flight_service) without bypassing business logic or raw INSERTs.
"""

import csv
import hashlib
import io
import re
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import openpyxl
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, ConflictError, NotFoundError
from app.models.aircraft import Aircraft
from app.models.asset import Asset, AssetType
from app.models.flight import Flight
from app.models.import_job import ImportDomain, ImportJob, ImportJobStatus
from app.models.import_mapping import TenantImportMapping
from app.models.user import User
from app.schemas.aircraft import AircraftCreateRequest
from app.schemas.asset import AssetCreateRequest
from app.services import aircraft_service, asset_service, drone_service, flight_service
from app.services.audit_service import record_audit_event

MAX_IMPORT_ROWS = 50000  # bounds memory footprint for single onboarding batch

CANONICAL_SYNONYMS: dict[str, list[str]] = {
    "registration": [
        "reg", "reg no", "reg_no", "registration", "aircraft", "drone", "uav",
        "asset", "tail", "tail_number", "tail no", "tail number", "airframe",
        "asset_registration", "aircraft_registration", "aircraft registration",
        "drone_registration", "drone registration", "ident", "callsign",
    ],
    "flown_at": [
        "date", "flight_date", "flown_at", "date of flight", "flight date",
        "timestamp", "datetime", "flight_datetime", "departure date", "dep date",
    ],
    "duration_minutes": [
        "duration", "duration_minutes", "duration (min)", "minutes", "min",
        "time_minutes", "block_time_minutes", "flight_time_minutes",
    ],
    "flight_hours": [
        "fh", "flight_hours", "flight hours", "hours", "hrs", "airframe_hours",
        "flight_time", "total_hours", "block_hours", "duration_hours", "flight time",
    ],
    "cycles": [
        "fc", "cycles", "flight_cycles", "flight cycles", "landings", "sorties",
        "cycle_count", "operating_cycles", "flight_cycles_count",
    ],
    "flight_number": [
        "flight_no", "flight no", "flight number", "flight_number", "flight #", "flight",
        "mission_no", "mission no", "mission number", "sortie", "trip_number", "trip no",
    ],
    "pilot": [
        "pilot", "pilot_name", "pilot name", "operator", "pic", "pilot in command",
        "pilot_email", "crew", "commander", "captain",
    ],
    "origin": [
        "from", "origin", "departure", "dep", "orig", "departure_airport",
        "source", "from_location", "launch_site", "departure location",
    ],
    "destination": [
        "to", "destination", "arrival", "arr", "dest", "arrival_airport",
        "to_location", "recovery_site", "arrival location",
    ],
    "departure_time": ["dep_time", "departure_time", "start_time", "out", "off_block", "dep time"],
    "arrival_time": ["arr_time", "arrival_time", "end_time", "in", "on_block", "arr time"],
    "mission_type": ["mission", "mission_type", "type", "operation", "flight_type", "purpose", "mission type"],
    "status": ["status", "state", "flight_status"],
    "notes": ["notes", "remarks", "comments", "description"],
    "msn": ["msn", "serial", "serial_no", "serial_number", "manufacturer_serial_number", "serial no"],
    "aircraft_type": ["aircraft_type", "type", "model", "icao_type", "airframe_type", "aircraft type"],
    "manufacturer": ["manufacturer", "make", "oem", "builder"],
    "model": ["model", "series", "variant"],
}


def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _parse_date_string(val: Any) -> datetime | None:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=UTC)
    if not val:
        return None
    s = str(val).strip()
    if not s:
        return None

    # Handle ISO formats
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        pass

    # Standard date formats
    date_formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
        "%d-%b-%Y", "%d-%B-%Y", "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%m/%d/%Y %H:%M",
    ]
    for fmt in date_formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def _parse_duration_minutes(row: dict[str, Any]) -> int | None:
    # Check duration_minutes first
    min_val = row.get("duration_minutes")
    if min_val is not None and str(min_val).strip() != "":
        try:
            val_str = str(min_val).strip()
            if ":" in val_str:
                parts = val_str.split(":")
                return int(parts[0]) * 60 + int(parts[1])
            return int(float(val_str))
        except (ValueError, TypeError):
            pass

    # Check flight_hours
    hrs_val = row.get("flight_hours")
    if hrs_val is not None and str(hrs_val).strip() != "":
        try:
            val_str = str(hrs_val).strip()
            if ":" in val_str:
                parts = val_str.split(":")
                return int(parts[0]) * 60 + int(parts[1])
            hrs_float = float(val_str)
            return int(round(hrs_float * 60))
        except (ValueError, TypeError):
            pass

    return None


def _parse_cycles(row: dict[str, Any]) -> int | None:
    c_val = row.get("cycles")
    if c_val is not None and str(c_val).strip() != "":
        try:
            return int(float(str(c_val).strip()))
        except (ValueError, TypeError):
            pass
    return None


def auto_map_columns(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    normalized_headers = {h: h.strip().lower().replace("_", " ").replace("-", " ") for h in headers}

    for raw_header, norm_h in normalized_headers.items():
        matched_canonical = None
        for canonical_key, synonyms in CANONICAL_SYNONYMS.items():
            if norm_h == canonical_key.replace("_", " ") or norm_h in synonyms:
                matched_canonical = canonical_key
                break
        if matched_canonical:
            mapping[raw_header] = matched_canonical
    return mapping


def parse_file_content(
    content: bytes, filename: str, sheet_name: str | None = None
) -> tuple[list[dict[str, str]], list[str], str, str]:
    file_hash = compute_file_hash(content)
    lower_fn = filename.lower()

    if lower_fn.endswith(".xlsx") or lower_fn.endswith(".xls"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        except Exception as exc:
            raise AeroComplyError(f"Failed to parse Excel workbook: {exc}", code="invalid_excel_file") from exc

        sheet_names = wb.sheetnames
        if not sheet_names:
            raise AeroComplyError("Excel workbook has no sheets", code="empty_workbook")

        target_sheet = sheet_name if sheet_name and sheet_name in sheet_names else sheet_names[0]
        ws = wb[target_sheet]

        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            raise AeroComplyError("Selected sheet is empty", code="empty_sheet")

        if not header_row or all(c is None for c in header_row):
            raise AeroComplyError("Selected sheet has no headers", code="no_headers")

        headers = [str(c or "").strip() for c in header_row]
        raw_rows: list[dict[str, str]] = []

        for row in rows_iter:
            if not row or all(c is None or str(c).strip() == "" for c in row):
                continue  # skip blank lines
            row_dict = {}
            for h, cell_val in zip(headers, row):
                if h:
                    row_dict[h] = str(cell_val).strip() if cell_val is not None else ""
            raw_rows.append(row_dict)
            if len(raw_rows) > MAX_IMPORT_ROWS:
                raise AeroComplyError(
                    f"File exceeds maximum of {MAX_IMPORT_ROWS} rows", code="file_too_large"
                )
        return raw_rows, sheet_names, target_sheet, file_hash

    # CSV fallback
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise AeroComplyError("File is not valid text or spreadsheet", code="invalid_file_encoding") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise AeroComplyError("File has no header row", code="invalid_file_format")

    raw_rows = []
    for row in reader:
        if not any((v or "").strip() for v in row.values()):
            continue
        raw_rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items() if k})
        if len(raw_rows) > MAX_IMPORT_ROWS:
            raise AeroComplyError(
                f"File exceeds maximum of {MAX_IMPORT_ROWS} rows", code="file_too_large"
            )
    return raw_rows, ["Default"], "Default", file_hash


def auto_map_columns(headers: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for h in headers:
        clean = h.strip().lower().replace("_", " ").replace("-", " ")
        clean_raw = h.strip()
        matched = False
        for canonical, synonyms in CANONICAL_SYNONYMS.items():
            canonical_clean = canonical.lower().replace("_", " ")
            if (
                clean == canonical_clean
                or clean in synonyms
                or clean_raw.lower() in synonyms
                or clean in [s.replace("_", " ") for s in synonyms]
            ):
                mapping[clean_raw] = canonical
                matched = True
                break
        if not matched:
            mapping[clean_raw] = clean_raw
    return mapping


def _apply_mapping(row: dict[str, str], column_mapping: dict[str, str]) -> dict[str, Any]:
    canonical_row: dict[str, Any] = {}
    for src_col, val in row.items():
        target_field = column_mapping.get(src_col) or column_mapping.get(src_col.strip())
        if target_field:
            canonical_row[target_field] = val
        else:
            canonical_row[src_col] = val
    return canonical_row


# ---------------------------------------------------------------------------
# Domain Row Validators
# ---------------------------------------------------------------------------


def _validate_aircraft_rows(
    db: Session,
    *,
    organization_id: uuid.UUID,
    raw_rows: list[dict[str, str]],
    column_mapping: dict[str, str],
    match_strategy: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    existing_registrations = {
        r.upper()
        for r in db.execute(
            select(Aircraft.registration).where(Aircraft.organization_id == organization_id)
        ).scalars()
    }
    seen_in_file: set[str] = set()
    results: list[dict[str, Any]] = []

    for i, raw_row in enumerate(raw_rows, start=1):
        errors: list[str] = []
        warnings: list[str] = []
        row = _apply_mapping(raw_row, column_mapping)

        registration = (row.get("registration") or "").strip()
        msn = (row.get("msn") or "").strip()
        aircraft_type = (row.get("aircraft_type") or row.get("model") or "").strip()

        if not registration:
            errors.append("registration is required")
        if not msn:
            errors.append("msn is required")
        if not aircraft_type:
            errors.append("aircraft_type is required")

        reg_key = registration.upper() if registration else ""
        if registration and reg_key in existing_registrations:
            errors.append(f"Aircraft registration {registration!r} already exists in this organization")
        elif registration and reg_key in seen_in_file:
            errors.append(f"Duplicate registration {registration!r} within this file")

        status = (row.get("status") or "").strip().upper()
        if not status:
            warnings.append("status not provided — will default to ACTIVE")

        if registration:
            seen_in_file.add(reg_key)

        row_status = "INVALID" if errors else ("WARNING" if warnings else "VALID")
        results.append({
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
            "matched_asset_id": None,
            "match_action": None,
        })
    return results, []


def _validate_drone_rows(
    db: Session,
    *,
    organization_id: uuid.UUID,
    raw_rows: list[dict[str, str]],
    column_mapping: dict[str, str],
    match_strategy: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    existing_registrations = {
        r.upper()
        for r in db.execute(
            select(Asset.registration).where(
                Asset.organization_id == organization_id,
                Asset.asset_type == AssetType.DRONE.value,
                Asset.is_deleted.is_(False),
            )
        ).scalars()
    }
    seen_in_file: set[str] = set()
    results: list[dict[str, Any]] = []

    for i, raw_row in enumerate(raw_rows, start=1):
        errors: list[str] = []
        warnings: list[str] = []
        row = _apply_mapping(raw_row, column_mapping)

        registration = (row.get("registration") or "").strip()
        manufacturer = (row.get("manufacturer") or "").strip()
        model = (row.get("model") or "").strip()
        serial_number = (row.get("serial_number") or row.get("msn") or "").strip()

        if not registration:
            errors.append("registration is required")

        reg_key = registration.upper() if registration else ""
        if registration and reg_key in existing_registrations:
            errors.append(f"Drone registration {registration!r} already exists in organization")
        elif registration and reg_key in seen_in_file:
            errors.append(f"Duplicate registration {registration!r} within this file")

        if not manufacturer:
            warnings.append("manufacturer not provided — will default to Unknown")
        if not model:
            warnings.append("model not provided — will default to Unknown")

        status = (row.get("status") or "").strip().upper()
        if not status:
            warnings.append("status not provided — will default to ACTIVE")

        if registration:
            seen_in_file.add(reg_key)

        row_status = "INVALID" if errors else ("WARNING" if warnings else "VALID")
        results.append({
            "row_number": i,
            "status": row_status,
            "errors": errors,
            "warnings": warnings,
            "data": {
                "registration": registration,
                "manufacturer": manufacturer or "Unknown",
                "model": model or "Unknown",
                "serial_number": serial_number or None,
                "status": status or "ACTIVE",
            },
            "matched_asset_id": None,
            "match_action": None,
        })
    return results, []


def _validate_flight_rows(
    db: Session,
    *,
    organization_id: uuid.UUID,
    raw_rows: list[dict[str, str]],
    column_mapping: dict[str, str],
    match_strategy: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    match_strategy = match_strategy or {}

    # Query all active assets for this organization (by registration and ID)
    assets_by_reg = {
        a.registration.upper(): a
        for a in db.execute(
            select(Asset).where(
                Asset.organization_id == organization_id,
                Asset.deleted_at.is_(None),
            )
        ).scalars().all()
    }
    # Also check Aircraft table for legacy mappings
    aircraft_by_reg = {
        a.registration.upper(): a
        for a in db.execute(
            select(Aircraft).where(Aircraft.organization_id == organization_id)
        ).scalars().all()
    }

    # Query pilots by email/name
    pilots = {
        u.email.lower(): u
        for u in db.execute(
            select(User).where(User.organization_id == organization_id, User.is_active.is_(True))
        ).scalars().all()
    }

    seen_flights: set[str] = set()
    unmatched_assets: set[str] = set()
    results: list[dict[str, Any]] = []

    for i, raw_row in enumerate(raw_rows, start=1):
        errors: list[str] = []
        warnings: list[str] = []
        row = _apply_mapping(raw_row, column_mapping)

        registration = (row.get("registration") or "").strip()
        if not registration:
            errors.append("registration / asset identifier is required")

        reg_key = registration.upper() if registration else ""
        matched_asset = assets_by_reg.get(reg_key)
        matched_asset_id = None
        match_action = None

        if matched_asset:
            matched_asset_id = str(matched_asset.id)
            match_action = "MATCH_EXISTING"
        elif reg_key in aircraft_by_reg:
            # Found in aircraft table
            ac = aircraft_by_reg[reg_key]
            # Find associated Asset row
            asset_row = db.execute(
                select(Asset).where(
                    Asset.organization_id == organization_id,
                    Asset.registration == reg_key,
                    Asset.deleted_at.is_(None),
                )
            ).scalars().first()
            if asset_row:
                matched_asset_id = str(asset_row.id)
                match_action = "MATCH_EXISTING"
            else:
                matched_asset_id = str(ac.id)
                match_action = "MATCH_EXISTING"
        else:
            # Asset not found
            if registration:
                unmatched_assets.add(registration)
            if isinstance(match_strategy, str):
                action = match_strategy
            elif isinstance(match_strategy, dict):
                action = (
                    match_strategy.get(registration)
                    or match_strategy.get(reg_key)
                    or match_strategy.get("*")
                    or match_strategy.get("strategy")
                )
            else:
                action = None

            if action == "CREATE_ASSET":
                match_action = "CREATE_ASSET"
                warnings.append(f"Asset {registration!r} will be auto-created during import")
            elif action == "SKIP":
                match_action = "SKIP"
                warnings.append(f"Asset {registration!r} is marked to be skipped")
            else:
                errors.append(f"Asset {registration!r} not found in organization. Select match, create, or skip.")

        # Date validation
        flown_at_raw = row.get("flown_at")
        flown_at = _parse_date_string(flown_at_raw)
        if flown_at is None:
            errors.append(f"Invalid flight date format: {flown_at_raw!r}")

        # Duration validation
        duration_minutes = _parse_duration_minutes(row)
        if duration_minutes is None:
            errors.append("Flight duration (duration_minutes or flight_hours) is required and must be positive")
        elif duration_minutes <= 0:
            errors.append("Flight duration must be strictly greater than 0")
        elif duration_minutes > 1440:
            warnings.append(f"Suspicious long flight duration: {duration_minutes} minutes ({round(duration_minutes/60, 1)} hrs)")

        # Cycles validation
        cycles = _parse_cycles(row)
        if cycles is None:
            cycles = 1  # default 1 cycle
        elif cycles <= 0:
            errors.append("Cycles must be a positive integer")

        flight_number = (row.get("flight_number") or "").strip() or None
        origin = (row.get("origin") or "").strip() or None
        destination = (row.get("destination") or "").strip() or None
        departure_time = _parse_date_string(row.get("departure_time"))
        arrival_time = _parse_date_string(row.get("arrival_time"))
        mission_type = (row.get("mission_type") or "").strip() or None
        status = (row.get("status") or "").strip().upper() or "COMPLETED"
        notes = (row.get("notes") or "").strip() or None

        # Pilot matching (optional)
        pilot_raw = (row.get("pilot") or "").strip().lower()
        pilot_user_id = None
        if pilot_raw:
            pilot_match = pilots.get(pilot_raw)
            if pilot_match:
                pilot_user_id = str(pilot_match.id)
            else:
                warnings.append(f"Pilot {pilot_raw!r} not found in organization users — logged as unassigned")

        # Duplicate checking in file
        dedup_key = f"{reg_key}|{flight_number or ''}|{flown_at.isoformat() if flown_at else ''}"
        if dedup_key in seen_flights:
            warnings.append(f"Potential duplicate flight in spreadsheet: {flight_number or 'unnamed'} on {flown_at}")
        seen_flights.add(dedup_key)

        row_status = "INVALID" if errors else ("WARNING" if warnings else "VALID")
        results.append({
            "row_number": i,
            "status": row_status,
            "errors": errors,
            "warnings": warnings,
            "data": {
                "registration": registration,
                "flight_number": flight_number,
                "origin": origin,
                "destination": destination,
                "departure_time": departure_time.isoformat() if departure_time else None,
                "arrival_time": arrival_time.isoformat() if arrival_time else None,
                "flown_at": flown_at.isoformat() if flown_at else datetime.now(UTC).isoformat(),
                "duration_minutes": duration_minutes or 0,
                "cycles": cycles or 1,
                "mission_type": mission_type,
                "status": status,
                "source": "EXCEL_IMPORT",
                "pilot_user_id": pilot_user_id,
                "notes": notes,
            },
            "matched_asset_id": matched_asset_id,
            "match_action": match_action,
        })

    return results, sorted(unmatched_assets)


_DOMAIN_VALIDATORS = {
    ImportDomain.AIRCRAFT: _validate_aircraft_rows,
    ImportDomain.DRONE: _validate_drone_rows,
    ImportDomain.FLIGHT: _validate_flight_rows,
}

_DOMAIN_REQUIRED_COLUMNS = {
    ImportDomain.AIRCRAFT: ("registration", "msn", "aircraft_type"),
    ImportDomain.DRONE: ("registration",),
    ImportDomain.FLIGHT: ("registration", "flown_at"),
}


# ---------------------------------------------------------------------------
# Import Job Management (Validate -> Configure -> Preview -> Commit)
# ---------------------------------------------------------------------------


def create_import_job(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    domain: str,
    filename: str,
    file_content: bytes,
    sheet_name: str | None = None,
    selected_sheet: str | None = None,
    column_mapping: dict[str, str] | None = None,
    match_strategy: dict[str, str] | None = None,
) -> ImportJob:
    effective_sheet = sheet_name or selected_sheet
    domain_upper = domain.upper()
    if domain_upper not in _DOMAIN_VALIDATORS:
        raise AeroComplyError(f"Unsupported import domain: {domain}", code="unsupported_domain")

    raw_rows, sheet_names, selected_sheet, file_hash = parse_file_content(
        file_content, filename, sheet_name=effective_sheet
    )

    # Detect headers from first row
    headers = list(raw_rows[0].keys()) if raw_rows else []

    # Check for default saved mapping for this tenant
    if not column_mapping:
        saved_default = db.execute(
            select(TenantImportMapping).where(
                TenantImportMapping.organization_id == organization_id,
                TenantImportMapping.domain == domain_upper,
                TenantImportMapping.is_default.is_(True),
            )
        ).scalars().first()
        if saved_default:
            column_mapping = saved_default.mapping
        else:
            column_mapping = auto_map_columns(headers)

    required = _DOMAIN_REQUIRED_COLUMNS.get(domain_upper, ())
    if raw_rows and required:
        mapped_targets = set(column_mapping.values())
        missing_columns = [
            c for c in required
            if c not in mapped_targets and not any(h.lower() == c or h.lower() in CANONICAL_SYNONYMS.get(c, []) for h in headers)
        ]
        if missing_columns:
            raise AeroComplyError(
                f"File is missing required column(s): {', '.join(missing_columns)}",
                code="missing_columns",
            )

    row_results, unmatched_assets = _DOMAIN_VALIDATORS[domain_upper](
        db,
        organization_id=organization_id,
        raw_rows=raw_rows,
        column_mapping=column_mapping,
        match_strategy=match_strategy,
    )

    rows_valid = sum(1 for r in row_results if r["status"] in ("VALID", "WARNING"))
    rows_invalid = sum(1 for r in row_results if r["status"] == "INVALID")
    warning_count = sum(1 for r in row_results if r["status"] == "WARNING")
    error_count = sum(len(r["errors"]) for r in row_results)

    job = ImportJob(
        organization_id=organization_id,
        domain=domain_upper,
        filename=filename,
        file_hash=file_hash,
        status=ImportJobStatus.VALIDATED,
        created_by_user_id=actor_user_id,
        sheet_names=sheet_names,
        selected_sheet=selected_sheet,
        column_mapping=column_mapping,
        match_strategy=match_strategy or {},
        rows_total=len(raw_rows),
        rows_valid=rows_valid,
        rows_invalid=rows_invalid,
        warning_count=warning_count,
        error_count=error_count,
        row_results=row_results,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def configure_import_job(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    job_id: uuid.UUID,
    column_mapping: dict[str, str] | None = None,
    match_strategy: dict[str, str] | None = None,
) -> ImportJob:
    job = get_import_job(db, organization_id=organization_id, job_id=job_id)
    if job.status not in (ImportJobStatus.VALIDATED, ImportJobStatus.STAGED):
        raise ConflictError(f"Cannot configure import job in status {job.status}")

    # Re-apply mapping and match strategy on original data
    if column_mapping is not None:
        job.column_mapping = column_mapping
    if match_strategy is not None:
        merged_strategy = dict(job.match_strategy or {})
        merged_strategy.update(match_strategy)
        job.match_strategy = merged_strategy

    raw_data_rows = [r["data"] for r in job.row_results]
    row_results, unmatched = _DOMAIN_VALIDATORS[job.domain](
        db,
        organization_id=organization_id,
        raw_rows=raw_data_rows,
        column_mapping=job.column_mapping or {},
        match_strategy=job.match_strategy,
    )

    job.row_results = row_results
    job.rows_valid = sum(1 for r in row_results if r["status"] in ("VALID", "WARNING"))
    job.rows_invalid = sum(1 for r in row_results if r["status"] == "INVALID")
    job.warning_count = sum(1 for r in row_results if r["status"] == "WARNING")
    job.error_count = sum(len(r["errors"]) for r in row_results)
    job.status = ImportJobStatus.VALIDATED

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
    """M5.14: Commits staged records through identical domain services."""
    claim = cast(
        CursorResult[Any],
        db.execute(
            sa_update(ImportJob)
            .where(
                ImportJob.id == job_id,
                ImportJob.organization_id == organization_id,
                ImportJob.status.in_([ImportJobStatus.VALIDATED, ImportJobStatus.STAGED]),
            )
            .values(status=ImportJobStatus.IMPORTING)
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
        if row.get("match_action") == "SKIP":
            continue
        try:
            row_data = row["data"]
            if job.domain == ImportDomain.AIRCRAFT:
                aircraft_service.create_aircraft(
                    db,
                    organization_id=organization_id,
                    payload=AircraftCreateRequest(**row_data),
                )
                created += 1

            elif job.domain == ImportDomain.DRONE:
                drone_service.create_drone(
                    db,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    registration=row_data["registration"],
                    manufacturer=row_data.get("manufacturer"),
                    model=row_data.get("model"),
                    serial_number=row_data.get("serial_number"),
                )
                created += 1

            elif job.domain == ImportDomain.FLIGHT:
                matched_asset_id_str = row.get("matched_asset_id")
                target_asset_id: uuid.UUID | None = None

                if matched_asset_id_str:
                    target_asset_id = uuid.UUID(matched_asset_id_str)
                elif row.get("match_action") == "CREATE_ASSET":
                    # Auto-provision asset
                    reg = row_data["registration"]
                    new_asset = asset_service.create_asset(
                        db,
                        organization_id=organization_id,
                        actor_user_id=actor_user_id,
                        payload=AssetCreateRequest(
                            asset_type=AssetType.AIRCRAFT.value,
                            registration=reg,
                            status="ACTIVE",
                        ),
                    )
                    target_asset_id = new_asset.id

                if not target_asset_id:
                    raise AeroComplyError(f"No asset associated with flight row {row['row_number']}")

                flown_at_dt = datetime.fromisoformat(row_data["flown_at"])
                dep_dt = datetime.fromisoformat(row_data["departure_time"]) if row_data.get("departure_time") else None
                arr_dt = datetime.fromisoformat(row_data["arrival_time"]) if row_data.get("arrival_time") else None
                pilot_uid = uuid.UUID(row_data["pilot_user_id"]) if row_data.get("pilot_user_id") else None

                flight_service.record_flight(
                    db,
                    organization_id=organization_id,
                    actor_user_id=actor_user_id,
                    asset_id=target_asset_id,
                    flown_at=flown_at_dt,
                    duration_minutes=int(row_data["duration_minutes"]),
                    cycles=int(row_data["cycles"]),
                    pilot_user_id=pilot_uid,
                    flight_number=row_data.get("flight_number"),
                    origin=row_data.get("origin"),
                    destination=row_data.get("destination"),
                    departure_time=dep_dt,
                    arrival_time=arr_dt,
                    mission_type=row_data.get("mission_type"),
                    status=row_data.get("status", "COMPLETED"),
                    source="EXCEL_IMPORT",
                    source_row_id=f"job_{job.id}_row_{row['row_number']}",
                    notes=row_data.get("notes"),
                    update_battery=True,
                )
                created += 1

        except AeroComplyError as exc:
            db.rollback()
            failed += 1
            failure_messages.append(f"Row {row['row_number']}: {exc.message}")
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            failed += 1
            failure_messages.append(f"Row {row['row_number']}: unexpected error ({type(exc).__name__})")

    if failed == 0:
        job.status = ImportJobStatus.COMPLETED
    elif created > 0:
        job.status = ImportJobStatus.COMPLETED_WITH_ERRORS
    else:
        job.status = ImportJobStatus.FAILED

    job.rows_created = created
    job.rows_failed = failed
    job.completed_at = datetime.now(UTC)
    job.error_summary = "; ".join(failure_messages) if failure_messages else None
    db.add(job)

    record_audit_event(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="import.commit",
        entity_type="ImportJob",
        entity_id=job.id,
        metadata={
            "domain": job.domain,
            "filename": job.filename,
            "file_hash": job.file_hash,
            "rows_created": created,
            "rows_failed": failed,
            "status": job.status,
        },
    )
    db.commit()
    db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# M5.6: Saved Column Mappings Service
# ---------------------------------------------------------------------------


def create_import_mapping(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    domain: str,
    name: str,
    mapping: dict[str, str],
    is_default: bool = False,
) -> TenantImportMapping:
    if is_default:
        # Clear previous default
        db.execute(
            sa_update(TenantImportMapping)
            .where(
                TenantImportMapping.organization_id == organization_id,
                TenantImportMapping.domain == domain.upper(),
            )
            .values(is_default=False)
        )

    saved_mapping = TenantImportMapping(
        organization_id=organization_id,
        domain=domain.upper(),
        name=name.strip(),
        mapping=mapping,
        is_default=is_default,
        created_by_user_id=actor_user_id,
    )
    db.add(saved_mapping)
    db.commit()
    db.refresh(saved_mapping)
    return saved_mapping


def list_import_mappings(
    db: Session, *, organization_id: uuid.UUID, domain: str | None = None
) -> list[TenantImportMapping]:
    stmt = select(TenantImportMapping).where(TenantImportMapping.organization_id == organization_id)
    if domain:
        stmt = stmt.where(TenantImportMapping.domain == domain.upper())
    return list(db.execute(stmt.order_by(TenantImportMapping.created_at.desc())).scalars().all())


def get_import_mapping(
    db: Session, *, organization_id: uuid.UUID, mapping_id: uuid.UUID
) -> TenantImportMapping:
    m = db.execute(
        select(TenantImportMapping).where(
            TenantImportMapping.id == mapping_id,
            TenantImportMapping.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Import mapping not found")
    return m


def delete_import_mapping(
    db: Session, *, organization_id: uuid.UUID, mapping_id: uuid.UUID
) -> None:
    m = get_import_mapping(db, organization_id=organization_id, mapping_id=mapping_id)
    db.delete(m)
    db.commit()


# Aliases
create_tenant_mapping = create_import_mapping
list_tenant_mappings = list_import_mappings
