# KOTA AEROSPACE — Developer 1 → Developer 2 Domain Event Contract

Digital Operations (Developer 1) publishes operational facts. Compliance / Evidence / Readiness / AI Intelligence (Developer 2) consumes them to reason about compliance and readiness. Developer 1 never implements that reasoning; it only guarantees these facts are accurate, timely, and tenant-scoped.

## Current transport: the audit log, not a message bus

There is no separate event-bus/pub-sub system in this codebase today, and this contract does not introduce one. Every mutation in the domains below already writes an [`AuditEvent`](backend/app/models/audit_event.py) row via `app.services.audit_service.record_audit_event(...)` — immutable (enforced by a DB trigger, migration `0002_audit_events_immutability.py`), tenant-scoped (`organization_id`), and queryable by `entity_type`/`entity_id`/`action`.

**Developer 2 should consume domain events by querying `AuditEvent` filtered by `action`**, not by standing up a new subscriber. This is the cheapest path that satisfies the milestone's actual goal — reliable, replayable operational facts — without duplicating a second source of truth. If a future need (real-time push, cross-service fan-out) outgrows polling `AuditEvent`, that is a deliberate follow-up decision, not something to build speculatively now.

Every `AuditEvent` row has this shape:

```
organization_id   uuid   — tenant scope (never trust a caller-supplied org id instead)
user_id           uuid | null   — actor, null for system-initiated events
action            str    — dotted event name, see table below
entity_type       str    — e.g. "WorkOrder", "Mission", "Finding"
entity_id         uuid   — the entity's id
metadata          jsonb  — action-specific payload (see per-event notes)
created_at        timestamptz — event timestamp
```

There is no separate `correlation_id` column today. Where one event is caused by another within the same request (e.g. a Finding created from a completed inspection), the causing entity's id is included in `metadata` — see per-event notes below. Developer 2 should correlate via `metadata` fields and `entity_id` chains rather than expect a dedicated correlation column; adding one is a candidate follow-up if cross-event stitching proves painful in practice.

## Event catalog

| Event (`action`) | Producer (service) | `entity_type` / `entity_id` | Key `metadata` fields | Consumer use |
|---|---|---|---|---|
| `mission.created` | mission_service.create_mission | Mission | `asset_id`, `status` | Readiness: asset now has an active mission |
| `mission.updated` | mission_service.update_mission | Mission | `status` | Track mission state changes |
| `mission.authorized` | mission_service.authorize_mission | Mission | `status` | Flight-execution clearance recorded |
| `finding.created` | finding_service | Finding | asset/aircraft/component linkage | Evidence intelligence: new defect surfaced |
| `finding.disposition_added` | finding_service | Finding | `disposition_type` | Corrective-action tracking |
| `finding.closed` | finding_service | Finding | — | Finding resolved, asset defect cleared |
| `work_order.created` | work_order_service.create_work_order | WorkOrder | `asset_id`, `status`, `work_order_type` | Readiness: open maintenance work exists |
| `work_order.updated` | work_order_service.update_work_order | WorkOrder | changed fields | General field edits |
| `work_order.assigned` | work_order_service.assign_work_order | WorkOrder | `assigned_to_user_id` | Technician workload tracking |
| `work_order.transitioned` | work_order_service.transition_work_order | WorkOrder | `from_status`, `to_status` (covers IN_PROGRESS→INSPECTION, INSPECTION→COMPLETED, COMPLETED→CLOSED, and CANCELLED) | State-machine progress, TAT input, feeds release readiness |
| `task.created` / `task.updated` / `task.completed` | work_order_service (create_task/update_task/complete_task) | Task | `work_order_id`, `execution_state` | Task-gate progress for IN_PROGRESS→INSPECTION gate |
| `battery.installed` / `battery.removed` | installation_service | Battery | `asset_id` | Configuration snapshot changes |
| `component.installed` / `component.removed` | installation_service | Component | `asset_id` | Configuration snapshot changes |
| `inspection.completed` / `inspection.rejected` / `inspection.marked_not_required` / `inspection.reopened` | inspection_service | InspectionRequirement | `rejection_reason` (on reject) | RII/checklist state for readiness, gates INSPECTION→COMPLETED |

Verified directly against `action="..."` call sites in `work_order_service.py`, `installation_service.py`, and `inspection_service.py` — these are the real strings in the codebase today, not aspirational names. `mission.*` and `finding.*` rows above are likewise taken from `mission_service.py`/`finding_service.py` call sites.

## What Developer 2 should NOT expect

- No push/webhook delivery — polling `AuditEvent` (e.g. `WHERE organization_id = ? AND created_at > ? ORDER BY created_at`) is the intended consumption pattern.
- No cross-tenant visibility — every query must filter by `organization_id`; there is no global event stream.
- No guaranteed `correlation_id` — correlate via `metadata` and `entity_id` until/unless this contract is revised.
- No compliance/readiness computation — Developer 1 publishes facts (asset status, open work order count, mission state); Developer 2 owns turning those into a readiness verdict.

## Example: computing readiness inputs from existing facts (illustrative, not new code)

```
asset_status = Asset.status                                  # Developer 1 fact
open_work_orders = count(WorkOrder where asset_id=X 
                          and status not in (CLOSED, CANCELLED))
active_mission = Mission where asset_id=X and status in (PLANNED, AUTHORIZED, IN_PROGRESS)
inspection_required = InspectionRequirement where ... status = PENDING
```

Developer 2's `readiness` reasoning combines these into `READY` / `NOT_READY` — this file only guarantees the inputs are correct and queryable.
