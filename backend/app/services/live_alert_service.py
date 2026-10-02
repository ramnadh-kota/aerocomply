"""C5: live operational rules over the C4 live state -- geofence entry/exit/proximity, low battery, telemetry loss.

Ownership: alerts are M7 `ProactiveSignalRecord`s (this module never creates a second alert store). Evaluator memory
(confirmed state, debounce candidate, episode counter) lives in `live_rule_state` and is derived data.

Called from `live_state_service.apply_event` (inside the ingest transaction, in its own savepoint: an evaluator failure
never loses the live state) and, for silence detection, from the periodic `live.telemetry_loss_sweep` job.

Decision rules (all thresholds are configuration, none is a regulatory limit):
* A position produces a geofence decision only if it is present, recent, from a 3D+ fix and has acceptable HDOP.
  Otherwise the rule state is left UNCHANGED (no entry, no exit, no clearing) and the skip is counted by reason.
* State changes need `confirm_count` consecutive reliable observations (debounce). Leaving a zone additionally needs
  `boundary_tolerance_m` of clearance (hysteresis), so GPS jitter on the boundary cannot flap alerts.
* One alert per episode. An episode ends when the condition clears; a later breach is a NEW alert (new episode).
  Breaches are never auto-resolved. Low-battery and telemetry-loss alerts are auto-resolved on recovery only if nobody
  has touched them; otherwise the operator closes them.
"""
from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.models.asset import Asset
from app.models.drone_live_state import DroneLiveState
from app.models.geofence import Geofence, LiveRuleState
from app.models.proactive_signal import ProactiveSignalRecord
from app.schemas.live_alert import ACTIVE_STATUSES, LIVE_ALERT_TYPES, LiveAlertV1
from app.services import audit_service, geo

log = structlog.get_logger(__name__)

RULE_VERSION_BATTERY = 1
RULE_VERSION_LOSS = 1
MAX_GEOFENCES_EVALUATED = 200
SWEEP_BATCH = 500
ADVISORY = "Geofence output is advisory operational information, not authoritative airspace authorisation."
_PROX_SEVERITY = {"CRITICAL": "MEDIUM", "HIGH": "MEDIUM", "MEDIUM": "LOW", "LOW": "LOW"}


# ------------------------------------------------------------------------------------------------ helpers
def _ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            d = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    return None


def _queue_event(db: Session, organization_id: uuid.UUID, signal_id: uuid.UUID, change: str) -> None:
    """Alert events reach SSE subscribers only after the transaction commits (see live_state_service)."""
    from app.services import live_state_service

    db.info.setdefault("_live_alert_events", {})[(organization_id, signal_id)] = change
    live_state_service.ensure_publish_listener(db)


def _rule_state(db: Session, organization_id: uuid.UUID, asset_id: uuid.UUID, rule_key: str,
                geofence_id: uuid.UUID | None = None) -> LiveRuleState:
    rs = db.execute(select(LiveRuleState).where(
        LiveRuleState.organization_id == organization_id, LiveRuleState.asset_id == asset_id,
        LiveRuleState.rule_key == rule_key,
    ).with_for_update()).scalar_one_or_none()
    if rs is None:
        rs = LiveRuleState(organization_id=organization_id, asset_id=asset_id, rule_key=rule_key,
                           geofence_id=geofence_id, state="UNKNOWN", candidate_count=0, active=False, episode=0)
        db.add(rs)
        db.flush()
    return rs


