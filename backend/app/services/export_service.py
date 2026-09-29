"""M14.28: Tenant Data Export Service.

Enables secure, tenant-isolated data exports for customer backups, regulatory audits,
and platform migration with complete audit lineage.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.aircraft import Aircraft
from app.models.asset import Asset
from app.models.finding import Finding
from app.models.flight import Flight
from app.models.work_order import WorkOrder
from app.services.audit_service import record_audit_event


def export_tenant_data_package(
    db: Session,
    *,
    organization_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
    include_categories: list[str] | None = None,
) -> dict[str, Any]:
    """Generates a complete or filtered export package for a single tenant."""
    categories = set(include_categories or ["FLEET", "FLIGHTS", "WORK_ORDERS", "FINDINGS"])
    now = datetime.now(UTC)
    package: dict[str, Any] = {
        "export_id": str(uuid.uuid4()),
        "organization_id": str(organization_id),
        "exported_at": now.isoformat(),
        "categories_included": list(categories),
        "data": {},
    }

    # 1. Fleet
    if "FLEET" in categories:
        assets = list(
            db.execute(
                select(Asset).where(
                    Asset.organization_id == organization_id,
                    Asset.deleted_at.is_(None),
                )
            ).scalars().all()
        )
        package["data"]["fleet"] = [
            {
                "id": str(a.id),
                "asset_type": a.asset_type,
                "identifier": a.registration or a.serial_number or str(a.id),
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in assets
        ]

    # 2. Flights
    if "FLIGHTS" in categories:
        flights = list(
            db.execute(
                select(Flight).where(
                    Flight.organization_id == organization_id,
                ).order_by(Flight.flown_at.desc()).limit(1000)
            ).scalars().all()
        )
        package["data"]["flights"] = [
            {
                "id": str(f.id),
                "flight_number": f.flight_number,
                "asset_id": str(f.asset_id),
                "duration_minutes": f.duration_minutes,
                "cycles": f.cycles,
                "flown_at": f.flown_at.isoformat() if f.flown_at else None,
            }
            for f in flights
        ]

    # 3. Work Orders
    if "WORK_ORDERS" in categories:
        work_orders = list(
            db.execute(
                select(WorkOrder).where(
                    WorkOrder.organization_id == organization_id,
                    WorkOrder.deleted_at.is_(None),
                ).limit(1000)
            ).scalars().all()
        )
        package["data"]["work_orders"] = [
            {
                "id": str(w.id),
                "work_order_number": w.work_order_number,
                "title": w.title,
                "status": w.status,
                "created_at": w.created_at.isoformat() if w.created_at else None,
            }
            for w in work_orders
        ]

    # 4. Findings
    if "FINDINGS" in categories:
        findings = list(
            db.execute(
                select(Finding).where(
                    Finding.organization_id == organization_id,
                ).limit(1000)
            ).scalars().all()
        )
        package["data"]["findings"] = [
            {
                "id": str(fn.id),
                "title": fn.title,
                "severity": str(fn.severity),
                "status": str(fn.status),
                "created_at": fn.created_at.isoformat() if fn.created_at else None,
            }
            for fn in findings
        ]

    record_audit_event(
        db,
        action="tenant.data_export_generated",
        entity_type="organization",
        entity_id=organization_id,
        organization_id=organization_id,
        user_id=actor_user_id,
        metadata={"export_id": package["export_id"], "categories": list(categories)},
    )
    return package
