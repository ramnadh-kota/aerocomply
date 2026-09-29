"""H3: Persists/retrieves HUMSBaseline rows.

Baselines are recomputed lazily and cached: `get_or_compute_baseline`
returns the current version if it exists and isn't stale, otherwise
computes a fresh one from bounded recent HUMSFeature history and versions
it. This avoids the "recompute the entire historical dataset on every API
request" anti-pattern the H3 spec warns against — a request for an asset's
health touches at most one bounded query per (sensor, feature_type) plus
whatever baseline row already exists.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.hums import HUMSBaseline, HUMSFeature, HUMSSensor
from app.services.hums.baseline_engine import compute_baseline_stats

# A baseline older than this is considered STALE and eligible for
# recomputation on next access -- not a regulatory/engineering constant,
# just a reasonable "don't trust year-old statistics forever" default.
BASELINE_STALE_AFTER = datetime.timedelta(days=30)

# How much feature history to pull when (re)computing a baseline. Bounded
# so this never turns into an unbounded table scan as history grows.
BASELINE_HISTORY_LIMIT = 200


def get_current_baseline(db: Session, *, organization_id: uuid.UUID, sensor_id: uuid.UUID, feature_type: str) -> HUMSBaseline | None:
    return db.execute(
        select(HUMSBaseline).where(
            HUMSBaseline.organization_id == organization_id,
            HUMSBaseline.sensor_id == sensor_id,
            HUMSBaseline.feature_type == feature_type,
            HUMSBaseline.is_current.is_(True),
        )
    ).scalar_one_or_none()


def _is_stale(baseline: HUMSBaseline) -> bool:
    now = datetime.datetime.now(datetime.UTC)
    created = baseline.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=datetime.UTC)
    return (now - created) > BASELINE_STALE_AFTER


def get_or_compute_baseline(
    db: Session,
    *,
    organization_id: uuid.UUID,
    sensor: HUMSSensor,
    feature_type: str,
    force_recompute: bool = False,
    history_override: list[HUMSFeature] | None = None,
) -> HUMSBaseline | None:
    """Returns the current baseline for (sensor, feature_type), recomputing
    it if missing, stale, or `force_recompute` is set. Returns None if
    there isn't enough GOOD-quality feature history to establish one —
    callers must treat that as INSUFFICIENT_DATA, never fabricate a range.

    `history_override`: when evaluating deviation for a specific "current"
    observation (health_service.evaluate_feature_health), the caller passes
    the feature history EXCLUDING that observation — a baseline must
    represent prior expected behavior, never absorb the very value it is
    about to be compared against (otherwise an anomaly widens its own
    "normal" range and can never be detected). Standalone baseline
    endpoints (no single "current" observation in question) omit this and
    the full recent history is used instead.
    """
    existing = get_current_baseline(db, organization_id=organization_id, sensor_id=sensor.id, feature_type=feature_type)
    if existing and not force_recompute and not _is_stale(existing) and history_override is None:
        return existing

    if history_override is not None:
        history = history_override
    else:
        history = list(
            db.execute(
                select(HUMSFeature)
                .where(
                    HUMSFeature.organization_id == organization_id,
                    HUMSFeature.sensor_id == sensor.id,
                    HUMSFeature.feature_type == feature_type,
                    HUMSFeature.quality.in_(("GOOD", "DEGRADED")),
                )
                .order_by(HUMSFeature.window_end.desc())
                .limit(BASELINE_HISTORY_LIMIT)
            )
            .scalars()
            .all()
        )
    if not history:
        return existing  # nothing new to compute from; keep whatever (possibly stale) baseline exists, or None

    values = [h.value for h in history]  # order doesn't matter -- compute_baseline_stats sorts internally
    stats = compute_baseline_stats(values)
    if stats is None:
        return existing

    next_version = (existing.version + 1) if existing else 1
    if existing:
        existing.is_current = False

    baseline = HUMSBaseline(
        organization_id=organization_id,
        asset_id=sensor.asset_id,
        component_id=sensor.component_id,
        sensor_id=sensor.id,
        feature_type=feature_type,
        baseline_scope="ASSET",
        sample_count=stats.sample_count,
        mean=stats.mean,
        median=stats.median,
        std_dev=stats.std_dev,
        minimum=stats.minimum,
        maximum=stats.maximum,
        percentile_05=stats.percentile_05,
        percentile_25=stats.percentile_25,
        percentile_50=stats.percentile_50,
        percentile_75=stats.percentile_75,
        percentile_95=stats.percentile_95,
        lower_bound=stats.lower_bound,
        upper_bound=stats.upper_bound,
        calculation_method=stats.calculation_method,
        source_window_start=min(h.window_start for h in history),
        source_window_end=max(h.window_end for h in history),
        version=next_version,
        is_current=True,
        quality=stats.quality,
        confidence=stats.confidence,
        context_notes="No RPM/flight-phase/operating-context segmentation available — asset-wide baseline only." if sensor.component_id is None else None,
    )
    db.add(baseline)
    db.flush()
    return baseline


def list_asset_baselines(db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID) -> list[HUMSBaseline]:
    return list(
        db.execute(
            select(HUMSBaseline).where(
                HUMSBaseline.organization_id == organization_id,
                HUMSBaseline.asset_id == asset_id,
                HUMSBaseline.is_current.is_(True),
            )
        )
        .scalars()
        .all()
    )


__all__ = ["get_current_baseline", "get_or_compute_baseline", "list_asset_baselines", "BASELINE_STALE_AFTER", "BASELINE_HISTORY_LIMIT"]