class _States:
    """All rule state rows of one asset, loaded (and row-locked) once per evaluation instead of once per rule."""

    def __init__(self, db: Session, organization_id: uuid.UUID, asset_id: uuid.UUID) -> None:
        self.db, self.org, self.asset_id = db, organization_id, asset_id
        self._rows = {rs.rule_key: rs for rs in db.execute(select(LiveRuleState).where(
            LiveRuleState.organization_id == organization_id, LiveRuleState.asset_id == asset_id
        ).with_for_update()).scalars()}

    def get(self, rule_key: str, geofence_id: uuid.UUID | None = None) -> LiveRuleState:
        rs = self._rows.get(rule_key)
        if rs is None:
            rs = LiveRuleState(organization_id=self.org, asset_id=self.asset_id, rule_key=rule_key,
                               geofence_id=geofence_id, state="UNKNOWN", candidate_count=0, active=False, episode=0)
            self.db.add(rs)
            self.db.flush()
            self._rows[rule_key] = rs
        return rs

    def values(self) -> list[LiveRuleState]:
        return list(self._rows.values())


def _evidence(label: str, source_type: str, source_id: str | None, metric: str | None, value: Any,
              threshold: Any, details: str) -> dict[str, Any]:
    return {"source_type": source_type, "source_id": source_id, "label": label, "metric": metric,
            "current_value": value, "threshold_value": threshold, "details": details}


def _activate(
    db: Session, rs: LiveRuleState, *, asset: Asset, signal_type: str, key_base: str, severity: str, title: str,
    headline: str, explanation: list[str], evidence: list[dict[str, Any]], factors: dict[str, Any],
    actions: list[dict[str, Any]], rule_version: int, condition: str,
) -> ProactiveSignalRecord:
    rs.episode += 1
    rs.active, rs.condition, rs.rule_version = True, condition, rule_version
    record = ProactiveSignalRecord(
        organization_id=rs.organization_id, signal_key=f"{key_base}:{asset.id}:{rs.episode}", signal_type=signal_type,
        severity=severity, priority=severity, status="OPEN", title=title, headline=headline,
        explanation_json=explanation, asset_id=asset.id, detected_at=datetime.now(UTC), evidence_json=evidence,
        contributing_factors_json={**factors, "rule_version": rule_version, "episode": rs.episode, "advisory": ADVISORY},
        recommended_actions_json=actions,
    )
    db.add(record)
    db.flush()
    rs.signal_id = record.id
    metrics.LIVE_ALERT_EVENTS.inc(alert_type=signal_type, change="raised")
    audit_service.record_audit_event(
        db, organization_id=rs.organization_id, user_id=None, action="live_alert.raised", entity_type="ProactiveSignal",
        entity_id=record.id, metadata={"alert_type": signal_type, "asset_id": str(asset.id), "episode": rs.episode,
                                       "rule_version": rule_version},
    )
    _queue_event(db, rs.organization_id, record.id, "raised")
    return record


def _update_active(db: Session, rs: LiveRuleState, *, severity: str, headline: str, evidence: list[dict[str, Any]],
                   factors: dict[str, Any], condition: str) -> None:
    rs.condition = condition
    record = db.get(ProactiveSignalRecord, rs.signal_id) if rs.signal_id else None
    if record is None or record.status not in ACTIVE_STATUSES:
        return
    record.severity = record.priority = severity
    record.headline = headline
    record.evidence_json = evidence
    record.contributing_factors_json = {**(record.contributing_factors_json or {}), **factors}
    db.flush()
    metrics.LIVE_ALERT_EVENTS.inc(alert_type=record.signal_type, change="updated")
    _queue_event(db, rs.organization_id, record.id, "updated")


def _clear(db: Session, rs: LiveRuleState, *, reason: str, auto_resolve: bool, at: datetime) -> None:
    rs.active, rs.condition = False, None
    record = db.get(ProactiveSignalRecord, rs.signal_id) if rs.signal_id else None
    if record is None or record.status not in ACTIVE_STATUSES:
        return
    record.contributing_factors_json = {
        **(record.contributing_factors_json or {}), "cleared_at": at.isoformat(), "cleared_reason": reason}
    change = "cleared"
    if auto_resolve and record.status == "OPEN":
        record.status = "RESOLVED"
        record.resolved_at = datetime.now(UTC)
        record.resolution_notes = f"Auto-resolved by the system: {reason}"
        metrics.M7_SIGNALS.inc(event="resolved", signal_type=record.signal_type)
        change = "auto_resolved"
    db.flush()
    metrics.LIVE_ALERT_EVENTS.inc(alert_type=record.signal_type, change=change)
    audit_service.record_audit_event(
        db, organization_id=rs.organization_id, user_id=None, action=f"live_alert.{change}", entity_type="ProactiveSignal",
        entity_id=record.id, metadata={"reason": reason, "status": record.status},
    )
    _queue_event(db, rs.organization_id, record.id, change)


