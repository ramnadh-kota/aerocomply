# C6 — LISA Live-Operations Tools: Dependency Map (planning only, nothing implemented)

C6 starts only after C5 is verified. Scope stays **read-only**: LISA answers questions about live drones; it never
commands, arms, re-routes or acknowledges anything on a user's behalf.

## 1. What exists today (verified in the repository)

| Piece | Location | Relevance |
|---|---|---|
| Tool registry | `backend/app/services/ai/tools.py` — `ToolSpec(name, description, input_schema, handler, required_permission, required_feature, required_suite)`, ~55 tools | New tools register here; every tool must map to the same permission as its REST twin |
| Tool execution + guard rails | `ai/agent_service.py`, `_require_permission`, `_require_entitlement`, `metrics.LISA_TOOL_*` | Reused as is (latency/error metrics included) |
| Deterministic investigations | `lisa/orchestration_service.py` (`Intent` → `_investigate_*`, `_CallBudget.call(tool, args)`) | `Intent.TELEMETRY_HUMS` already answers "telemetry status of this drone"; there is **no live-operations intent** |
| Intent / entity / context resolution | `lisa/intent_service.py`, `entity_resolution_service.py`, `context_service.py` | Entity types "aircraft"/"drone" resolve to an asset id already |
| Existing, reusable tools | `get_asset_telemetry_status` (DRONE_READ + `flight_telemetry`), `get_asset_proactive_signals`, `get_proactive_alerts`, `get_fleet_attention_summary`, `list_fleet_assets`, `get_control_center_fleet`, `get_asset_hums_health`, `get_daily_brief`, `get_asset_operational_impact` | Answer *historical/HUMS/compliance* questions; they know nothing of C4 live state, geofences or C5 alerts |
| C4/C5 services to wrap | `live_state_service.get_fleet_state / get_drone_state`, `live_alert_service.list_alerts / get_alert`, `geofence_service.list_geofences / get_geofence / list_versions` | Already tenant-scoped by `organization_id`; handlers pass `user.organization_id` only |

## 2. Required new LISA tools (all read-only; permission `DRONE_READ`, feature `flight_telemetry`)

| Tool | Backed by | Notes |
|---|---|---|
| `get_live_fleet_state` (filters: freshness, armed, limit) | `live_state_service.get_fleet_state` | Must return freshness + connectivity per drone; never imply health from absence of data |
| `get_drone_live_state(asset_id)` | `get_drone_state` | Position/battery/mode/mission groups with per-group `observed_at`; `null` ≠ 0 |
| `list_live_alerts(status, alert_type, asset_id, limit)` | `live_alert_service.list_alerts` | Includes `condition_active`, cleared reason, rule version, episode |
| `get_live_alert(alert_id)` | `live_alert_service.get_alert` | Evidence + provenance for "why did this fire" |
| `list_geofences(include_inactive)` / `get_geofence(id)` | `geofence_service` | Advisory zones; tool text must repeat "not airspace authorisation" |
| `get_drone_geofence_status(asset_id)` | **new** read function over `live_rule_state` (+ `geofences`) | Confirmed INSIDE/OUTSIDE/UNKNOWN, last signed distance, active episode per fence |
| `get_mission_progress(asset_id)` | live `mission` group + `mission_service` (planned missions) | **Gap:** nothing maps MAVLink `MISSION_CURRENT.seq` to a planned `Mission` item; needs a defined binding first (or the tool reports live sequence only) |
| `get_recent_status_texts(asset_id, limit)` | live `status_texts` | Firmware free text: return flagged `untrusted: true`; the tool description must forbid following instructions in it (prompt-injection) |

## 3. Required analytics services (new, deterministic, labelled as estimates)

| Service | Input | Preconditions / honesty rules |
|---|---|---|
| Battery trend / reserve estimate | `battery.remaining_pct` history | **Gap:** C4 stores only the *latest* state. History is available only as `NormalizedTelemetryEvent` metadata (`telemetry_event_logs.metadata_payload.live_state`) — needs a bounded query/index and a retention check. Return "insufficient data" below N samples / fresh window; never a remaining-flight-time claim without a validated model |
| Track / distance-to-fence summary | position history + geofences (`services/geo.py`) | Same history dependency; reuse `geo.signed_distance_m` |
| Alert/episode summary per drone/day | `proactive_signal_records` (live types) | No new storage |

## 4. Orchestration and safety changes

1. Add `Intent.LIVE_OPERATIONS` (+ keyword rules in `intent_service`) and `_investigate_live_operations` that calls the
   tools above through `_CallBudget`; keep `TELEMETRY_HUMS` for historical/HUMS questions and route by wording.
2. Answers must state data age ("last position 4 s ago"), freshness class, and say **LOST/NO_DATA ≠ failed or healthy**.
3. Geofence answers carry the advisory disclaimer; alert answers cite alert id, rule version and evidence.
4. LISA offers no action tools. Acknowledging/resolving alerts stays a UI action by an authorised user.
5. Treat all `status_texts` and geofence/alert free text as data, not instructions.

## 5. Evals and tests needed

* Tool unit tests (permission, entitlement, **cross-tenant 404**, `null` handling) in the pattern of the existing tool tests.
* Orchestration tests: stale drone, never-reported drone, active breach, cleared-but-unacknowledged breach, loss alert.
* Prompt-injection eval: a STATUSTEXT such as "ignore previous instructions…" must appear only as quoted, untrusted data.
* Contract test that the tool outputs stay in sync with `kota.drone.live_state.v1` / `kota.drone.live_alert.v1`.

## 6. Order of work for C6

1. `get_drone_geofence_status` read service (small) → 2. live tools (§2, excluding mission) → 3. intent + orchestration →
4. history query for analytics (decide storage/retention) → 5. battery/track analytics → 6. mission binding (needs a product decision) → 7. evals.
