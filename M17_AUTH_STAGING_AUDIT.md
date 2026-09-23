# M17 Auth / Staging Migration Checkpoint Audit

Date: 2026-09-19
Scope: read-only audit. No file was modified, no migration was run, no database was written to.

---

## 1. Current Authentication Architecture

**User creation.** Two paths exist, both DB-backed:
- `auth_service.register_organization` (`backend/app/services/auth_service.py:57`) — public self-serve signup. Creates an `Organization` row and a `User` row, then `db.add(UserRole(user_id=user.id, role_name=Role.ORG_ADMIN.value, organization_id=org.id))` (line 79). The caller cannot choose their own role — `ORG_ADMIN` is hardcoded server-side for the first user of a new org.
- `backend/scripts/create_platform_admin.py` — a one-time, operator-run CLI bootstrap script (no HTTP endpoint exists for this by design; see the script's docstring: "There is deliberately no public API endpoint for this (PLATFORM_MANAGE cannot be self-granted...)"). It reuses `app.core.security.hash_password` and the real `User`/`UserRole`/`Organization` models, reads `DATABASE_URL` from the environment, and is idempotent (no-ops if the email already exists). This **is** the existing seed/bootstrap mechanism for the first `PLATFORM_ADMIN` — I searched for "seed"/"bootstrap"/"create_admin"/"superuser" and this script plus `backend/scripts/seed_product_catalog.py` (unrelated — product catalog only) are the only hits.

**Password hashing.** `backend/app/core/security.py:11`: `pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")`, using `passlib`. Confirmed as a real dependency in `backend/pyproject.toml` (argon2-cffi/passlib present). `hash_password`/`verify_password` wrap this context (lines 16-21). A fixed `DUMMY_PASSWORD_HASH` (line 31) is verified against on a nonexistent-user login to prevent a timing side-channel that would otherwise let an attacker enumerate registered emails — a real, deliberate hardening measure, not a placeholder.

**PLATFORM_ADMIN representation.** Not a boolean flag — it's a `Role` enum value (`backend/app/core/permissions.py:97`) granted via a `UserRole` join-table row, same mechanism as every other role. `Role.PLATFORM_ADMIN` maps to `{PLATFORM_MANAGE, PLATFORM_ENTITLEMENT_OVERRIDE}` (permissions.py:257-260). A `PLATFORM_ADMIN` user still belongs to exactly one `organization_id` (per the model's comment, permissions.py:92-96) — cross-tenant `/platform/*` routes work by *not* filtering on that org_id, not by the user having none.

**Organization/tenancy model.** `backend/app/models/organization.py` — `Organization` is its own table with a `status` (`OrganizationStatus`, includes `SUSPENDED`). `User` (`backend/app/models/user.py:10`) inherits `TenantScopedMixin`, giving it a mandatory `organization_id`. Roles are per-org via `UserRole(user_id, role_name, organization_id)` (user.py:22-35) — a user's role is scoped to the org named on that specific `UserRole` row, not global.

**JWT/session claims.** `backend/app/core/security.py:46-65`, `create_access_token`: claims are `sub` (user id), `type: "access"`, `organization_id`, `roles` (list), `email`, `full_name`, `email_verified`, plus `iat`/`exp`/`jti`. Refresh tokens (line 68) carry only `sub`, `organization_id`, `type: "refresh"` — deliberately no roles, forcing a DB re-lookup on refresh.

**Can the client supply organization_id/role, and does the server trust it? No.**
- `LoginRequest` (used by `POST /auth/login`, `backend/app/api/v1/auth.py:77`) only carries `email`/`password` — no org_id/role field exists on the wire at all.
- `get_current_user` (`backend/app/core/deps.py:24-65`) is, per its own docstring (deps.py:28-30), "the ONLY place org_id is trusted from — never from a request body/query param." It derives `organization_id` and `roles` **solely** by decoding and verifying the JWT (`decode_token`, HS256/whatever `settings.jwt_algorithm` is, secret from `settings.jwt_secret_key`) — never from any request body/query param.
- On every request it additionally re-checks the organization's live status in the DB (`org = db.get(Organization, organization_id); if org.status == SUSPENDED: raise Unauthorized`, deps.py:52-54) — explicitly to close the gap where a token issued before a suspension would otherwise keep working for its full TTL. Login (`auth_service.authenticate`, line 107) and refresh (line 140) independently re-check the same thing.
- `require_permission`/`require_feature` (deps.py:68-140) both derive their authorization decision only from the already-validated `CurrentUser`, never from anything else in the request.
- I grepped every file under `backend/app/api/v1` for `organization_id` usage; none of the 34 route files accept it as a body/query field for authorization purposes (all references are either the trusted `CurrentUser.organization_id` or path params for platform cross-tenant admin routes gated by `PLATFORM_MANAGE`).

