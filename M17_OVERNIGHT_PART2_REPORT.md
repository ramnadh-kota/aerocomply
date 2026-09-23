# M17 Overnight Run — Part 2 Report (broader QA/bug-fix sweep)

Date: 2026-09-19
Scope: the broader local QA sweep explicitly deferred by Part 1
(M17_OVERNIGHT_AUTONOMOUS_REPORT.md), covering drones, flights, maintenance,
inspections, evidence, compliance, release readiness, work orders, and
platform admin, run against local Postgres (localhost:55432) and the local
backend/frontend. Nothing in this report is fabricated; every claim below is
backed by a command actually run in this session.

## 1. Genuine bugs found and fixed

**None found in application code.** This was a real, non-trivial sweep (see
section 9 for what was actually checked), not a rubber stamp. The backend is
already unusually well-hardened for this stage: FK-based tenant scoping
enforced at the service layer for every entity touched, atomic
`UPDATE ... SET x = x + delta` patterns used everywhere lost-updates would
otherwise be possible (flight cycle counts, part-requirement fulfillment),
partial-failure paths (storage-succeeds/DB-fails) explicitly logged rather
than silently swallowed or misreported, and no bare `except Exception` that
masks a real error as a false-success. I did not find a broken state,
console error against real data, incorrect display, N+1 query, or
undifferentiated-500 case to fix.

One genuine **verification gap** was found and closed (not a bug, a test
coverage gap) — see section 2.

## 2. Release-readiness panel/API verified end-to-end for the Part 1 fix

Part 1's fix (`PartRequirement.fulfilled_quantity` now updates on PO
receipt) only had test coverage at the service-function level
(`db_session` fixture calling services directly). I verified it also holds
at the real HTTP API layer, which is what the frontend panel actually calls:

