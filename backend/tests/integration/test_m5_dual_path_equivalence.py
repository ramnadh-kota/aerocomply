import io
import uuid
import pytest
from datetime import datetime, timezone
import openpyxl
from sqlalchemy.orm import Session

from app.models.asset import Asset, AssetType
from app.models.flight import Flight
from app.models.import_job import ImportDomain, ImportJobStatus
from app.models.organization import Organization
from app.models.user import User
from app.services import flight_service, asset_service, import_service


@pytest.fixture
def dual_path_org(db_session: Session) -> Organization:
    org = Organization(name=f"Dual Path Org {uuid.uuid4().hex[:6]}")
    db_session.add(org)
    db_session.commit()
    db_session.refresh(org)
    return org


@pytest.fixture
def dual_path_user(db_session: Session, dual_path_org: Organization) -> User:
    user = User(
        organization_id=dual_path_org.id,
        email=f"commander-{uuid.uuid4().hex[:6]}@example.com",
        full_name="Fleet Commander",
        hashed_password="hash",
        is_active=True,
        email_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _create_flight_xlsx(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Flights"
    for r_idx, row in enumerate(rows, 1):
        for c_idx, val in enumerate(row, 1):
            ws.cell(row=r_idx, column=c_idx, value=val)
    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


def test_m5_dual_path_operational_equivalence(
    db_session: Session, dual_path_org: Organization, dual_path_user: User
):
    """M5 Critical Dual-Path Test (Section 33):
    Proves that a Manual Flight Record and an Equivalent Excel Flight Record
    produce identical domain, operational, utilization, and intelligence outcomes.
    """
    flight_date = datetime(2026, 4, 15, 10, 0, 0, tzinfo=timezone.utc)

    # -------------------------------------------------------------------------
    # PATH 1: MANUAL ENTRY PATH
    # -------------------------------------------------------------------------
    # 1. Create asset for manual entry
    manual_asset = Asset(
        organization_id=dual_path_org.id,
        registration="VT-MANUAL",
        model="Pilatus PC-12",
        asset_type=AssetType.AIRCRAFT.value,
        status="ACTIVE",
    )
    db_session.add(manual_asset)
    db_session.commit()
    db_session.refresh(manual_asset)

    # 2. Record manual flight: 1.8 hours (108 mins), 1 cycle, flight KA-501
    manual_flight = flight_service.record_flight(
        db_session,
        organization_id=dual_path_org.id,
        actor_user_id=dual_path_user.id,
        asset_id=manual_asset.id,
        flown_at=flight_date,
        duration_minutes=108,  # 1.8 hours
        cycles=1,
        flight_number="KA-501",
        origin="VOMM",
        destination="VOBL",
        mission_type="PASSENGER",
        status="COMPLETED",
        source="MANUAL",
        update_battery=False,
    )
    assert manual_flight.id is not None

    # -------------------------------------------------------------------------
    # PATH 2: EXCEL IMPORT PATH (Ingestion -> Mapping -> Domain Service)
    # -------------------------------------------------------------------------
    # 1. Create asset for excel import
    import_asset = Asset(
        organization_id=dual_path_org.id,
        registration="VT-EXCEL",
        model="Pilatus PC-12",
        asset_type=AssetType.AIRCRAFT.value,
        status="ACTIVE",
    )
    db_session.add(import_asset)
    db_session.commit()
    db_session.refresh(import_asset)

    # 2. Prepare Excel workbook with matching flight data: 1.8 hours, 1 cycle, KA-501
    excel_rows = [
        ["Aircraft Registration", "Date of Flight", "Flight Hours", "Cycles", "Flight No", "Origin", "Destination", "Mission"],
        ["VT-EXCEL", "2026-04-15", 1.8, 1, "KA-501", "VOMM", "VOBL", "PASSENGER"],
    ]
    excel_content = _create_flight_xlsx(excel_rows)

    # 3. Import through Import Center pipeline
    import_job = import_service.create_import_job(
        db_session,
        organization_id=dual_path_org.id,
        actor_user_id=dual_path_user.id,
        domain=ImportDomain.FLIGHT,
        filename="legacy_ops_log.xlsx",
        file_content=excel_content,
        match_strategy="MATCH_EXISTING",
    )
    assert import_job.rows_total == 1
    assert import_job.rows_valid == 1
    assert import_job.rows_invalid == 0

    # 4. Commit import (invokes authoritative flight_service.record_flight internally)
    committed_job = import_service.commit_import_job(
        db_session,
        organization_id=dual_path_org.id,
        actor_user_id=dual_path_user.id,
        job_id=import_job.id,
    )
    assert committed_job.status == ImportJobStatus.COMPLETED
    assert committed_job.rows_created == 1

    # -------------------------------------------------------------------------
    # 3. VERIFY DUAL-PATH OPERATIONAL EQUIVALENCE
    # -------------------------------------------------------------------------
    # A. Utilization equivalence
    manual_util = flight_service.get_utilization(
        db_session, organization_id=dual_path_org.id, asset_id=manual_asset.id
    )
    import_util = flight_service.get_utilization(
        db_session, organization_id=dual_path_org.id, asset_id=import_asset.id
    )

    assert manual_util["total_minutes"] == import_util["total_minutes"] == 108
    assert manual_util["total_cycles"] == import_util["total_cycles"] == 1
    assert manual_util["total_flights"] == import_util["total_flights"] == 1

    # B. Asset Service Operational State equivalence
    manual_asset_util = asset_service.get_asset_utilization(
        db_session, organization_id=dual_path_org.id, asset_id=manual_asset.id
    )
    import_asset_util = asset_service.get_asset_utilization(
        db_session, organization_id=dual_path_org.id, asset_id=import_asset.id
    )

    assert manual_asset_util.total_flight_hours == import_asset_util.total_flight_hours == 1.8
    assert manual_asset_util.total_cycles == import_asset_util.total_cycles == 1
    assert manual_asset_util.total_flights == import_asset_util.total_flights == 1

    # C. Flight History query equivalence
    manual_flights, m_total = flight_service.list_flights_for_asset(
        db_session, organization_id=dual_path_org.id, asset_id=manual_asset.id
    )
    import_flights, i_total = flight_service.list_flights_for_asset(
        db_session, organization_id=dual_path_org.id, asset_id=import_asset.id
    )

    assert m_total == i_total == 1
    mf = manual_flights[0]
    inf = import_flights[0]

    assert mf.flight_number == inf.flight_number == "KA-501"
    assert mf.duration_minutes == inf.duration_minutes == 108
    assert mf.cycles == inf.cycles == 1
    assert mf.origin == inf.origin == "VOMM"
    assert mf.destination == inf.destination == "VOBL"
    assert mf.mission_type == inf.mission_type == "PASSENGER"
    assert mf.status == inf.status == "COMPLETED"
    assert mf.source == "MANUAL"
    assert inf.source == "EXCEL_IMPORT"

    # D. Asset Operations domain contract equivalence
    manual_ops = asset_service.get_asset_operations(
        db_session, organization_id=dual_path_org.id, asset_id=manual_asset.id
    )
    import_ops = asset_service.get_asset_operations(
        db_session, organization_id=dual_path_org.id, asset_id=import_asset.id
    )

    assert manual_ops.utilization.total_flight_hours == import_ops.utilization.total_flight_hours == 1.8
    assert manual_ops.utilization.total_cycles == import_ops.utilization.total_cycles == 1
    assert manual_ops.utilization.total_flights == import_ops.utilization.total_flights == 1