# ------------------------------------------------------------------------------------- position quality
def position_quality(payload: dict[str, Any], reference_time: datetime) -> tuple[dict[str, Any] | None, str]:
    """(position fields, 'ok'|'unverified_fix') when usable, else (None, reason). Never guesses a missing value."""
    s = get_settings()
    pos = payload.get("position") or {}
    lat, lon = pos.get("lat"), pos.get("lon")
    if lat is None or lon is None:
        return None, "no_position"
    observed = _ts(pos.get("observed_at"))
    if observed is None or (reference_time - observed).total_seconds() > s.live_position_max_age_s:
        return None, "stale_position"
    fix = pos.get("gps_fix_type")
    if fix is not None and fix < s.live_gps_min_fix_type:
        return None, "poor_fix"
    hdop = pos.get("hdop")
    if hdop is not None and hdop > s.live_gps_max_hdop:
        return None, "poor_hdop"
    if lat == 0.0 and lon == 0.0:
        return None, "null_island"
    return pos, ("ok" if fix is not None else "unverified_fix")


def _in_window(g: Geofence, at: datetime) -> bool:
    return (g.active_from is None or at >= g.active_from) and (g.active_until is None or at < g.active_until)


# ------------------------------------------------------------------------------------------- geofences
def _evaluate_geofence(db: Session, g: Geofence, asset: Asset, pos: dict[str, Any], quality: str,
                       event_at: datetime, state_version: int, states: _States) -> None:
    aid = asset.id
    rs = states.get(f"geofence:{g.id}", g.id)
    prox = states.get(f"geofence_prox:{g.id}", g.id)
    # Ordering/dedup key is the observation time of the POSITION itself: heartbeats, attitude etc. re-evaluate the same
    # cumulative state, and an unchanged position must not count as another debounce observation.
    obs_at = _ts(pos.get("observed_at")) or event_at
    if rs.last_event_at is not None and _ts(rs.last_event_at) >= obs_at:
        metrics.LIVE_EVAL_SKIPPED.inc(reason="duplicate_or_older")
        return

    # Vertical limits: unknown altitude => no decision (never assume inside or outside).
    vertical_inside = True
    if g.alt_min_m is not None or g.alt_max_m is not None:
        alt = pos.get("alt_msl_m") if g.altitude_reference == "MSL" else pos.get("alt_rel_m")
        if alt is None:
            metrics.LIVE_EVAL_SKIPPED.inc(reason="no_altitude")
            return
        vertical_inside = (g.alt_min_m is None or alt >= g.alt_min_m) and (g.alt_max_m is None or alt <= g.alt_max_m)

    lat, lon = pos["lat"], pos["lon"]
    margin = g.proximity_buffer_m + g.boundary_tolerance_m + 1.0
    min_lat, min_lon, max_lat, max_lon = geo.bbox(g.geometry_type, g.geometry, margin)
    if not (min_lat <= lat <= max_lat and min_lon <= lon <= max_lon):
        d = 1e9  # cheap pre-filter: far outside; skips the exact distance computation
    else:
        d = geo.signed_distance_m(g.geometry_type, g.geometry, lat, lon)

    # --- confirmed geometric state with debounce + exit hysteresis
    cur = rs.state
    if cur == "INSIDE":
        desired = "OUTSIDE" if (d >= g.boundary_tolerance_m or not vertical_inside) else "INSIDE"
    else:
        desired = "INSIDE" if (d <= 0 and vertical_inside) else "OUTSIDE"
    if desired == cur:
        if rs.candidate_count:
            metrics.LIVE_ALERTS_SUPPRESSED.inc(rule="geofence_debounce")
        rs.candidate_state, rs.candidate_count = None, 0
    else:
        rs.candidate_count = rs.candidate_count + 1 if rs.candidate_state == desired else 1
        rs.candidate_state = desired
        if rs.candidate_count >= g.confirm_count:
            rs.state, rs.candidate_state, rs.candidate_count = desired, None, 0
        else:
            metrics.LIVE_ALERTS_SUPPRESSED.inc(rule="geofence_debounce")
    rs.last_event_at, rs.last_signed_distance_m = obs_at, (None if d >= 1e9 else round(d, 2))

    violation = (rs.state == "INSIDE") if g.kind != "OPERATING_AREA" else (rs.state == "OUTSIDE")
    pos_ev = {"lat": lat, "lon": lon, "alt_msl_m": pos.get("alt_msl_m"), "alt_rel_m": pos.get("alt_rel_m"),
              "gps_fix_type": pos.get("gps_fix_type"), "hdop": pos.get("hdop"), "position_quality": quality}
    base = {"live": True, "geofence_id": str(g.id), "geofence_name": g.name, "geofence_kind": g.kind,
            "geofence_version": g.version, "event_at": event_at.isoformat(), "state_version": state_version,
            "position": pos_ev, "signed_distance_m": rs.last_signed_distance_m,
            "boundary_tolerance_m": g.boundary_tolerance_m, "confirm_count": g.confirm_count,
            "altitude_reference": g.altitude_reference}
    reg = asset.registration or str(asset.id)[:8]
    ev = [
        _evidence(f"Live position of {reg}", "DroneLiveState", str(aid), "signed_distance_m", rs.last_signed_distance_m,
                  0, f"Position {lat:.6f},{lon:.6f} at {event_at.isoformat()} (state v{state_version}, quality {quality})"),
        _evidence(f"Geofence {g.name} v{g.version}", "Geofence", str(g.id), "kind", g.kind, None,
                  f"{g.geometry_type}, tolerance {g.boundary_tolerance_m:g} m, confirm {g.confirm_count}"),
    ]
    actions = [{"action_type": "MONITOR_ASSET", "title": "Review live position", "target_url": f"/drones/{aid}",
                "description": "Open the live view for this drone.", "requires_authorization": False}]

    # breach
    if violation and not rs.active:
        verb = "left its operating area" if g.kind == "OPERATING_AREA" else "entered the zone"
        _activate(
            db, rs, asset=asset, signal_type="GEOFENCE_BREACH", key_base=f"geofence_breach:{g.id}", severity=g.severity,
            title=f"Geofence {g.kind.replace('_', ' ').title()} — {g.name}",
            headline=f"{reg} {verb} \"{g.name}\".",
            explanation=[f"Reliable position reports ({g.confirm_count} consecutive) place {reg} "
                         f"{'outside' if g.kind == 'OPERATING_AREA' else 'inside'} geofence \"{g.name}\" (v{g.version}).",
                         ADVISORY],
            evidence=ev, factors=base, actions=actions, rule_version=g.version, condition="BREACH")
    elif not violation and rs.active:
        _clear(db, rs, reason="drone returned to the permitted side of the boundary", auto_resolve=False, at=event_at)

    # proximity (only while on the permitted side)
    if g.proximity_buffer_m > 0:
        safe_margin = d if g.kind != "OPERATING_AREA" else -d
        on_safe_side = not violation and rs.state != "UNKNOWN"
        in_band = on_safe_side and 0 < safe_margin <= g.proximity_buffer_m
        # Hysteresis: an active proximity alert only closes once the drone is clearly beyond the buffer (or the state
        # flipped to a confirmed violation), so one noisy fix cannot flap it.
        still_near = on_safe_side and safe_margin <= g.proximity_buffer_m + g.boundary_tolerance_m
        if in_band and not prox.active:
            prox.candidate_count += 1
            if prox.candidate_count < g.confirm_count:
                metrics.LIVE_ALERTS_SUPPRESSED.inc(rule="proximity_debounce")
            else:
                prox.candidate_count = 0
                _activate(
                    db, prox, asset=asset, signal_type="GEOFENCE_PROXIMITY", key_base=f"geofence_prox:{g.id}",
                    severity=_PROX_SEVERITY[g.severity], title=f"Approaching geofence — {g.name}",
                    headline=f"{reg} is {safe_margin:.0f} m from the boundary of \"{g.name}\".",
                    explanation=[f"Distance to the violation boundary {safe_margin:.1f} m is within the "
                                 f"{g.proximity_buffer_m:g} m proximity buffer.", ADVISORY],
                    evidence=ev, factors=base, actions=actions, rule_version=g.version, condition="PROXIMITY")
        elif not prox.active:
            prox.candidate_count = 0
        elif not still_near:
            _clear(db, prox, reason="drone moved away from the boundary" if on_safe_side else "boundary condition changed",
                   auto_resolve=True, at=obs_at)
    elif prox.active:
        _clear(db, prox, reason="proximity alerts disabled for this geofence", auto_resolve=True, at=event_at)


