# M22 — Work Order Lifecycle & MRO Operations

## Executive Summary
Milestone M22 upgrades KOTA AEROSPACE's Work Order architecture into a production-grade, state-machine-governed MRO operations system. It establishes complete traceability from:
$$\text{Asset} \rightarrow \text{Maintenance Requirement} \rightarrow \text{Defect / Finding} \rightarrow \text{Work Order} \rightarrow \text{Tasks} \rightarrow \text{Parts / Components} \rightarrow \text{Labour / Technician} \rightarrow \text{Inspection} \rightarrow \text{Evidence} \rightarrow \text{Compliance} \rightarrow \text{Closure} \rightarrow \text{Readiness}$$

This implementation enhances the existing database schema and domain models rather than introducing parallel or duplicate MRO systems.

---

## 1. Data Models & Migration

### Database Migration: `0045_work_order_lifecycle`
Migration `0045` safely adds operational lifecycle columns and performance indexes to the existing `work_orders` and `tasks` tables without breaking pre-existing records:

#### `work_orders` Table Enhancements:
- `title`: `VARCHAR(255)` (default `'Untitled Work Order'`)
- `description`: `TEXT`
- `work_order_type`: `VARCHAR(64)` (default `'CORRECTIVE'`)
- `maintenance_category`: `VARCHAR(64)`
- `scheduled_start`: `TIMESTAMPTZ`
- `scheduled_end`: `TIMESTAMPTZ`
- `actual_start`: `TIMESTAMPTZ`
- `actual_end`: `TIMESTAMPTZ`
- `due_at`: `TIMESTAMPTZ` (indexed)
- `estimated_hours`: `DOUBLE PRECISION`
- `actual_hours`: `DOUBLE PRECISION`
- `estimated_cost`: `DOUBLE PRECISION`
- `actual_cost`: `DOUBLE PRECISION`
- `assigned_to_user_id`: `UUID` foreign key to `users.id` (indexed)
- `location`: `VARCHAR(255)`
- `source_type`: `VARCHAR(64)`
- `source_reference`: `VARCHAR(255)`
- `compliance_required`: `BOOLEAN` (default `False`)
- `compliance_reference`: `VARCHAR(255)`
- `completed_at`: `TIMESTAMPTZ`
- `closed_at`: `TIMESTAMPTZ`
- `cancelled_at`: `TIMESTAMPTZ`
- `cancellation_reason`: `VARCHAR(500)`

#### `tasks` Table Enhancements:
- `task_number`: `VARCHAR(32)`
- `title`: `VARCHAR(255)`
- `estimated_hours`: `DOUBLE PRECISION`
- `actual_hours`: `DOUBLE PRECISION`
- `started_at`: `TIMESTAMPTZ`
- `completed_at`: `TIMESTAMPTZ`
- `sequence`: `INTEGER` (default `1`)
- `notes`: `TEXT`

---

## 2. State Machine & Transition Gates

The Work Order domain enforces an explicit, finite state transition graph:

$$\text{DRAFT} \rightarrow \text{OPEN} \rightarrow \text{PLANNED} \rightarrow \text{ASSIGNED} \rightarrow \text{IN\_PROGRESS} \leftrightarrow \text{ON\_HOLD} \rightarrow \text{INSPECTION} \rightarrow \text{COMPLETED} \rightarrow \text{CLOSED}$$

*Exception / Terminal State:* $\text{CANCELLED}$ (accessible from any active non-closed state with a mandatory reason $\ge 3$ characters).

### Transition Gates & Invariants:
1. **DRAFT $\rightarrow$ OPEN**: Formalizes the work order from draft state to open work backlog.
2. **OPEN $\rightarrow$ PLANNED**: Scopes tooling, parts, and scheduling.
3. **PLANNED $\rightarrow$ ASSIGNED**: Requires a valid technician in the same organization (`assigned_to_user_id` must not be null).
4. **ASSIGNED $\rightarrow$ IN\_PROGRESS**: Requires assignment; automatically sets `actual_start = now()`.
5. **IN\_PROGRESS $\leftrightarrow$ ON\_HOLD**: Allows holding work for parts/tooling and resuming execution.
6. **IN\_PROGRESS $\rightarrow$ INSPECTION**: Requires all execution tasks on the work order to have reached `execution_state == COMPLETED`. Blocked with `409 Conflict` if any task remains uncompleted.
7. **INSPECTION $\rightarrow$ COMPLETED**: Requires all linked inspection requirements to be satisfied. Automatically sets `completed_at = now()`.
8. **COMPLETED $\rightarrow$ CLOSED**: Evaluates the authoritative `ReleaseReadinessService`. Closure is blocked if readiness is `BLOCKED`. Automatically sets `closed_at = now()`.
9. **CANCELLED**: Requires a mandatory cancellation reason of at least 3 characters. Sets `cancelled_at = now()` and `cancellation_reason`.

---

## 3. RBAC & Security
- **Administrative Operations** (`create`, `assign`, `close`, `cancel`, `delete`): Require `Permission.AIRCRAFT_WRITE`.
- **Operational Execution** (`transition`, `complete`, task update, task completion): Require `require_any_permission(Permission.AIRCRAFT_WRITE, Permission.TECHNICIAN_WRITE)`.
- Field technicians holding role `MAINTENANCE_ENGINEER` with `TECHNICIAN_WRITE` can execute operational state transitions and complete assigned tasks, but cannot alter administrative scope, cancel, or close work orders.

---

## 4. Turnaround Time (TAT) Integration
Operational Turnaround Time is wired directly to `WorkOrder.due_at`:
- `ON_TRACK`: Work order is due $> 3$ days in the future, or already completed on time.
- `AT_RISK`: Work order is due within $\le 3$ days.
- `DELAYED`: Work order due date has passed.
- `UNKNOWN`: No due date recorded on the work order (`due_at is None`).

Both individual status (`GET /work-orders/{id}/tat`) and fleet summary (`GET /fleet/tat`) are protected by `require_feature("work_order_management")` and `require_permission(Permission.AIRCRAFT_READ)`.

---

## 5. Tenant Isolation & Entitlements
- Every query, mutation, task addition, and transition enforces strict `organization_id == current_user.organization_id` server-side.
- Cross-tenant requests return `404 Not Found` (never leaking existence).
- Feature entitlement `require_feature("work_order_management")` is consistently enforced across all endpoints.

---

## 6. Frontend Architecture
- `/maintenance/work-orders`: Upgraded with search, status filtering tabs, priority dropdown, type dropdown, overdue filter toggle, pagination, sorting, and accessible "Create Work Order" modal.
- `/maintenance/work-orders/[id]`: Upgraded with lifecycle action bar, status pipeline indicator, technician assignment dialog, task creation & gate panels (`RealTaskGatePanel`), parts requirements panel, findings panel, release readiness integration (`RealReleaseReadinessPanel`), TAT status badge, and audit milestone timeline.
- Both REAL mode and DEMO simulation modes remain completely functional.
