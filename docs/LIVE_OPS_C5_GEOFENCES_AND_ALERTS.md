# Live Drone Operations — C5 Geofences and Operational Alerts

Read-only operations. Nothing here sends a command to an aircraft. Geofence output is **advisory operational
information configured by the organization — never authoritative airspace authorisation.**

## 1. Architecture (what is reused, what is new)

| Concern | Owner | Notes |
|---|---|---|
| Alert record + lifecycle | **M7** `proactive_signal_records` | No second alert table. Four signal types added: `GEOFENCE_BREACH`, `GEOFENCE_PROXIMITY`, `LIVE_LOW_BATTERY`, `LIVE_TELEMETRY_LOSS` |
| Lifecycle transitions | `proactive_intelligence_service.transition_signal` | One state machine incl. **reopen**; existing M7 endpoints unchanged |
| Live data | C4 `drone_live_state` via `live_state_service.apply_event` | Rules run in the ingest transaction, in their own savepoint |
| Geofence configuration | `geofences`, `geofence_versions` (migration 0072) | Tenant-scoped, versioned, audited |
| Evaluator memory | `live_rule_state` (0072) | Derived/rebuildable: confirmed state, debounce candidate, episode, signal link |
| Telemetry loss | `live.telemetry_loss_sweep` job (60 s) | Silence cannot be detected by events |
| Streaming | C4 SSE broker | New `alert` events; `alerts` in the snapshot |

`TELEMETRY_FRESHNESS` (M13, **days**-scale stale HUMS data) is unchanged and distinct from `LIVE_TELEMETRY_LOSS`
(**seconds**-scale, armed drone went silent). Low-battery and telemetry-loss had no existing owner for live data.

## 2. Geofence domain

* `kind`: `RESTRICTED` / `CAUTION` (entering is the violation), `OPERATING_AREA` (leaving is the violation).
* `geometry_type`: `CIRCLE {center:{lat,lon}, radius_m}` or `POLYGON {ring:[[lon,lat],…]}` (WGS84, GeoJSON order).
  Validation: lat ±85°, lon ±180°, radius 1 m–100 km, 3–500 vertices, no repeated vertices, no self-intersection, non-zero
  area, extent ≤ 100 km. Antimeridian and polar fences are refused, not approximated.
* Altitude: optional `alt_min_m`/`alt_max_m` with `altitude_reference` = `HOME_RELATIVE` (relative to take-off, **not AGL**)
  or `MSL`. If a limit exists and the altitude was never reported the rule makes **no decision**.
* `proximity_buffer_m` (0 = off), `boundary_tolerance_m` (exit hysteresis), `confirm_count` (1–10 consecutive updates),
  `severity`, optional `asset_ids` (null = all drones), `active_from/until` (tz-aware), `is_active`.
* Zones are never deleted: `POST /geofences/{id}/deactivate`. Each change bumps `version`, writes an immutable
  `geofence_versions` snapshot and an `audit_events` row (`geofence.created|updated|deactivated|reactivated`).
* Limits: 200 geofences per organization.

## 3. Evaluation rules

1. A position is used only if present, newer than `live_position_max_age_s` (15 s), from a fix ≥ 3D, HDOP ≤ 5, not 0/0.
   If the fix type was never reported (no GPS_RAW_INT) the decision is made but evidence says `unverified_fix`.
   Otherwise the rule state is **unchanged** (no entry, no exit, no clearing) and `kota_live_evaluation_skipped_total{reason}` counts it.