def _geofence_applies(g: Geofence, asset_id: uuid.UUID, at: datetime) -> bool:
    return g.is_active and (g.asset_ids is None or str(asset_id) in g.asset_ids) and _in_window(g, at)


def _evaluate_geofences(db: Session, asset: Asset, payload: dict[str, Any], event_at: datetime, state_version: int,
                        states: _States) -> None:
    fences = list(db.execute(
        select(Geofence).where(Geofence.organization_id == asset.organization_id, Geofence.is_active.is_(True))
        .order_by(Geofence.id).limit(MAX_GEOFENCES_EVALUATED)
    ).scalars())
    applicable = {g.id for g in fences if _geofence_applies(g, asset.id, event_at)}
    # Rule state of fences that stopped applying (deactivated, out of window, asset rescoped) is closed AND reset, so a
    # later reactivation starts from UNKNOWN instead of a stale INSIDE/OUTSIDE.
    for rs in states.values():
        if rs.geofence_id is None or rs.geofence_id in applicable:
            continue
        is_prox = rs.rule_key.startswith("geofence_prox:")
        if rs.active:
            _clear(db, rs, reason="geofence no longer applies (deactivated, outside its activation window or rescoped)",
                   auto_resolve=is_prox, at=event_at)
        if not is_prox and (rs.state != "UNKNOWN" or rs.candidate_count):
            rs.state, rs.candidate_state, rs.candidate_count = "UNKNOWN", None, 0
    if not applicable:
        return
    pos, quality = position_quality(payload, event_at)
    if pos is None:
        metrics.LIVE_EVAL_SKIPPED.inc(reason=quality)  # state deliberately left unchanged
        return
    for g in fences:
        if g.id in applicable:
            _evaluate_geofence(db, g, asset, pos, quality, event_at, state_version, states)


