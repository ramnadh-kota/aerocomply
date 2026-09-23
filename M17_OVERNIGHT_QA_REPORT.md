# Overnight QA Report — 2026-09-19

Scope: staging/local QA and bug-fixing only, per the coordinating session's
explicit instructions. No Lisa autonomy work and no go-live work was done —
see confirmations at the bottom.

## 1. The two screenshot bugs

### 1a. Platform Admin > Plans / Product Catalog — "No plans/suites configured yet"

**Verdict: correct empty state, not a bug.**

Investigated `frontend/app/(app)/platform/plans/page.tsx` and the equivalent
product-catalog page, the API clients `frontend/lib/api/plan.ts` (and the
product-catalog client), and the backend routes/services:
`backend/app/api/v1/platform.py` (`POST /plans`, `POST /product-catalog/suites`),
`backend/app/services/plan_service.py::create_plan`,
`backend/app/services/product_catalog_service.py::create_suite`.

- The frontend create form calls `planApi.createPlan` / the suite equivalent,
  which POST to exactly the routes the backend exposes, with matching field
  names (`name`, `code`, `description`, `is_active`).
- I exercised the actual backend service functions directly against the
  local Postgres instance (`aerocomply_dev`, port 55432) to prove the create
  path works end-to-end, independent of HTTP/auth plumbing:
  ```
  PLAN CREATED: f4067e24-1880-4e3e-8cbf-54a4ecfcf09c qa-test-ff28e3e3
  SUITE CREATED: 7153464a-3e01-4aa0-bcbb-868e95062569 qa-suite-fa6b24a7
  ```
  Both rows were created successfully (transaction + audit event pattern
  worked as designed), then deleted afterward to leave the dev DB clean.
- The backend integration test suites `tests/integration/test_plan_administration.py`
  and `tests/integration/test_product_catalog.py` (32 tests total) pass
  against the same local Postgres, covering create/list/activate/deactivate
  and conflict (duplicate code) cases.

Conclusion: the "No plans/suites have been configured yet" message is simply
because the catalog is genuinely empty in this environment (nobody has
created a plan or suite yet tonight) — not a broken create flow. No fix
needed.

### 1b. Lisa dashboard — PERMISSION_DENIED / aircraft:read banner

**Verdict: correct-by-design, not a bug.**

Read `frontend/components/ai/AIConsole.tsx` end to end (the banner, the
`backendAlertsStatus` state machine, and the `ask()` fallback logic) and
`backend/app/core/permissions.py`.

- The banner only appears when `isRealModeSession` is true, the proactive
  alerts fetch returns HTTP 403, and `ApiError.status === 403` — i.e. only
  when the backend's own `require_permission` dependency genuinely rejects
  the request because the signed-in identity lacks `aircraft:read`. A
  platform-admin identity legitimately does not have this permission — it
  administers tenants/plans/catalog, not one customer's fleet — so 403 here
  is the RBAC system working correctly.
- The code explicitly distinguishes this case (`backendAlertsStatus ===
  "forbidden"`) from a genuine backend outage (`"unavailable"`), with a code
  comment at `AIConsole.tsx:244-248` explaining exactly why: "A 403 means
  this identity genuinely lacks aircraft:read ... that is not the backend
  being down." The UI correctly shows "—" instead of a fabricated count in
  that case, rather than falling back to demo data — which is exactly the
  "never show fake data in place of a real permission gate" policy the
  product already documents elsewhere for Lisa.
- The messaging itself is already fairly clear: it states the specific
  missing permission, explains it's expected for a platform-admin identity,
  and confirms it deliberately isn't substituting demo counts.

I did not change the permission check (correctly), and did not change the
messaging either, since the existing copy already explains the situation
accurately. If the user wants an *even* friendlier UX later (e.g. a link to
"view as an org-scoped test user" instead of just prose, or hiding the
proactive-alerts KPI row entirely for platform-admin identities rather than
showing an inline banner), that is a product/UX preference, not a bug —
logged under "needs user decision" below.

## 2. Backend test suite (pytest)

Environment: local Postgres on port 55432, `TEST_DATABASE_URL` overridden to
`postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_test`
(the stale default in `tests/integration/conftest.py` points at port 5432 and
was overridden via env var only — the file itself was not edited).

```
981 passed, 1 failed, 16 deselected, 120 warnings in 75.95s
```

The one failure:

**`tests/integration/test_aog_recovery_service.py::test_full_supply_chain_progression_updates_blocker_category`**

Root cause (traced by hand, with a temporary debug patch to the test file
that was reverted afterward — `git status` confirms the test file is
unmodified):

- After a full procure → approve → PO → send → receive cycle, the
  `PartRequirement` row correctly flips from `SHORT` to `AVAILABLE`
  (`part_requirement_service._derive_status`), and
  `aog_recovery_service.get_recovery_status`'s own `MATERIAL_*` staged
  blockers correctly clear (`shortages = [... status == SHORT]` no longer
  matches it).
- However, `release_readiness_service.get_release_readiness_for_work_order`
  (added in the just-landed `285a667 feat(readiness): add material,
  compliance, and evidence blockers`) computes its own separate `"MATERIAL"`
  blocker (`backend/app/services/release_readiness_service.py:190-205`) using
  a *different* gate: `part_requirement.fulfilled_quantity <
  part_requirement.required_quantity`. `fulfilled_quantity` is never
  incremented anywhere by receiving/inventory code — grep confirms it is
  only ever set via the manual `PATCH /part-requirements/{id}` endpoint
  (`part_requirement_service.update_part_requirement`). So this readiness
  gate stays permanently "blocked" even once the part is fully received and
  the requirement's own status says `AVAILABLE`.
