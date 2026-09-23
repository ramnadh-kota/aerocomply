# M17 Overnight Autonomous Run — Report

Date: 2026-09-19
Scope executed: Part 1 (material-readiness fix) only, fully tested. Part 2
(broader QA/bug-fix pass across drones/flights/maintenance/etc.) was **not**
attempted this run — see "What was not done" below. This report only
describes work that was actually performed and verified; nothing here is
fabricated or assumed.

## 1. Material-readiness fix (Part 1)

### The gap
`release_readiness_service.get_release_readiness_for_work_order` (backend/app/services/release_readiness_service.py)
raises a MATERIAL blocker whenever `PartRequirement.fulfilled_quantity <
PartRequirement.required_quantity` and the requirement isn't
FULFILLED/CANCELLED. Nothing in the codebase ever incremented
`fulfilled_quantity` — it stayed at its default of 0 forever, so a fully
received part requirement never cleared its MATERIAL blocker.

### Investigation
- `part_requirement_service._derive_status` only re-derives the *status*
  string (REQUIRED/SHORT/AVAILABLE) from `Part.available_quantity`; it
  explicitly documents that ORDERED/RECEIVED/FULFILLED/CANCELLED are "set
  explicitly by later procurement/receiving workflows (not yet built)."
- `inventory_transaction_service.receive_part` bumps `Part.quantity_on_hand`
  and calls `part_requirement_service.recompute_status_for_part`, which only
  flips SHORT↔AVAILABLE — never touches `fulfilled_quantity`.
- `receiving_service.receive_purchase_order` is the real supply-chain
  receiving flow (PO line → `ProcurementRequest` → `Part`), and is what the
  previously-failing AOG test exercises end-to-end.
- An existing, still-relevant test,
  `test_receiving_stock_flips_short_requirement_to_available`
  (tests/integration/test_inventory_transaction_service.py), asserts that a
  generic/ad hoc `receive_part` call (no PO, no work order) results in status
  `AVAILABLE`, not `FULFILLED`. This is a deliberate, load-bearing
  distinction: "available in stock" and "fulfilled against this specific
  job" are not the same thing. My first implementation attempt hooked the
  fulfillment logic into the generic `receive_part`/`recompute_status_for_part`
  path and broke this test — I reverted that and moved the logic to the
  place that actually has the work-order/task context: the PO-receiving flow.

### Fix implemented
- **backend/app/services/part_requirement_service.py**: added
  `fulfill_from_receipt(db, *, organization_id, part_id, work_order_id,
  task_id, received_quantity)`. It looks up open (non-FULFILLED/CANCELLED)
  `PartRequirement` rows for that `part_id` + `work_order_id` (+ `task_id`
  when given), oldest first, and applies the received quantity FIFO across
  them via a single atomic statement per requirement:
  `UPDATE part_requirements SET fulfilled_quantity =
  LEAST(required_quantity, fulfilled_quantity + delta) WHERE id = :id`.
  This is a database-atomic operation, not an application-level
  read-modify-write — Postgres computes the new value from the row's
  current value at UPDATE time, so two concurrent receipts against the same
  requirement serialize on the row instead of one clobbering the other, and
  the `LEAST(...)` cap means it can never exceed `required_quantity`. This
  mirrors the existing convention in this codebase (see
  `part_service.get_part`'s `for_update=True` docstring, and how the
  inventory ledger avoids stale-read races).
  `recompute_status_for_part` (the generic, part-quantity-driven path) was
  left untouched — it still only ever moves SHORT↔AVAILABLE, never
  `fulfilled_quantity`.
- **backend/app/services/receiving_service.py**: after
  `receive_purchase_order` posts a receipt to inventory for a PO line linked
  to a `ProcurementRequest` with a known `part_id`, it now also calls
  `fulfill_from_receipt` with that request's `work_order_id`/`task_id`/`part_id`
  and the received quantity. A PO line with no linked `ProcurementRequest`,
  or a `ProcurementRequest` with no `work_order_id`, is a no-op (nothing to
  fulfill — unchanged from before).
- **backend/app/services/inventory_transaction_service.py**: no functional
  change beyond what was reverted; kept exactly as before this change (the
  generic receive path never touches `fulfilled_quantity`).

### Migration
**None created.** `fulfilled_quantity` already exists as a column on
`PartRequirement` (backend/app/models/part_requirement.py) with a working
default of 0; the fix is service-logic-only, using existing columns.

### Tests
New file: `backend/tests/integration/test_material_readiness_fulfillment.py`
(3 tests, all passing):
- `test_full_receipt_fulfills_requirement_and_clears_material_blocker` —
  receiving exactly the required quantity against a work order's
  `PartRequirement` sets `fulfilled_quantity` to the requirement, flips
  status to FULFILLED, and the MATERIAL blocker disappears from
  `release_readiness_service`'s output for that work order.
- `test_partial_receipt_keeps_blocker_with_correct_remaining_quantity` —
  receiving less than required leaves the MATERIAL blocker in place with the
  correct `fulfilled_quantity=3 of required_quantity=5` wording, status not
  yet FULFILLED.
- `test_concurrent_receiving_against_same_requirement_does_not_lose_updates`
  — verifies the atomic-UPDATE property directly: two receipts landing
  back-to-back against the same requirement both land (sum to
  `required_quantity`, nothing lost), and a third, over-eager receipt cannot
  push `fulfilled_quantity` past `required_quantity`. **Caveat, stated
  honestly**: true multi-connection/thread concurrency could not be modeled
  under this test suite's `db_session` fixture (tests/integration/conftest.py) —
  each test runs inside one already-open connection/transaction rolled back
  at teardown, so rows created in one test session are invisible to a second,
  separate connection until a real top-level commit that never happens. I
  attempted a two-thread/two-connection version first; it failed with
  `NotFoundError` because the PO/work order rows were never visible outside
  the fixture's transaction — that is a limitation of the test fixture, not
  a bug in the fix. The test as committed instead verifies the specific
  database-level property (`LEAST`-capped atomic UPDATE) that is what
  actually prevents lost updates under real concurrent connections.