# --------------------------------------------------------------------------------------------- battery
def _evaluate_battery(db: Session, asset: Asset, payload: dict[str, Any], event_at: datetime, state_version: int,
                      states: _States) -> None:
    s = get_settings()
    b, mode = payload.get("battery") or {}, payload.get("mode") or {}
    rem, observed = b.get("remaining_pct"), _ts(b.get("observed_at"))
    if rem is None or observed is None or (event_at - observed).total_seconds() > s.live_battery_max_age_s:
        metrics.LIVE_EVAL_SKIPPED.inc(reason="battery_unavailable")
        return
    rs = states.get("low_battery")
    if rs.last_event_at is not None and _ts(rs.last_event_at) >= observed:
        return  # same battery observation already evaluated (other messages re-deliver the cumulative state)
    if s.live_low_battery_only_when_armed and mode.get("armed") is not True:
        return  # not flying: a low pack on the ground is not an in-flight alert (and an active alert is kept as is)
    rs.last_event_at = observed
    level = ("CRITICAL" if rem <= s.live_low_battery_critical_pct
             else "WARNING" if rem <= s.live_low_battery_warning_pct else None)
    reg = asset.registration or str(asset.id)[:8]
    threshold = s.live_low_battery_critical_pct if level == "CRITICAL" else s.live_low_battery_warning_pct
    severity = "CRITICAL" if level == "CRITICAL" else "MEDIUM"
    ev = [_evidence(f"Battery of {reg}", "DroneLiveState", str(asset.id), "battery_remaining_pct", rem, threshold,
                    f"Reported at {observed.isoformat()} (state v{state_version}); voltage {b.get('voltage_v')} V")]
    factors = {"live": True, "event_at": event_at.isoformat(), "state_version": state_version, "remaining_pct": rem,
               "voltage_v": b.get("voltage_v"), "level": level, "warning_pct": s.live_low_battery_warning_pct,
               "critical_pct": s.live_low_battery_critical_pct, "armed": mode.get("armed")}
    if level is None:
        rs.candidate_state, rs.candidate_count = None, 0
        if rs.active and rem >= s.live_low_battery_warning_pct + s.live_low_battery_clear_margin_pct:
            _clear(db, rs, reason=f"battery recovered to {rem}%", auto_resolve=True, at=event_at)
        return
    if not rs.active:
        rs.candidate_count = rs.candidate_count + 1 if rs.candidate_state == level or rs.candidate_state == "LOW" else 1
        rs.candidate_state = "LOW"
        if rs.candidate_count < s.live_low_battery_confirm:
            metrics.LIVE_ALERTS_SUPPRESSED.inc(rule="battery_debounce")
            return
        rs.candidate_state, rs.candidate_count = None, 0
        _activate(
            db, rs, asset=asset, signal_type="LIVE_LOW_BATTERY", key_base="live_low_battery", severity=severity,
            title=f"{'Critical' if level == 'CRITICAL' else 'Low'} battery — {reg}",
            headline=f"{reg} reports {rem}% battery remaining (threshold {threshold}%).",
            explanation=[f"Battery remaining {rem}% is at or below the configured {level.lower()} threshold of "
                         f"{threshold}%.", "Thresholds are deployment settings, not aircraft limits."],
            evidence=ev, factors=factors,
            actions=[{"action_type": "MONITOR_ASSET", "title": "Review live status", "target_url": f"/drones/{asset.id}",
                      "description": "Open the live view for this drone.", "requires_authorization": False}],
            rule_version=RULE_VERSION_BATTERY, condition=level)
    elif level == "CRITICAL" and rs.condition != "CRITICAL":
        _update_active(db, rs, severity="CRITICAL", condition="CRITICAL", evidence=ev, factors=factors,
                       headline=f"{reg} battery is critical: {rem}% remaining (threshold {threshold}%).")


