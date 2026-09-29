"""Operational metrics endpoint (Prometheus text format).

Restricted to platform operators: metric names and per-route counters describe the whole deployment
and must never be readable by a tenant. Metrics carry no tenant/user/asset identifiers (see
app/core/metrics.py); those are in the structured logs.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.models.data_source import DataSource
from app.schemas.auth import CurrentUser
from app.services import acquisition_service

router = APIRouter(tags=["observability"])

_MAX_SOURCES_SCANNED = 5000


@router.get("/platform/metrics", response_class=Response)
def platform_metrics(
    db: Session = Depends(get_db_session),
    _: CurrentUser = Depends(require_permission(Permission.PLATFORM_MANAGE)),
) -> Response:
    """Prometheus text exposition. Source-health gauges are derived from recorded evidence at scrape
    time (bounded scan); everything else is a live in-process counter/histogram."""
    metrics.SOURCES_BY_HEALTH.reset()
    counts: dict[str, int] = {"HEALTHY": 0, "DEGRADED": 0, "FAILED": 0, "INACTIVE": 0}
    for source in db.execute(select(DataSource).limit(_MAX_SOURCES_SCANNED)).scalars():
        counts[acquisition_service.compute_health_detail(source)["status"]] += 1
    for status, n in counts.items():
        metrics.SOURCES_BY_HEALTH.set(n, health=status)
    return Response(content=metrics.REGISTRY.render(), media_type="text/plain; version=0.0.4; charset=utf-8")