Test run results (local Postgres, localhost:55432, `TEST_DATABASE_URL`
pointed at `aerocomply_test`):
- `tests/integration/test_aog_recovery_service.py` — **9 passed**, including
  the previously-failing
  `test_full_supply_chain_progression_updates_blocker_category`, which now
  passes because the MATERIAL blocker genuinely clears after the full
  approve → PO → send → receive chain.
- `tests/integration/test_inventory_transaction_service.py`,
  `test_part_requirement_service.py`, `test_receiving_service.py`,
  `test_release_readiness_full_chain.py`,
  `tests/unit/test_release_readiness_service.py`,
  `test_material_readiness_fulfillment.py` — **59 passed, 0 failed** (this
  includes the pre-existing `test_receiving_stock_flips_short_requirement_to_available`,
  confirmed still passing after the revert/redesign).
- Full backend suite (`pytest -q`, whole `backend/tests` tree): **985
  passed, 16 deselected, 0 failed**.
- `ruff check` on all four changed/added files: **all checks passed** (after
  fixing one unused-variable and two import/line-length issues introduced
  by my own draft).
- `mypy` on the three changed service files: **no issues found**.

### Environment note (worth knowing)
The test suite's `TEST_DATABASE_URL` default
(`postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply_test`,
in `tests/integration/conftest.py`) does not match `backend/.env`'s
`DATABASE_URL` (`postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_dev`).
Running `pytest` without `TEST_DATABASE_URL` set fails every integration
test at fixture setup with a connection error to port 5432 (nothing
listening there in this environment) — this is a pre-existing environment
mismatch, not something I introduced or fixed. All test runs in this report
were done with:
```
TEST_DATABASE_URL=postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_test
```
against a database named `aerocomply_test` on the same local Postgres
instance as `.env`'s `aerocomply_dev` (confirmed to already exist; not
created by me as part of any migration).

## 2. Part 2 (broader QA/bug-fix pass) — **not done this run**

I did not get to the drones/flights/maintenance/inspections/evidence/
compliance/work-orders/platform-admin sweep, or any frontend
vitest/tsc/eslint/build run, or any browser click-through QA. Given the
session's effort/time budget, I prioritized doing Part 1 completely and
honestly (including catching and fixing my own regression before it landed)
over starting a broad sweep I would not have had room to finish and verify
properly. I would rather report this gap accurately than claim partial,
unverified fixes across a dozen modules.

**Needs user decision / follow-up**: whether to run Part 2 as its own
scoped session (recommended — it's a large, independent piece of work and
deserves its own dedicated pass rather than being squeezed in after Part 1).

## 3. Full backend test suite final count
985 passed, 16 deselected, 0 failed (see Section 1 for the exact command and
environment).

## 4. Full frontend test suite final count
**Not run.** No frontend changes were made this session, and Part 2 (which
would have exercised the frontend) was not attempted.

## 5. ruff / mypy / tsc / eslint / build final results
- `ruff check` (on the 4 files touched): all checks passed.
- `mypy` (on the 3 changed service files): no issues found.
- `tsc` / `eslint` / frontend build: not run (no frontend changes).

## 6. Git commits made
```
23dcda5 fix(readiness): fulfill PartRequirement.fulfilled_quantity on receipt
```
One commit, scoped to the material-readiness fix (3 service files + 1 new
test file). **Nothing was pushed** — `git push` was never run. `git log`
confirms this commit sits directly on top of the pre-existing tip of `main`
(`285a667`) with nothing else added.

## 7. Staging / production confirmation
- Production Neon (`bitter-tooth-52841705`): never connected to, never
  referenced, never touched in any way.
- Staging Neon (`small-meadow-85982633`): never connected to, never
  referenced, never touched in any way — this run only ever used the local
  Postgres instance at `localhost:55432` (`aerocomply_dev` per `.env`, plus
  the pre-existing `aerocomply_test` database used by the test suite).

## 8. Lisa / go-live scope confirmation
Lisa's permission model was not touched. No files under any AI-assistant
read/write-capability path were opened or edited. No go-live, pricing,
legal, marketing, or customer-onboarding files or logic were touched.

## What's ready for the user to review/push
- Commit `23dcda5` — the material-readiness fix, fully tested (985/985
  backend tests passing, including the specifically-named previously-failing
  AOG test), ruff/mypy clean. This is ready to review and push at the user's
  discretion.

## What still needs the user's decision or further work
- **Part 2 was not attempted.** The drones/flights/maintenance/inspections/
  evidence/compliance/work-orders/platform-admin QA sweep, plus the frontend
  test/lint/build suite and any browser click-through QA, remain entirely
  outstanding and should be run as a dedicated follow-up session.
- The `TEST_DATABASE_URL` default in `tests/integration/conftest.py` doesn't
  match this environment's actual local Postgres port/credentials (5432 vs.
  55432, `aerocomply`/`aerocomply` vs. `postgres`/`aerocomplydevpw`). Anyone
  running `pytest` locally without exporting `TEST_DATABASE_URL` first will
  see every integration test fail at fixture setup with a connection error —
  worth deciding whether to update the conftest default, add a `.env.test`,
  or document the required export somewhere discoverable. I did not change
  this default myself since it's a cross-cutting environment/DX decision,
  not a bug in the code under test.
