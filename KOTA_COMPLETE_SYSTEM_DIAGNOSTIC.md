# Kota Aerospace — Complete System Diagnostic

Scope honesty: this was a **bounded forensic pass**, not an exhaustive audit of every
subsystem. Sections marked **NOT AUDITED** were not examined and no claim is made about them.
Code is the source of truth; every finding below was observed in the repository or produced
by an executed command.

## 1. Executive summary
- The commercial architecture (Suite → Plan → Subscription → effective entitlement) is sound
  and enforced server-side on every request; the previous M20 pass closed the main gaps.
- This pass found **one P0** (unauthenticated cross-tenant telemetry write), **two whole routers
  that returned HTTP 500 on every call** (`/edge/*`, `/commercial/*`), an M7 signal path that
  crashed on any asset with a completed work order, and a migration (0061) that could not be
  downgraded/re-upgraded. All are fixed with regression tests (except where noted).
- The test suite gave **false confidence**: the two dead routers and the M7 crash had no
  route-level tests, so 1,900+ tests stayed green while the endpoints were broken.
- Not verified at all: real multi-vehicle MAVLink behaviour, LISA tenant grounding end-to-end,
  Neo4j (not implemented), deployment configs, concurrency/performance, browser console cleanliness.

## 2. Repository inventory (measured)
| Item | Count |
|---|---|
| API operations (OpenAPI) | 472 (462 bearer-protected, 10 public) |
| Public operations | auth login/refresh/forgot/reset/onboarding/SSO x2, health x2, DJI webhook |
| Alembic migrations | 61, single head `0061`, linear |
| Model modules / service modules / api modules | 49 / 66 / 51 |
| Tenant-scoped ORM models | 62 |
| Backend test files | 176 |
| Frontend pages (`page.tsx`) | 132 (99 static/dynamic routes in build) |
| Frontend test files | 30 |

## 3. Architecture reality
- Layers as intended: Next.js → FastAPI → `get_current_user` (JWT + per-request org status
  re-check) → `require_permission` / `require_feature` → services → PostgreSQL.
- Entitlements: one resolver (`entitlement_service.resolve_entitlements`), no cache, no
  entitlement claims in JWT.
- **Knowledge graph / Neo4j: NOT IMPLEMENTED.** Only a config setting and a docker-compose entry
  exist; `app/graph/` contains an empty `__init__.py`. PostgreSQL is the only store.
- Intended-vs-actual differences: see §5 (dead routers, ungated features, drift).

## 4. Suites
DRONE_UAV, AIRCRAFT, HELICOPTER, EVTOL_AAM seeded by migration 0061. Cloned dev DB after
migration: 0 subscriptions without suite, 0 suite/plan mismatches, 0 orgs with >1 current
subscription, 0 plans carrying features from a foreign suite.