- `aog_recovery_service.get_recovery_status` merges
  `release_readiness_service`'s blockers straight into its own `blockers`
  list (`aog_recovery_service.py:179-180`), which is how the stale
  `"MATERIAL"` blocker leaks into the AOG recovery status and fails the
  test's final assertion.

**I did not fix this.** This sits squarely inside release-readiness /
material-gate logic, which the rules for tonight explicitly say never to
weaken, and closing this gap requires a real product decision about what
"material requirement satisfied" should mean for release-readiness purposes:
- Should `AVAILABLE` (part physically in stock, not yet installed on the
  aircraft) satisfy the release-readiness material gate? or
- Should the gate require an explicit "installed/consumed" signal
  (incrementing `fulfilled_quantity`) that doesn't exist as an automated
  workflow step yet — meaning the *real* gap is a missing "mark part
  installed" action somewhere in the maintenance/task-execution flow?

Either resolution changes what release-readiness is allowed to report as
"blocked," so I logged it under "needs user decision" rather than guessing.
The test was left exactly as-is (still failing, not weakened or deleted), so
tomorrow's decision has a reproducing test to validate against.

No other backend test failures. No test was modified, weakened, or deleted.

## 3. Frontend test suite

- **vitest**: `8 test files, 133 tests` — all passed (`npm test -- --run`, exit 0).
- **tsc --noEmit**: clean, no errors.
- **eslint .**: clean, no errors/warnings.
- **next build**: succeeded; full route manifest printed with no build
  errors (static + dynamic routes for aircraft, drones, maintenance,
  procurement, platform/plans, platform/product-catalog, etc. all compiled).

One incidental side effect: running `next build` regenerated
`frontend/next-env.d.ts` (Next.js changed its internal `.next/types` path
convention between dev and build). This is a machine-generated file that
Next.js explicitly marks "should not be edited" — I reverted it with `git
checkout` so the working tree has zero unintended diffs from this session.

## 4. Other bugs found and fixed

None beyond what's covered above. I did not find other broken create flows,
console errors, or dead-end UX during code-level review of the platform
admin, plans, product-catalog, and Lisa/AIConsole code paths. I was not able
to click through the running app in a browser this session (no dev server
was started against a browser tool as part of this pass — the verification
above was done at the service/API/test-suite level instead, which is a
narrower but concrete form of verification). If a live click-through is
still wanted, that's an easy follow-up but I want to be honest that it
wasn't done here rather than claim browser verification that didn't happen.

## 5. Flagged as "needs user decision" (not fixed)

1. **Release-readiness material gate semantics** (test failure above): should
   `PartRequirement.status == AVAILABLE` (received, not yet installed)
   satisfy the release-readiness `MATERIAL` blocker, or does the product need
   a new explicit "part installed/consumed against this work order" step
   before the gate clears? This is a compliance/release-decision question,
   not something I'll infer.
2. **Lisa PERMISSION_DENIED banner UX** (bug 1b above): current messaging is
   accurate and was left as-is. If the product wants a friendlier
   alternative for platform-admin identities (e.g. "switch to an org-scoped
   test user" affordance, or hiding the KPI row instead of showing a banner),
   that's a UX preference decision, not a bug fix.

## 6. Lisa autonomy — explicit confirmation

**Nothing was done to give Lisa/the AI assistant any write or action
capability.** No code in `frontend/components/ai/AIConsole.tsx` or any
backend `lisa`/AI-agent module was modified. The product's existing
constraint ("Lisa explains, summarizes, and ranks; it never makes or
overrides a compliance, inspection, release, or airworthiness decision") is
untouched. Read-only behavior (the PERMISSION_DENIED banner, fallback
messaging) was reviewed but not altered.

## 7. Going live — explicit confirmation

**No go-live work was performed.** No pricing changes, no legal/compliance
sign-off, no production deployment, no customer-onboarding flow work, no
marketing content. **Production Neon project `bitter-tooth-52841705` was
never accessed, queried, or referenced by any command run this session.**
All database work happened against local Postgres (`localhost:55432`,
databases `aerocomply_dev` and `aerocomply_test`) only. Render
staging/`aerocomply-backend-staging` and Neon staging
(`small-meadow-85982633`) were also not touched this session — no `render`
CLI or staging DB commands were run.

## 8. Final git state

- Branch: `main`, up to date with `origin/main` at session start
  (`285a667 feat(readiness): add material, compliance, and evidence
  blockers`).
- **No commits were made this session.** All investigation was either
  read-only or self-reverting (the temporary debug print added to
  `tests/integration/test_aog_recovery_service.py` to trace the release-
  readiness bug was reverted with `git checkout` before finishing; a
  Next.js-regenerated `frontend/next-env.d.ts` diff from running `next
  build` was likewise reverted).
- Working tree at end of session: identical to the start, plus this new
  report file (`M17_OVERNIGHT_QA_REPORT.md`) and the pre-existing untracked
  `M17_*.md` files from earlier in the night, which I did not touch.
- Nothing was pushed (nothing was committed).