# ------------------------------------------------------------------------------------ telemetry loss
def sweep_telemetry_loss(db: Session, *, organization_id: uuid.UUID | None = None, now: datetime | None = None) -> dict[str, int]:
    """Raise LIVE_TELEMETRY_LOSS for drones that were ARMED at their last report and have been silent longer than
    `live_telemetry_loss_seconds`. A drone that was disarmed/unknown when it went quiet is simply offline, not an
    operational alert. Idempotent: one alert per silence episode (the rule state is locked per asset)."""
    s = get_settings()
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(seconds=s.live_telemetry_loss_seconds)
    q = select(DroneLiveState).where(
        DroneLiveState.last_received_at < cutoff, DroneLiveState.payload["mode"]["armed"].astext == "true")
    if organization_id is not None:
        q = q.where(DroneLiveState.organization_id == organization_id)
    rows = list(db.execute(q.order_by(DroneLiveState.last_received_at).limit(SWEEP_BATCH)).scalars())
    raised = 0
    for row in rows:
        asset = db.get(Asset, row.asset_id)
        if asset is None or asset.deleted_at is not None:
            continue
        rs = _rule_state(db, row.organization_id, row.asset_id, "telemetry_loss")
        if rs.active:
            continue
        silent = (now - row.last_received_at).total_seconds()
        reg = asset.registration or str(asset.id)[:8]
        pos = (row.payload or {}).get("position") or {}
        _activate(
            db, rs, asset=asset, signal_type="LIVE_TELEMETRY_LOSS", key_base="live_telemetry_loss", severity="HIGH",
            title=f"Telemetry lost while armed — {reg}",
            headline=f"No telemetry from {reg} for {silent:.0f} s; it was armed at its last report.",
            explanation=[f"Last report received {row.last_received_at.isoformat()}; the loss threshold is "
                         f"{s.live_telemetry_loss_seconds:g} s.",
                         "Loss of telemetry does not mean the aircraft has failed; the link, companion computer or "
                         "ingest path may be down."],
            evidence=[_evidence(f"Last live state of {reg}", "DroneLiveState", str(asset.id), "seconds_since_last_report",
                                round(silent, 1), s.live_telemetry_loss_seconds,
                                f"state v{row.state_version}; last position "
                                f"{pos.get('lat')},{pos.get('lon')}")],
            factors={"live": True, "last_received_at": row.last_received_at.isoformat(), "state_version": row.state_version,
                     "last_position": {k: pos.get(k) for k in ("lat", "lon", "alt_msl_m", "alt_rel_m")},
                     "last_battery_pct": ((row.payload or {}).get("battery") or {}).get("remaining_pct")},
            actions=[{"action_type": "MONITOR_ASSET", "title": "Verify telemetry link", "target_url": f"/drones/{asset.id}",
                      "description": "Check the companion computer, link and ingest status.", "requires_authorization": False}],
            rule_version=RULE_VERSION_LOSS, condition="LOSS")
        raised += 1
    return {"candidates": len(rows), "raised": raised}