## 5. Issues found
| ID | Sev | Area | Problem | Root cause | Fixed | Test |
|---|---|---|---|---|---|---|
| F-01 | **P0** | Security/tenancy | `POST /telemetry/dji/webhook` unauthenticated; signature only checked if the header was sent; tenant chosen by `X-Organization-ID`; hardcoded fallback secret `dji-test-secret` | verification made conditional; settings had no `dji_webhook_secret` field | Yes: signature mandatory, endpoint 503 when no secret configured, secret is a real setting with no default | `test_dji_webhook_api_endpoint` (5 cases). Old assertion expected 200 for unsigned requests — replaced, reason in test |
| F-02 | P1 | Backend/RBAC | All 10 `/edge/*` management/read endpoints raised `AttributeError` (500) | called non-existent `CurrentUser.require_permission` and non-existent `Permission.FLEET_MANAGE/READ` | Yes: standard RBAC dependencies (ORG_MANAGE for management, AIRCRAFT/DRONE_READ for reads) | `test_edge_router_rbac_instead_of_500` |
| F-03 | P1 | Backend/RBAC | All 5 `/commercial/*` endpoints 500; onboarding-stage PATCH also never committed and accepted any string | same defect + missing commit + no validation | Yes | `test_commercial_router_endpoints_no_longer_500`, `test_onboarding_stage_patch_*` |
| F-04 | P1 | M7 | `_evaluate_compliance_evidence_gaps` crashed for any asset with a COMPLETED work order | queried non-existent `EvidenceFile.work_order_id` | Yes: joined Evidence→Task | `test_m7_evidence_gap_query_no_longer_raises…` |
| F-05 | P1 | Plans | `update_plan(suite_id=…)` raised `NameError`; no guard when moving a plan with subscribers | undefined `_validate_suite_id` | Yes: reject if subscribers or out-of-suite features | `test_update_plan_suite_move_guards` |
| F-06 | P1 | Database | Migration 0061 not round-trippable (`try/except` around DROP inside a Postgres transaction aborts it; downgrade did not restore 0024 shape) | swallowed error, wrong downgrade | Yes: `IF EXISTS`, correct downgrade | existing `test_asset_foundation` round-trip |
| F-07 | P1 | Subscription | `update_subscription` allowed moving a subscription to another suite's plan | no suite check | Yes: `suite_plan_mismatch` | M20 tests + rewritten assertion in architecture test |
| F-08 | P2 | Entitlement | `require_feature` chose error code by substring of the feature name | heuristic | Yes: suite-boundary based | M20 tests |
| F-09 | P2 | Subscription | `schedule_subscription` left `suite_id` NULL | omission | Yes | M20 test |
| F-10 | P2 | Entitlement | `/inspections` had no feature gate | omission | Yes (`inspections_management`, present in all seed/default plans) | full suite |
| F-11 | P2 | Database/tooling | `app.models` did not import 10 model modules → `Base.metadata` incomplete for Alembic autogenerate (would propose dropping tables) | indirect imports only | Yes: explicit imports | none (verified: no missing/extra tables vs DB) |
| F-12 | P2 | Data import | `Asset.is_deleted` does not exist (model uses `deleted_at`) → AttributeError in drone dedup path | wrong column | Yes | none — mypy no longer reports it |
| F-13 | P2 | Compliance | `Asset.name` does not exist → AttributeError explaining an asset-only obligation | wrong column | Yes (`registration`) | none — mypy no longer reports it |
| F-14 | P2 | Edge | `trace_telemetry_lineage` read non-existent `HUMSExceedance.peak_value/.status` | wrong columns | Yes (`observed_value`, `threshold_value`, `parameter`) | none — needs telemetry fixtures |
| F-15 | P2 | Edge | `ValidationError` undefined in `edge_hardware_service` (revoked-device paths) | missing class | Yes: `ConflictError(code="device_revoked")` | import-level check only |
| F-16 | P2 | Frontend | Entitlements never refreshed; fail-open on non-granting status; route URLs unguarded; hooks-rule violation in `FeatureGuard`; unescaped entities | — | Yes | 4 new vitest + lint 11→0 errors |
| F-17 | P3 | Types | `Any` not imported in `decision_simulation_service` | — | Yes | — |
| F-18 | P2 | Entitlement | Backend gates missing for `/telemetry` JWT routes, `release_readiness`, `battery_analytics`, `predictive_maintenance`, `audit_logging` | routes never wired | **No** — telemetry mixes device/webhook/JWT auth and release_readiness needs plan seeding first; changing tenant access needs a product decision | — |
| F-19 | P2 | Telemetry | MAVLink connector parses `seq`/`compid` but never uses them: vehicle identity is `system_id` only, no sequence-gap/duplicate detection at connector level | incomplete | **No** | no tests for out-of-order, late packets, store-and-forward |
| F-20 | P2 | Database | 175 model↔schema differences (58 nullability, 40 add_index, 30 remove_index, 26 FK, …); tables match exactly | hand-written migrations | **No** — not touching history; autogenerate unusable until reconciled | — |
| F-21 | P3 | Quality | ruff: 3,055 findings (1,091 line-length, 142 files unformatted); mypy: 100 errors (135 before) | never enforced | **No** | — |
| F-22 | P1 (ops) | Data | On the cloned dev DB, 40 of 47 organizations have **no subscription** → resolve to NO_SUBSCRIPTION → every feature-gated API denies. Migration 0061 does not create subscriptions | data state | **No** — check production before deploy | — |

Totals: **22 issues recorded; 17 fixed, 5 open.**

