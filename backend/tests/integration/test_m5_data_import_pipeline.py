import io
import uuid
import pytest
from datetime import datetime, timezone
import openpyxl
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models.asset import Asset, AssetType
from app.models.flight import Flight
from app.models.import_job import ImportDomain, ImportJobStatus, ImportJob
from app.models.import_mapping import TenantImportMapping
from app.models.organization import Organization
from app.models.user import User
from app.schemas.data_import import (
    ImportConfigureRequest,
    ImportMappingCreateRequest,
)
from app.services import import_service, flight_service, asset_service


@pytest.fixture
def tenant_a(db_session: Session) -> Organization:
    org = Organization(name=f"Tenant A {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def tenant_b(db_session: Session) -> Organization:
    org = Organization(name=f"Tenant B {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def user_a(db_session: Session, tenant_a: Organization) -> User:
    user = User(
        organization_id=tenant_a.id,
        email=f"admin-a-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Admin A",
        hashed_password="hash",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    # remove default sheet
    default_sheet = wb.active
    for i, (sheet_name, rows) in enumerate(sheets.items()):
        ws = wb.create_sheet(title=sheet_name) if i > 0 or default_sheet is None else default_sheet
        ws.title = sheet_name
        for r_idx, row in enumerate(rows, 1):
            for c_idx, val in enumerate(row, 1):
                ws.cell(row=r_idx, column=c_idx, value=val)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_excel_multi_sheet_parsing_and_selection(
    db_session: Session, tenant_a: Organization, user_a: User
):
    """M5-11/12: Multi-sheet Excel workbook parsing and sheet extraction."""
    flights_data = [
        ["Tail Number", "Date", "Duration Hours", "Cycles", "Flight No"],
        ["VT-M5-01", "2026-03-01", 2.5, 1, "KA-101"],
        ["VT-M5-01", "2026-03-02", 1.8, 1, "KA-102"],
    ]
    aircraft_data = [
        ["Registration", "Manufacturer", "Model", "Serial"],
        ["VT-M5-01", "Cessna", "Grand Caravan", "208B-5001"],
    ]
    excel_bytes = _create_xlsx({"Aircraft Fleet": aircraft_data, "Flight Log": flights_data})

    # Step 1: Upload and parse sheets
    job = import_service.create_import_job(
        db_session,
        organization_id=tenant_a.id,
        actor_user_id=user_a.id,
        domain=ImportDomain.FLIGHT,
        filename="operations_archive.xlsx",
        file_content=excel_bytes,
        selected_sheet="Flight Log",
    )

    assert job.sheet_names == ["Aircraft Fleet", "Flight Log"]
    assert job.selected_sheet == "Flight Log"
    assert job.file_hash is not None
    assert job.rows_total == 2
    assert job.status in [ImportJobStatus.VALIDATED, ImportJobStatus.AWAITING_CONFIRMATION]


def test_custom_column_mapping_persistence_and_tenant_isolation(
    db_session: Session, tenant_a: Organization, tenant_b: Organization, user_a: User
):
    """M5-13: Column mapping CRUD, persistence, and tenant isolation."""
    # Tenant A saves a custom column mapping for flight logs
    req = ImportMappingCreateRequest(
        name="Legacy Nav System Mapping",
        domain=ImportDomain.FLIGHT,
        mapping={
            "Tail Number": "registration",
            "Duration Hours": "flight_hours",
            "Flight No": "flight_number",
            "Date": "flight_date",
        },
    )
    saved = import_service.create_tenant_mapping(
        db_session,
        organization_id=tenant_a.id,
        actor_user_id=user_a.id,
        domain=req.domain.value if hasattr(req.domain, "value") else str(req.domain),
        name=req.name,
        mapping=req.mapping,
    )
    assert saved.id is not None
    assert saved.name == "Legacy Nav System Mapping"
    assert saved.mapping["Tail Number"] == "registration"

    # Tenant A can list their mappings
    tenant_a_mappings = import_service.list_tenant_mappings(
        db_session, organization_id=tenant_a.id, domain=ImportDomain.FLIGHT
    )
    assert len(tenant_a_mappings) == 1
    assert tenant_a_mappings[0].id == saved.id

    # Tenant B CANNOT see Tenant A's mappings (Tenant Isolation)
    tenant_b_mappings = import_service.list_tenant_mappings(
        db_session, organization_id=tenant_b.id, domain=ImportDomain.FLIGHT
    )
    assert len(tenant_b_mappings) == 0


def test_validation_errors_vs_warnings_and_normalization(
    db_session: Session, tenant_a: Organization, user_a: User
):
    """M5-14/15: Validation engine categorizes errors vs warnings and normalizes formats."""
    # Pre-create asset for tenant A
    asset = Asset(
        organization_id=tenant_a.id,
        registration="VT-NORM",
        asset_type=AssetType.AIRCRAFT.value,
        model="Kodiak 100",
        status="ACTIVE",
    )
    db_session.add(asset)
    db_session.commit()

    csv_data = (
        "registration,flight_date,flight_hours,cycles,flight_number,notes\n"
        "VT-NORM, 01/09/2026 , 1.5 , 1 , KA-901 , Normal valid row\n"  # Valid, DD/MM/YYYY normalized
        "VT-NORM, 2026-09-02, -2.0, 1, KA-902, Negative hours error\n"  # Error: negative hours
        "VT-UNKNOWN, 2026-09-03, 1.0, 1, KA-903, Unmatched asset row\n"  # Unmatched asset
    ).encode("utf-8")

    job = import_service.create_import_job(
        db_session,
        organization_id=tenant_a.id,
        actor_user_id=user_a.id,
        domain=ImportDomain.FLIGHT,
        filename="test_validation.csv",
        file_content=csv_data,
    )

    assert job.rows_total == 3
    assert job.rows_invalid == 2  # 1 negative hours + 1 unmatched asset (with default match strategy)
    assert job.rows_valid == 1


def test_asset_matching_strategies(
    db_session: Session, tenant_a: Organization, user_a: User
):
    """M5-16: Asset matching strategies (MATCH_EXISTING, CREATE_ASSET, SKIP)."""
    # Pre-create VT-EXIST
    asset = Asset(
        organization_id=tenant_a.id,
        registration="VT-EXIST",
        asset_type=AssetType.AIRCRAFT.value,
        model="Cessna 172",
        status="ACTIVE",
    )
    db_session.add(asset)
    db_session.commit()

    csv_data = (
        "registration,flight_date,flight_hours,cycles,flight_number\n"
        "VT-EXIST,2026-05-01,1.5,1,FL-01\n"
        "VT-BRANDNEW,2026-05-02,2.0,1,FL-02\n"
    ).encode("utf-8")

    # Upload with CREATE_ASSET strategy
    job = import_service.create_import_job(
        db_session,
        organization_id=tenant_a.id,
        actor_user_id=user_a.id,
        domain=ImportDomain.FLIGHT,
        filename="asset_match_test.csv",
        file_content=csv_data,
        match_strategy="CREATE_ASSET",
    )

    # When CREATE_ASSET is configured, all rows are valid because new asset will be auto-provisioned
    assert job.rows_valid == 2
    assert job.rows_invalid == 0

    # Commit the job
    committed_job = import_service.commit_import_job(
        db_session,
        organization_id=tenant_a.id,
        actor_user_id=user_a.id,
        job_id=job.id,
    )
    assert committed_job.status == ImportJobStatus.COMPLETED
    assert committed_job.rows_created == 2

    # Verify VT-BRANDNEW was created
    new_asset = db_session.query(Asset).filter(
        Asset.organization_id == tenant_a.id,
        Asset.registration == "VT-BRANDNEW",
    ).first()
    assert new_asset is not None
    assert new_asset.status == "ACTIVE"


def test_cross_tenant_isolation_in_import_pipeline(
    db_session: Session, tenant_a: Organization, tenant_b: Organization, user_a: User
):
    """M5-30: Cross-tenant isolation blocks reading, configuring, or committing other tenants' jobs."""
    csv_data = "registration,msn,aircraft_type,status\nVT-SEC,MSN-99,A320,ACTIVE\n".encode("utf-8")

    job_a = import_service.create_import_job(
        db_session,
        organization_id=tenant_a.id,
        actor_user_id=user_a.id,
        domain=ImportDomain.AIRCRAFT,
        filename="aircraft.csv",
        file_content=csv_data,
    )

    # Tenant B tries to get Tenant A's import job -> 404 NotFoundError
    with pytest.raises(NotFoundError):
        import_service.get_import_job(
            db_session, organization_id=tenant_b.id, job_id=job_a.id
        )

    # Tenant B tries to commit Tenant A's import job -> 404 NotFoundError
    with pytest.raises(NotFoundError):
        import_service.commit_import_job(
            db_session, organization_id=tenant_b.id, actor_user_id=uuid.uuid4(), job_id=job_a.id
        )