# ---------------------------------------------------------------------------------------- entry point
def evaluate_live_state(
    db: Session, *, organization_id: uuid.UUID, asset_id: uuid.UUID, payload: dict[str, Any], event_at: datetime,
    state_version: int,
) -> None:
    """Evaluate every live rule for one applied live-state update. Caller wraps this in a savepoint."""
    t0 = time.perf_counter()
    try:
        asset = db.execute(select(Asset).where(Asset.id == asset_id, Asset.organization_id == organization_id)
                           ).scalar_one_or_none()
        if asset is None:
            return
        states = _States(db, organization_id, asset_id)
        loss = states._rows.get("telemetry_loss")
        if loss is not None and loss.active:
            _clear(db, loss, reason="telemetry resumed", auto_resolve=True, at=event_at)
        _evaluate_battery(db, asset, payload, event_at, state_version, states)
        _evaluate_geofences(db, asset, payload, event_at, state_version, states)
    finally:
        metrics.LIVE_EVAL_LATENCY.observe(time.perf_counter() - t0)


# ------------------------------------------------------------------------------------------ read API
def to_alert(record: ProactiveSignalRecord, registration: str | None = None) -> LiveAlertV1:
    f = record.contributing_factors_json or {}
    cleared_at = _ts(f.get("cleared_at"))
    gid = f.get("geofence_id")
    return LiveAlertV1(
        id=record.id, alert_type=record.signal_type, severity=record.severity, status=record.status,
        condition_active=cleared_at is None, asset_id=record.asset_id, asset_registration=registration,
        geofence_id=uuid.UUID(gid) if gid else None, title=record.title, headline=record.headline,
        explanation=record.explanation_json or [], detected_at=record.detected_at, cleared_at=cleared_at,
        cleared_reason=f.get("cleared_reason"),
        rule={"name": record.signal_type, "rule_version": f.get("rule_version"), "episode": f.get("episode")},
        evidence=record.evidence_json or [],
        provenance={k: f.get(k) for k in ("event_at", "state_version", "position", "signed_distance_m", "remaining_pct",
                                          "last_received_at", "geofence_version", "geofence_kind") if k in f},
        acknowledged_by_user_id=record.acknowledged_by_user_id, acknowledged_at=record.acknowledged_at,
        resolved_by_user_id=record.resolved_by_user_id, resolved_at=record.resolved_at,
        resolution_notes=record.resolution_notes, dismissed_at=record.dismissed_at,
        dismissal_reason=record.dismissal_reason, reopen_count=int(f.get("reopen_count", 0)),
    )