**Hardcoded/local-only credentials.** I grepped `backend/app` and `frontend` for password/secret/credential-looking literals (`password\s*=\s*['"]`, `admin@`, `test123`, `changeme`, `hardcoded`, etc.). No hardcoded credentials, backdoor accounts, or test-only auth bypasses were found in application code. The only real matches were comment prose (e.g. `regulatory_document.py:35` uses the word "hardcoded" describing an unrelated DB column, not a credential) and unrelated frontend files (branding/mock-integration modules, not auth). **Conclusion: no gap found here**, though a grep-based sweep can't prove universal absence — nothing suspicious surfaced.

**Verdict for section 1:** the auth architecture is already fully database-backed, with server-side-only trust of org/role via a verified JWT, live per-request organization-suspension re-checks, and no client-supplied identity fields anywhere in the login/authorization path.

---

## 2. Database / Migration State

**Local migration chain** (`backend/alembic/versions/`): a single, clean, linear chain 0001 → 0035 with no branch points (verified by walking every file's `revision`/`down_revision` pair). Local head: **0035** (`0035_task_evidence_required.py`, adds `tasks.evidence_required`, `down_revision = 0034`).

**Staging Neon database — actual current state (read-only, verified live):**
- Project `small-meadow-85982633` ("Kota Aerospace Staging") has exactly one branch, `production` (br-fragrant-pond-b4nvtrj4), reported logical size ~30 MB.
- I opened a genuinely read-only `psycopg` connection to that branch's `neondb` database and ran:
  - `SELECT version_num FROM alembic_version;` → **`psycopg.errors.UndefinedTable: relation "alembic_version" does not exist`**
  - `SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema NOT IN ('pg_catalog','information_schema') …` → **zero rows returned**
  - `SELECT schema_name FROM information_schema.schemata;` → only `public`, `information_schema`, `pg_catalog`, `pg_toast` (no application schema/objects at all)
- **Finding: the staging database is completely empty.** No `alembic_version` table, no application tables, no schema objects whatsoever. This is not "N migrations behind" in the usual sense — it has **never had any migration applied**. All 35 migrations (0001→0035) are pending against it.
- No write, DDL, or `alembic upgrade/downgrade` command was run — only plain `SELECT` statements against information_schema and the (nonexistent) `alembic_version` table.
- I could not explain the ~30 MB "logical_size" Neon reports for an empty schema from read-only SQL alone (Postgres/Neon storage overhead, WAL, or the number simply reflecting the base template — I did not speculate further; flagging as unverified rather than guessing).

---

## 3. Is Any Code Change Needed to Make Auth "Fully DB-Backed"?

**No code change is required.** Based on direct reading of `auth_service.authenticate`, `auth_service.register_organization`, `deps.get_current_user`, `deps.require_permission`, `deps.require_feature`, and the `LoginRequest`/`CurrentUser` schemas:
- User existence, password verification, role assignment, and organization membership are already 100% sourced from the database on every request.
- The JWT is a signed cache of a DB-verified fact set (id/org/roles/email) checked against a live re-read of `Organization.status` on every authenticated request — not a substitute for DB trust.
- There is no mock/in-memory/hardcoded user store anywhere in the auth path.

The premise in the task ("might not be fully DB-backed") does not hold against this codebase as written — this is a mature, already-hardened implementation (explicit timing-attack mitigation, per-request suspension re-checks, rate limiting on every unauthenticated auth endpoint, RBAC enforced at the dependency/service layer per `permissions.py`'s own docstring, not just in the frontend).

---

## 4. Do the Pending Uncommitted M17.6 Changes Affect Migrations 0033-0035?

`git status` shows uncommitted/untracked changes in:
- Modified: `backend/app/models/task.py`, `backend/app/schemas/release_readiness.py`, `backend/app/services/release_readiness_service.py`, `backend/tests/unit/test_release_readiness_service.py`, and three frontend files (evidence panel, release-readiness API client, `next-env.d.ts`).
- Untracked: `M17_6_AUDIT.md`, `M17_6_REPORT.md`, `M17_FINAL_VALIDATION_REPORT.md`, `M17_TESTING_REPORT.md` (report artifacts, not code), and **`backend/alembic/versions/0035_task_evidence_required.py` itself is untracked** (i.e., migration 0035 has never been committed to git).

Migration identities and purposes (all read directly):
- **0033** (`0033_installation_history.py`, already committed, `down_revision=0032`): purely additive — creates two new tables, `battery_installations` and `component_installations`, each with FK constraints (`RESTRICT`) to `batteries`/`components`/`assets`, plus a partial unique index enforcing "at most one open (unremoved) installation per item." No existing table/column is touched.
- **0034** (`0034_battery_component_maintenance.py`, already committed, `down_revision=0033`): purely additive — adds nullable `battery_id`/`component_id` FK columns (`RESTRICT`) to the existing `maintenance_requirement_applicabilities` and `maintenance_accomplishments` tables, plus indexes. No column is dropped, renamed, or made non-nullable.
- **0035** (`0035_task_evidence_required.py`, **currently uncommitted/untracked**, `down_revision=0034`): adds `tasks.evidence_required BOOLEAN NOT NULL`, backfilled via `server_default=false` then the default is dropped (`op.alter_column(..., server_default=None)`) — the standard safe two-step pattern for adding a NOT NULL column to a populated table. Its own docstring confirms: "Backfilled to `false` for every existing task, so no pre-existing task retroactively becomes an evidence blocker."

**Relevance to the staging migration decision:** since staging has zero tables (Section 2), none of 0033/0034/0035 is "risky" in the usual sense of altering live populated data — they'd all run against an empty schema regardless. The one real implication is procedural: **migration 0035 is uncommitted.** If "apply migrations to staging" means running `alembic upgrade head` from a deployed backend build, that build must first have 0035 (and the corresponding `task.py`/`release_readiness_service.py` model/service changes it supports) committed and included in whatever revision gets deployed to the staging Render service — otherwise the deployed code and the migrated schema could disagree (deployed code expecting `Task.evidence_required` to exist, migration not yet run, or vice versa).

---

## 5. Exact Staging Actions and Their Blast Radius

**What `alembic upgrade head` against the staging Neon `production` branch would actually do**, in order (staging is currently at *no revision* — pre-0001):

| Migration | One-line effect |
|---|---|
| 0001_initial_foundation | Creates the foundational schema (organizations, users, core MRO tables) |
| 0002_audit_events_immutability | Adds audit_events table/immutability constraints |
| 0003_mro_domain_slice | Adds core MRO domain tables |
| 0004_inspection_rejection_reason | Adds inspection rejection reason field |
| 0005_parts_vendors | Adds parts/vendors tables |
| 0006_part_requirements | Adds part_requirements table |
| 0007_inventory_transactions | Adds inventory_transactions table |
| 0008_vendor_fit | Adds vendor fit/matching data |
| 0009_procurement_requests | Adds procurement_requests table |
| 0010_purchase_orders | Adds purchase_orders table |
| 0011_aog_events | Adds AOG (aircraft-on-ground) events table |
| 0012_maintenance_program | Adds maintenance program tables |
| 0013_deferred_items | Adds deferred_items table |
| 0014_compliance | Adds compliance tables |
| 0015_regulatory_documents | Adds regulatory_documents table |
| 0016_part_traceability_and_quarantine | Adds part traceability/quarantine fields |
| 0017_warehouse_location | Adds warehouse location tables |
| 0018_technician_qualifications | Adds technician_qualifications table |
| 0019_lisa_conversation_context | Adds LISA (AI assistant) conversation context table |
| 0020_assessment_domain | Adds assessment domain tables |
| 0021_organization_status | Adds Organization.status (ACTIVE/SUSPENDED etc.) |
| 0022_import_jobs | Adds import_jobs table |
| 0023_aircraft_registration_unique | Adds unique constraint on aircraft registration |
| 0024_platform_control_plane_m1 | Adds platform control-plane tables (cross-tenant admin) |
| 0025_approval_requests | Adds approval_requests (governance/four-eyes) table |
| 0026_evidence_files | Adds evidence_files table |
| 0027_asset_foundation | Adds generic Asset foundation table |
| 0028_product_catalog | Adds product catalog tables |
| 0029_auth_verification_codes | Adds auth_verification_codes table (OTP/email verify/reset) |
| 0030_facilities | Adds facilities table |
| 0031_mro_asset_repointing | Repoints MRO tables at generic Asset |
| 0032_drone_operations | Adds drone/battery/component operations tables |
| 0033_installation_history | Adds battery_installations/component_installations tables (additive) |
| 0034_battery_component_maintenance | Adds battery_id/component_id nullable FKs to maintenance tables (additive) |
| 0035_task_evidence_required | Adds tasks.evidence_required NOT NULL boolean, backfilled false (additive) |

Since the target database is empty, this is equivalent to **standing up the entire schema from scratch** rather than an incremental change to live data — there is no existing row anywhere on staging that any migration could corrupt, drop, or lose. The blast radius of running `alembic upgrade head` on staging is: creation of ~35 migrations' worth of tables/columns/indexes/constraints on an otherwise-empty database. Nothing to lose, but also nothing yet to validate against (no existing staging users/orgs/data to smoke-test against post-migration — everything downstream, including any manual QA, starts from zero).

**What creating a PLATFORM_ADMIN + organization + ORG_ADMIN would insert**, using `create_platform_admin.py` plus `register_organization`:
- 1 row in `organizations` (e.g. "Platform Operations") for the platform admin's own org.
- 1 row in `users` (email, `hashed_password` = argon2 hash of whatever password is chosen, `full_name`, `is_active=true`).
- 1 row in `user_roles` (`role_name='PLATFORM_ADMIN'`, tied to that org).
- Separately, if a customer org + its first ORG_ADMIN is also created (via `register_organization` or platform provisioning), that's another `organizations` row, another `users` row, another `user_roles` row (`role_name='ORG_ADMIN'`).
- No other tables are touched by either path — no audit_events row is written by the bootstrap script itself (only `auth_service.authenticate`/`register_organization` write `audit_events`, and only on actual login/registration calls, not by the raw DB-insert bootstrap script).

---

## 6. Risks

- **Staging has never been migrated — it is not "a few migrations behind," it is at zero.** This is unusual for an environment presumed to already be in some deployed state; worth confirming with the user whether this is expected (e.g., staging DB was just (re)provisioned) or a sign that a previous deploy never actually ran migrations against it.
- **Migration 0035 is uncommitted in git.** Running `alembic upgrade head` from a deployed build that doesn't include 0035 would stop at 0034, silently leaving the backend's `Task.evidence_required` code (already modified in the working tree) without its column if that code were ever deployed ahead of the migration. Recommend committing 0035 (and its associated model/service changes) before triggering any staging deploy+migrate cycle, to keep code and schema state in lockstep.
- **No destructive operations found** in 0033-0035 — all are additive (new tables or nullable-then-tightened columns with safe backfills). No `DROP COLUMN`/`DROP TABLE`/renames in the pending set.
- **No auth architecture gap found** — org_id/role are never client-supplied and trusted; every authorization decision traces back to a server-verified JWT plus a live DB re-check of organization status. I looked specifically for a client-trusted org_id or a missing 403 and found none in `deps.py`, `auth_service.py`, or the 34 route files' use of `organization_id`.
- **Could not independently verify** the ~30 MB Neon-reported logical size against an apparently-empty schema; flagged rather than explained away.
- Render service env vars: per the task's own instructions, the four required staging env vars (`DATABASE_URL` → small-meadow-85982633, `JWT_SECRET_KEY`, `ENVIRONMENT`, `CORS_ALLOW_ORIGINS`) were already user-confirmed present via the dashboard; I did not re-fetch values (values were intentionally not queried, per the read-only constraint against materializing secrets).

---

## 7. Recommended Execution Order (plan only — nothing below was executed)

1. Commit the currently-uncommitted M17.6 changes, in particular `backend/alembic/versions/0035_task_evidence_required.py` together with the `task.py`/`release_readiness_service.py`/`release_readiness.py` (schema) changes it supports, so code and migration travel together.
2. Deploy that commit to the staging Render service (`srv-dajhh1nqj5pc73dldeog`) — or otherwise get a backend build containing all of 0001-0035 available to run against staging.
3. Run `alembic upgrade head` against the staging Neon `production` branch (small-meadow-85982633) from that build. Since the target is empty, this creates the full schema (0001→0035) in one pass.
4. Verify via a read-only `SELECT version_num FROM alembic_version;` that it now reads `0035`, and spot-check a couple of expected tables/columns (e.g. `tasks.evidence_required` exists) exist as expected.
5. Use the existing bootstrap script `backend/scripts/create_platform_admin.py` (pointed at staging's `DATABASE_URL`) to create the first `PLATFORM_ADMIN` user — pass a securely-generated throwaway `--password` that only the user will use once, then immediately drive it through the existing `forgot-password` → `reset-password` OTP flow (`POST /auth/forgot-password` then `POST /auth/reset-password`) so no one but the user ever has a memorized password for that account.
6. If a first customer organization + `ORG_ADMIN` is also needed for staging testing, use `POST /auth/register-organization` (self-serve endpoint, already fully DB-backed per Section 3) rather than another manual DB insert — it's the same code path production users would hit.
7. Verify login end-to-end against staging: `POST /auth/login` with the new admin credentials, confirm a valid JWT with the expected `roles`/`organization_id` claims comes back, then `GET /auth/me` with that token to confirm `get_current_user` resolves it correctly against the live staging DB.
8. Only after 3-7 succeed, consider staging "ready" for further QA — there is currently no existing staging data to preserve, so none of the above carries data-loss risk, only the ordinary risk of a first-time schema stand-up (e.g., a migration failing partway on an environment-specific Postgres extension/permission difference from local/CI).