- `backend/app/api/v1/release_readiness.py`'s `GET
  /work-orders/{id}/release-readiness` is a thin, uncached passthrough
  straight to `release_readiness_service.get_release_readiness_for_work_order`
  — by construction there is no caching/staleness layer between the DB and
  this endpoint's response.
- I extended `backend/tests/integration/test_release_readiness_full_chain.py`
  (`test_full_readiness_chain`) with a new step 7–9 block that drives the
  **entire** MATERIAL-blocker lifecycle through real HTTP calls on the
  `TestClient`: create a part with 0 stock → create a part-requirement on
  the work order (MATERIAL blocker appears via `GET .../release-readiness`)
  → create a procurement request → approve it → create a purchase order →
  submit-for-approval → approve → send (MATERIAL blocker persists, correctly
  unchanged) → receive the PO line → `GET .../release-readiness` again →
  blocker is gone, `status == "READY"`.
  - The one non-HTTP step: `procurement_service.approve_request` enforces
    "approver ≠ requester"; the test only has one registered user/token
    available through the auth API, so approval is invoked directly against
    the same `db_session` the `client` fixture shares (a second real `User`
    row is inserted first so the FK is genuine, not faked). Every other
    step — part, part-requirement, procurement request, PO create/submit/
    approve/send/receive, and both readiness reads — is a real HTTP round
    trip through FastAPI's routing/permission/serialization layers.
- Result: **passed** on first correct attempt (after fixing the
  self-approval and FK issues above), confirming the fix is visible through
  the actual API surface the release-readiness panel consumes, not just in
  the service layer.

File changed: `backend/tests/integration/test_release_readiness_full_chain.py`
(test-only; no application code touched). Commit: `abc2e86`.

## 3. Needs user decision

- **Frontend is not wired to the real backend API.** `npm run build` and
  `npm run test` both pass, but a scan of the frontend confirms drones,
  flights, maintenance, inspections, procurement, and Lisa all render from
  `frontend/lib/mock/**` fixture data, not from `fetch` calls into the
  FastAPI backend on `localhost:8000`. This means: (a) the "browser
  click-through QA" requested in the task brief would only be exercising
  mock data, not real integration behavior, so I did not treat mock-data
  quirks as production bugs; (b) whether/when to wire the frontend to the
  real backend is a genuine product/architecture decision I should not make
  unilaterally overnight — flagging it here rather than guessing.
- Everything else reviewed (drones/battery-component lifecycle, flight
  recording/utilization, maintenance requirement due-state, inspection
  transitions, evidence upload/download/soft-delete, compliance assessment
  display, work order/task CRUD, platform admin plans/product catalog) is
  backend logic already covered by the existing 985-test suite and already
  audited once tonight per M17_OVERNIGHT_QA_REPORT.md / GO_LIVE_CHECKLIST.md
  — I did not find anything new to add to that list.

## 4. Backend test suite — final counts

```
985 passed, 16 deselected, 120 warnings in 73.57s
```
(local Postgres, `TEST_DATABASE_URL=postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_test`)
Same pass count as the Part 1 baseline — the added end-to-end assertions
extended the existing `test_full_readiness_chain` test rather than adding a
new test function.

## 5. Frontend test suite — final counts

```
Test Files  8 passed (8)
Tests       133 passed (133)
```
(`npm run test`, vitest)

## 6. ruff / mypy / tsc / eslint / build — final results

- **ruff** (`python -m ruff check .`): 8 pre-existing line-length (E501)
  errors in an unrelated migration file and an unrelated test file
  (`test_drone_lifecycle_api.py`) — present before this session, not
  touched. `ruff check` on the file I edited
  (`test_release_readiness_full_chain.py`) alone: **all checks passed**.
- **mypy** (`python -m mypy app/`): **Success: no issues found in 210 source
  files.**
- **tsc** (`npm run typecheck`): **clean**, no output/errors.
- **eslint** (`npm run lint`): **0 errors**, 54 pre-existing warnings (all
  `react-hooks/set-state-in-effect` and one unused-directive warning in
  files I did not touch).
- **build** (`npm run build`): **succeeded**, full route manifest generated.

## 7. Git commits this session

- `abc2e86` — `test(readiness): verify MATERIAL blocker clears end-to-end via HTTP API`

Full commit list since `23dcda5` (the HEAD this run started from):
```
abc2e86 test(readiness): verify MATERIAL blocker clears end-to-end via HTTP API
23dcda5 fix(readiness): fulfill PartRequirement.fulfilled_quantity on receipt   <- Part 1, prior session
```
Confirmed: `git status` shows branch **ahead of origin/main by 2 commits**;
**no `git push` was run** at any point this session.

## 8. Staging/production confirmation

No staging or production database was touched. Every test run this session
used `TEST_DATABASE_URL` pointed at local Postgres
(`localhost:55432/aerocomply_test`); no Neon connection string, staging
host, or production host appeared in any command I ran. No migration was
created or applied anywhere.

## 9. Lisa / go-live scope confirmation

Lisa's permission model was not touched — no file under
`app/services/lisa/**` or `frontend/lib/mock/ai/**` was edited. No pricing,
legal, marketing, customer-onboarding, or go-live file was touched. The
only file changed this session is the one test file listed in section 2/7.

## 10. What was actually checked (for transparency on sweep depth)

Given this was a single-pass overnight sweep, depth was prioritized over
breadth-for-its-own-sake. Concretely reviewed:
- `app/services/flight_service.py` in full (flight recording, atomic
  battery cycle-count update, utilization SUM-on-read, pagination bounds) —
  clean.
- `app/api/v1/evidence.py` upload/download/delete paths in full, including
  every `except Exception` — each is a deliberate, documented
  partial-failure log-and-re-raise, not a bug.
- `app/api/v1/release_readiness.py`, `app/services/part_requirement_service.py`,
  `app/services/receiving_service.py`, `app/api/v1/procurement.py`,
  `app/api/v1/purchase_orders.py`, `app/api/v1/receiving.py`,
  `app/api/v1/part_requirements.py`, `app/schemas/*` for the above — read in
  full to build the end-to-end test in section 2.
- Repo-wide grep for `TODO`/`FIXME`/`XXX`/`HACK` in `app/services` and
  `app/api`: **zero hits**.
- Full backend and frontend test/lint/type/build runs (sections 4–6).

Not independently re-audited this pass (already covered by tonight's
earlier reports and/or the existing 985/133 automated suites): maintenance
due-state calculation internals, inspection checklist internals, compliance
assessment engine internals, platform admin Plans/Product Catalog (already
checked once tonight as correct-empty-state per the task brief).

## Bottom line

**Ready for the user to review and push in the morning:** one commit
(`abc2e86`), test-only, extending existing coverage to prove the Part 1
material-readiness fix is visible through the real API, not just the
service layer. No application-code bugs were found this pass. The one
substantive open item is the "needs user decision" flag in section 3 — the
frontend's mock-data-only wiring — which is an architecture/product
decision, not a bug, and was left untouched.