def _registrations(db: Session, organization_id: uuid.UUID, asset_ids: set[uuid.UUID]) -> dict[uuid.UUID, str | None]:
    if not asset_ids:
        return {}
    return {a.id: a.registration for a in db.execute(
        select(Asset).where(Asset.organization_id == organization_id, Asset.id.in_(asset_ids))).scalars()}


def list_alerts(
    db: Session, *, organization_id: uuid.UUID, active_only: bool = True, asset_id: uuid.UUID | None = None,
    alert_type: str | None = None, status: str | None = None, limit: int = 200,
) -> list[LiveAlertV1]:
    q = select(ProactiveSignalRecord).where(
        ProactiveSignalRecord.organization_id == organization_id, ProactiveSignalRecord.signal_type.in_(LIVE_ALERT_TYPES))
    if status:
        q = q.where(ProactiveSignalRecord.status == status)
    elif active_only:
        q = q.where(ProactiveSignalRecord.status.in_(ACTIVE_STATUSES))
    if asset_id:
        q = q.where(ProactiveSignalRecord.asset_id == asset_id)
    if alert_type:
        q = q.where(ProactiveSignalRecord.signal_type == alert_type)
    rows = list(db.execute(q.order_by(ProactiveSignalRecord.detected_at.desc()).limit(max(1, min(limit, 500)))).scalars())
    regs = _registrations(db, organization_id, {r.asset_id for r in rows if r.asset_id})
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    rows.sort(key=lambda r: (rank.get(r.severity, 9), -r.detected_at.timestamp()))
    return [to_alert(r, regs.get(r.asset_id)) for r in rows]


def get_alert(db: Session, *, organization_id: uuid.UUID, signal_id: uuid.UUID) -> LiveAlertV1:
    r = db.execute(select(ProactiveSignalRecord).where(
        ProactiveSignalRecord.id == signal_id, ProactiveSignalRecord.organization_id == organization_id,
        ProactiveSignalRecord.signal_type.in_(LIVE_ALERT_TYPES))).scalar_one_or_none()
    if r is None:
        raise NotFoundError("Alert not found", code="alert_not_found")
    return to_alert(r, _registrations(db, organization_id, {r.asset_id} if r.asset_id else set()).get(r.asset_id))


def act_on_alert(db: Session, *, organization_id: uuid.UUID, signal_id: uuid.UUID, user_id: uuid.UUID, action: str,
                 notes: str | None) -> LiveAlertV1:
    """Lifecycle (acknowledge / in_review / resolve / dismiss / reopen) is owned by M7; this only guards that the
    signal is a live alert and queues the SSE event."""
    from app.services.intelligence import proactive_intelligence_service as m7

    get_alert(db, organization_id=organization_id, signal_id=signal_id)  # 404 for foreign or non-live signals
    record = m7.transition_signal(db, organization_id=organization_id, signal_id=signal_id, user_id=user_id,
                                  action=action, notes=notes)
    change = {"acknowledge": "acknowledged", "in_review": "in_review", "resolve": "resolved", "dismiss": "dismissed",
              "reopen": "reopened"}[action]
    metrics.LIVE_ALERT_EVENTS.inc(alert_type=record.signal_type, change=change)
    _queue_event(db, organization_id, signal_id, change)
    return get_alert(db, organization_id=organization_id, signal_id=signal_id)