2. Debounce: `confirm_count` consecutive position observations to change state (initial state included).
   An observation is a distinct position update (keyed on the position group's own timestamp); heartbeats and attitude
   frames that re-deliver the same cumulative state are not observations.
3. Hysteresis: entering needs signed distance ≤ 0; leaving needs ≥ `boundary_tolerance_m` clearance. Proximity closes only
   when the drone is beyond buffer + tolerance.
4. Episodes: one alert per episode. After the condition clears, a later breach is a **new** alert. Breaches are never
   auto-resolved; the operator closes them. Proximity, low-battery and telemetry-loss alerts auto-resolve on recovery
   **only if still OPEN** (untouched).
5. Fence deactivated / outside its window / drone out of scope → open breach condition is closed ("no longer applies")
   and the state resets to UNKNOWN (a reactivation never inherits a stale INSIDE).
6. Cost per update: one query for the org's active fences (≤ 200), bbox pre-filter, exact distance only near a fence;
   all rule-state rows loaded once per asset and row-locked.

Low battery: armed drones only (setting), warning ≤ 25 % (MEDIUM), critical ≤ 15 % (CRITICAL, escalated in place),
2 consecutive readings, clears at ≥ 30 %. Telemetry loss: armed at last report and silent > 60 s (HIGH). All thresholds
are `Settings.live_*` deployment defaults — **not aircraft or regulatory limits**.

## 4. API

| Endpoint | Permission | Notes |
|---|---|---|
| `GET/POST /geofences`, `GET/PATCH /geofences/{id}`, `POST /geofences/{id}/deactivate`, `GET /geofences/{id}/history` | `DRONE_READ` / `DRONE_WRITE` + `flight_telemetry` | tenant from JWT; `organization_id` in a body is rejected (422) |
| `GET /live/alerts?status=&alert_type=&asset_id=&include_closed=&limit=` | `DRONE_READ` | default: active (OPEN/ACKNOWLEDGED/IN_REVIEW) |
| `GET /live/alerts/{id}` | `DRONE_READ` | foreign / non-live ids → 404 |
| `POST /live/alerts/{id}/acknowledge \| in-review \| resolve \| dismiss \| reopen` | `DRONE_WRITE` | `resolve`/`dismiss` need `notes`; illegal transitions → 409 |
| `GET /live/fleet` | `DRONE_READ` | now includes `alerts` |
| `GET /live/stream` (SSE) | `DRONE_READ` | `snapshot` includes `alerts`; new `alert` event |

Alert object `kota.drone.live_alert.v1`: `id, alert_type, severity, status, condition_active, asset_id, geofence_id, title,
headline, explanation[], detected_at, cleared_at, cleared_reason, rule{name, rule_version, episode}, evidence[],
provenance{event_at, state_version, position{…, position_quality}, signed_distance_m, geofence_version…}, lifecycle fields,
reopen_count, advisory`. SSE `alert` data: `{"change": raised|updated|cleared|auto_resolved|acknowledged|in_review|resolved|dismissed|reopened, "alert": {…}}`.
Events are published only after the DB transaction commits and are dropped if it rolls back.

## 5. Observability

`kota_live_evaluation_duration_seconds`, `kota_live_evaluation_failures_total`, `kota_live_evaluation_skipped_total{reason}`
(`duplicate_or_older`, `stale_position`, `poor_fix`, `poor_hdop`, `no_position`, `null_island`, `no_altitude`,
`battery_unavailable`), `kota_live_alert_events_total{alert_type,change}`, `kota_live_alerts_suppressed_total{rule}`
(debounce suppression). Structured logs: `live.evaluation_failed`, `live.publish_failed`, `live.alert_publish_failed`.

## 6. Known limitations (do not overstate)

* **SSE broker is per process** (C4). The replay window is in memory (500 events/tenant); after a restart or on another
  worker the cursor is rejected and the client must re-read the snapshot (`/live/fleet` or the SSE `snapshot`).
  There is **no distributed replay guarantee**.
* Alerts raised in a **different process** than the one serving a client's stream (the worker-run telemetry-loss sweep,
  UDP/TCP listener processes) are **not pushed** over that client's SSE; they appear in `/live/alerts`, in the next
  snapshot/reconnect and on polling. A cross-process fan-out (e.g. Redis pub/sub) is not implemented.
* Telemetry loss is detected by a 60 s job: latency is the loss threshold plus up to one job period.
* Position uncertainty is modelled only by the fix-type / HDOP gate and `boundary_tolerance_m`; no covariance is used.
* Home-relative altitude is relative to the take-off point, not terrain.
* Geofences are not synchronised to the vehicle and there is no in-flight enforcement.
* Concurrent first events for a brand-new asset can race on creating rule-state rows; the loser's evaluation is lost
  (logged `live.evaluation_failed`) while its live state is kept.
* Post-commit SSE publication is not exercised by the automated tests (the test session cannot be committed); the
  queue/after-commit wiring is verified by code review only.
