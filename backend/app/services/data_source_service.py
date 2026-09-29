"""B1: DataSource acquisition connector management service.

Invariants:
- All operations are strictly scoped to organization_id (no cross-tenant reads/writes).
- Secrets are never stored inline — secret_reference is only a key pointer.
- Connector type is immutable after creation (would require data migration).
- Acquisition stats are updated atomically to maintain observability accuracy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, NotFoundError
from app.models.data_source import DataSource, DataSourceConnectorType, DataSourceStatus
from app.schemas.data_source import DataSourceCreate, DataSourceUpdate
from app.services import audit_service

log = structlog.get_logger(__name__)


class DataSourceError(AeroComplyError):
    pass


def _assert_asset_in_tenant(db: Session, organization_id: uuid.UUID, asset_id: uuid.UUID | None) -> None:
    """default_asset_id must be an undeleted asset of THIS tenant. Without this check a tenant
    could bind its source to another tenant's asset id and (with single-asset binding) have
    telemetry attributed to it."""
    if asset_id is None:
        return
    from app.models.asset import Asset

    ok = db.execute(
        select(Asset.id).where(
            Asset.id == asset_id,
            Asset.organization_id == organization_id,
            Asset.deleted_at.is_(None),
        )
    ).first()
    if ok is None:
        # Same answer for "does not exist" and "belongs to someone else": no existence oracle.
        raise NotFoundError("default_asset_id does not reference an asset in this organization")


def create_data_source(
    db: Session, *, organization_id: uuid.UUID, payload: DataSourceCreate, created_by_user_id: uuid.UUID | None = None
) -> DataSource:
    """Registers a new data acquisition connector for the tenant.

    Raises:
        DataSourceError: If a data source with the same name already exists for the organization.
    """
    _assert_asset_in_tenant(db, organization_id, payload.default_asset_id)
    existing = db.execute(
        select(DataSource).where(
            DataSource.organization_id == organization_id,
            DataSource.name == payload.name,
        )
    ).scalar_one_or_none()
    if existing:
        raise DataSourceError(
            f"A data source named '{payload.name}' already exists for this organization."
        )

    source = DataSource(
        organization_id=organization_id,
        name=payload.name,
        description=payload.description,
        connector_type=payload.connector_type,
        connection_config=payload.connection_config or {},
        secret_reference=payload.secret_reference,
        status=DataSourceStatus.DRAFT,
        default_asset_id=payload.default_asset_id,
        metadata_json=payload.metadata_json,
    )
    db.add(source)
    db.flush()

    audit_service.record_audit_event(
        db,
        organization_id=organization_id,
        user_id=created_by_user_id,
        action="data_source.created",
        entity_type="DataSource",
        entity_id=source.id,
        metadata={
            "name": source.name,
            "connector_type": source.connector_type,
        },
    )
    log.info(
        "data_source.created",
        organization_id=str(organization_id),
        data_source_id=str(source.id),
        connector_type=source.connector_type,
    )
    return source


def get_data_source(
    db: Session, *, organization_id: uuid.UUID, data_source_id: uuid.UUID
) -> DataSource:
    """Retrieves a single data source by ID within the tenant.

    Raises:
        NotFoundError: If not found or belongs to a different tenant.
    """
    source = db.execute(
        select(DataSource).where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if not source:
        raise NotFoundError(f"DataSource {data_source_id} not found")
    return source


def list_data_sources(
    db: Session,
    *,
    organization_id: uuid.UUID,
    connector_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[DataSource]]:
    """Lists data sources for the tenant with optional filtering.

    Returns:
        (total_count, page_of_sources)
    """
    stmt = select(DataSource).where(DataSource.organization_id == organization_id)
    if connector_type:
        stmt = stmt.where(DataSource.connector_type == connector_type)
    if status:
        stmt = stmt.where(DataSource.status == status)
    stmt = stmt.order_by(DataSource.created_at.desc())

    all_rows = list(db.execute(stmt).scalars().all())
    total = len(all_rows)
    return total, all_rows[offset : offset + limit]


def update_data_source(
    db: Session,
    *,
    organization_id: uuid.UUID,
    data_source_id: uuid.UUID,
    payload: DataSourceUpdate,
    updated_by_user_id: uuid.UUID | None = None,
) -> DataSource:
    """Updates mutable fields of a data source.

    Raises:
        NotFoundError: If not found or belongs to a different tenant.
        DataSourceError: If renaming conflicts with an existing name.
    """
    source = get_data_source(db, organization_id=organization_id, data_source_id=data_source_id)

    changes: dict[str, Any] = {}

    if payload.name is not None and payload.name != source.name:
        conflict = db.execute(
            select(DataSource).where(
                DataSource.organization_id == organization_id,
                DataSource.name == payload.name,
                DataSource.id != data_source_id,
            )
        ).scalar_one_or_none()
        if conflict:
            raise DataSourceError(
                f"A data source named '{payload.name}' already exists for this organization."
            )
        changes["name"] = (source.name, payload.name)
        source.name = payload.name

    if payload.description is not None:
        source.description = payload.description
        changes["description"] = True

    if payload.connection_config is not None:
        source.connection_config = payload.connection_config
        changes["connection_config"] = True

    if payload.secret_reference is not None:
        source.secret_reference = payload.secret_reference
        changes["secret_reference"] = True

    if payload.status is not None and payload.status != source.status:
        changes["status"] = (source.status, payload.status)
        source.status = payload.status

    if payload.default_asset_id is not None:
        _assert_asset_in_tenant(db, organization_id, payload.default_asset_id)
        source.default_asset_id = payload.default_asset_id
        changes["default_asset_id"] = True

    if payload.metadata_json is not None:
        source.metadata_json = payload.metadata_json
        changes["metadata_json"] = True

    db.flush()

    if changes:
        # Stateful connectors (MAVLink sequence tracking) must not survive a reconfiguration.
        from app.services.acquisition_service import forget_connector

        forget_connector(source.id)
        audit_service.record_audit_event(
            db,
            organization_id=organization_id,
            user_id=updated_by_user_id,
            action="data_source.updated",
            entity_type="DataSource",
            entity_id=source.id,
            metadata={"changes": list(changes.keys())},
        )

    return source


def delete_data_source(
    db: Session,
    *,
    organization_id: uuid.UUID,
    data_source_id: uuid.UUID,
    deleted_by_user_id: uuid.UUID | None = None,
) -> None:
    """Permanently deletes a data source configuration.

    Note: Only DRAFT or DECOMMISSIONED sources can be deleted to prevent
    accidental deletion of active acquisition pipelines.

    Raises:
        NotFoundError: If not found or belongs to a different tenant.
        DataSourceError: If source is ACTIVE or PAUSED.
    """
    source = get_data_source(db, organization_id=organization_id, data_source_id=data_source_id)
    if source.status in (DataSourceStatus.ACTIVE, DataSourceStatus.PAUSED):
        raise DataSourceError(
            f"Cannot delete an {source.status} data source. Decommission it first."
        )

    audit_service.record_audit_event(
        db,
        organization_id=organization_id,
        user_id=deleted_by_user_id,
        action="data_source.deleted",
        entity_type="DataSource",
        entity_id=source.id,
        metadata={"name": source.name, "connector_type": source.connector_type},
    )
    from app.services.acquisition_service import forget_connector

    forget_connector(source.id)
    db.delete(source)
    db.flush()


def record_acquisition_success(
    db: Session,
    *,
    organization_id: uuid.UUID,
    data_source_id: uuid.UUID,
    events_count: int,
) -> None:
    """Atomically updates acquisition success metrics on the data source."""
    source = db.execute(
        select(DataSource).where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if source:
        source.last_acquisition_at = datetime.now(UTC)
        source.total_events_ingested += events_count
        source.consecutive_failures = 0
        db.flush()


def record_acquisition_failure(
    db: Session,
    *,
    organization_id: uuid.UUID,
    data_source_id: uuid.UUID,
    rejected_count: int = 0,
) -> None:
    """Atomically records acquisition failure and increments failure counter."""
    source = db.execute(
        select(DataSource).where(
            DataSource.id == data_source_id,
            DataSource.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if source:
        source.consecutive_failures += 1
        source.total_events_rejected += rejected_count
        db.flush()


def compute_health(source: DataSource) -> str:
    """Health label (HEALTHY | DEGRADED | FAILED | INACTIVE) derived from recorded evidence.
    The single implementation lives in acquisition_service.compute_health_detail."""
    from app.services.acquisition_service import compute_health_detail

    return compute_health_detail(source)["status"]