## 6. Security findings
F-01 (P0, fixed). No hardcoded secrets found by pattern scan of `app/` and `scripts/`
(defaults exist for dev only: `jwt_secret_key`, `s3_secret_key`; `main.py` refuses the
default JWT secret outside development). Tokens are kept in `localStorage` (XSS-exposed by design;
not changed). CORS: wildcard is checked in `main.py` (not analysed further).

## 7. Tenant isolation
- Static scan: of 62 tenant-scoped models, every `select(...)` statement in `app/api` and
  `app/services` that omits `organization_id` was reviewed — remaining hits are platform-admin
  control-plane code (deletion/restoration/approval/dashboard), login-by-email, or lookups via an
  already-scoped parent. No reachable tenant-route leak found by this method.
- `tenant_service` user lookups verify `user.organization_id`.
- Existing suite has 54 files referencing cross-tenant cases. **Not proven** for every endpoint;
  the scan is heuristic (statement-level text match), not a per-route runtime probe.

## 8. AuthN / AuthZ
`get_current_user` re-checks org suspended/deleted on every request; entitlements re-resolved
per request; 10 public operations are expected ones. F-02/F-03 were RBAC defects that failed
closed (500), not open. Refresh/expiry/concurrent-tab behaviour: **NOT AUDITED**.

## 9. Database
Migration head 0061, chain linear, upgrade verified on a clone of the dev DB (47 orgs).
All 62 tenant-scoped tables have non-null `organization_id`; 11 tables legitimately lack it.
Two users on the clone have no roles (data).

## 10–12. Suite/Plan/Subscription, frontend, backend
See M20 documents (`M20_*.md`) and F-05…F-10, F-16. ESLint: 0 errors, 122 warnings.
Platform pages contain hardcoded demo IDs only inside `mode === "DEMO"` branches (mocked by design).

## 13–14. Telemetry / MAVLink
F-19. Idempotency: unique constraints exist on telemetry event/reading tables and 12 test files
mention idempotency; multi-vehicle test coverage is thin (2 files mention system id). **Real
multi-vehicle/high-frequency behaviour was not exercised.**

## 15–17. HUMS, M7, LISA
HUMS/M7 tests exist and pass (feature engine, diagnostics, prognostics, M7). F-04 was found in M7.
LISA: 67 of its tool code references carry `organization_id`; tenant grounding and
"cannot invent facts" behaviour were **not verified end-to-end**.

## 18. API contract
255 distinct frontend path literals compared with the OpenAPI paths: all resolve (5 flagged were
query-string template artefacts, checked manually). HTTP methods, response shapes and error
structures were **not** compared.

## 19. Performance / 20. Deployment / 37. Observability / 41. Documentation
**NOT AUDITED.** (Deployment: `infra/docker-compose.yml` and `infra/workflows` exist; no
Vercel/Render config was reviewed. Many pre-existing `M*_*.md` documents were not reconciled
with code.)

## 21. Test coverage findings
False confidence confirmed (F-02, F-03, F-04 had no route-level or runtime tests). Coverage gaps
remaining: telemetry out-of-order/late/store-and-forward, F-12/F-13/F-14 paths, real-browser flows.

## 22. Bugs fixed / 23. Bugs remaining
Fixed: F-01…F-17. Remaining: F-18…F-22.

## 24. Technical debt
Drift (F-20), lint/type debt (F-21), CRLF/LF warnings on many files, `TimestampMixin` has no
`updated_at` but `edge_hardware_service` assigns `EdgeDevice.updated_at` (silently not persisted).

## 25. Production risks
1. F-22 organizations without subscriptions will lose all gated features.
2. F-18 ungated routes give commercial (not tenant-isolation) exposure.
3. Set `DJI_WEBHOOK_SECRET` before enabling the DJI integration; until then it returns 503.
4. Downgrading 0061 fails if two suites share a plan code.

## 26. Recommended next work
1. Verify subscriptions for every production org before deploying.
2. Decide gating for telemetry/release_readiness and seed plans accordingly.
3. Extend `test_api_no_500_smoke.py` (added in this pass; ORG_ADMIN only) to more roles and to the
   platform/upload/export operations it currently skips.
4. Reconcile schema drift with a corrective migration; then enable autogenerate checks in CI.
5. MAVLink: use `seq`/`compid`, add out-of-order/duplicate/late-packet tests.
6. Enforce ruff/mypy in CI incrementally.
