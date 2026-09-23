# M19.1 — Invite ORG_ADMIN to an Existing Organization — Session Report

Date: 2026-09-19
Environment used for all verification: **LOCAL ONLY** — native Postgres 16 on `localhost:55432` (dev DB `aerocomply_dev`, test DB `aerocomply_test`, both already at Alembic head), backend `uvicorn` on `http://127.0.0.1:8001` (restarted once mid-session to load the new route — it runs without `--reload`), frontend build verified via `next build`/`tsc`/`eslint`/`vitest` (not run live in a browser this session — see item 12). Staging (`aerocomply-backend-staging`, Neon `small-meadow-85982633`) and production Neon (`bitter-tooth-52841705`) were never touched, queried, or written to. No push to `origin/main`.

**Note on referenced context file**: `M18_1_INTEGRATION_MATRIX.md` does not exist in this repo (confirmed by direct file listing). `M19_REPORT.md` exists and was read in full before starting; it explicitly documents that no invitation endpoint existed at all ("no user-invitation endpoint in this codebase ... `register-organization` only ever creates an `ORG_ADMIN`"), which this session addresses for the platform-admin-invites-an-org-admin case specifically.

---

## 1. What existed before this session

Inspected `backend/app/models`, `backend/app/services`, `backend/app/api/v1`, `frontend/lib/api`, `frontend/app` for "invite/invitation/activation/onboarding" concepts first, per instructions. Found a **fully real, already-working invitation primitive**, just not exposed for an already-existing organization:

- `AuthVerificationCode` (`backend/app/models/auth_verification.py`) — one shared, hashed, single-use, time-limited OTP table backing email verification, password reset, and `ACCOUNT_ONBOARDING` (Phase 18.3).
- `auth_service.request_account_onboarding` / `complete_account_onboarding` — issues and consumes the OTP, sets the invitee's own password, marks `email_verified`, records `auth.onboarding_email_requested` / `auth.onboarding_completed` audit events.
- `provisioning_service.provision_organization` — composes `platform_service.create_organization` + `subscription_service.create_subscription` + `platform_service.create_organization_admin` (random, immediately-discarded password) + `auth_service.request_account_onboarding`, but **only as part of creating a brand-new organization and subscription together**. There was no way to invite an admin into an organization that already exists without also spinning up a new subscription.
- `POST /platform/organizations/{organization_id}/admins` (pre-existing) — creates an admin in an existing org, but takes a **caller-supplied plaintext password** (`OrganizationAdminCreateRequest.password`) set directly by the platform admin — not a real invite-by-email flow, and violates the "Super Master never sets or sees the new admin's password" principle documented elsewhere in this codebase. Left in place unmodified (existing tests may depend on it); not used by the new invite flow.
- `frontend/app/onboarding/complete/page.tsx` — a public, unauthenticated invitation-acceptance page already existed and already validates everything server-side (email + OTP code + new password against `/auth/onboarding/complete`); it needed **no changes** to work with the new invite path, since it is decoupled from how the OTP was originally issued.

**Decision on data model**: extended the existing `AuthVerificationCode` + `User`/`UserRole`/`Organization` primitives rather than introducing a first-class `Invitation` model. Reasoning: the mission's own suggested `Invitation` fields (email, organization_id, role, inviter, expiration, accepted_at) are already fully represented by the *combination* of a `User` row (organization_id + role via `UserRole`, created at invite time) plus an `AuthVerificationCode` row (hashed token, expiration, single-use consumption) plus `AuditEvent` rows (inviter, timestamps). Introducing a second, parallel invitation-token system would duplicate exactly the primitive this codebase already uses for two other flows (email verification, password reset) and was explicitly built in Phase 18.3 anticipating this exact use case (see that module's own docstring: "Sent by platform tenant provisioning right after an invited admin user is created"). This satisfies constraint #6 (no second auth/invitation system).

## 2. What was implemented

One new orchestration function and one new endpoint, composing existing, already-tested pieces — no new tables, no new auth mechanism:

- `provisioning_service.invite_organization_admin(db, *, actor_user_id, organization_id, email, full_name)` — the narrower sibling of `provision_organization` for an **already-provisioned** organization. Calls `platform_service.create_organization_admin` with a random, immediately-discarded password, then `auth_service.request_account_onboarding`. Email-send failure does not roll back the created account (mirrors `provision_organization`'s own compensation rule); recorded as its own audit event and reported via `onboarding_email_sent: false` so the platform admin can retry via the pre-existing `POST /platform/admins/{user_id}/resend-invitation` endpoint.
- `POST /platform/organizations/{organization_id}/invite-admin` (`backend/app/api/v1/platform.py`) — `PLATFORM_MANAGE`-gated, request body `{email, full_name}` only (no password field exists on the request schema at all — `OrganizationAdminInviteRequest`).
- Frontend: an "Invite Org Admin" panel added to the Platform Admin organization detail page (`frontend/app/(app)/platform/organizations/[organizationId]/page.tsx`), calling `platformApi.inviteOrganizationAdmin` (`frontend/lib/api/platform.ts`). Reuses the existing, unmodified `/onboarding/complete` public page for acceptance.

## 3. Files changed

- `backend/app/api/v1/platform.py` — new `invite_organization_admin` route.
- `backend/app/schemas/platform.py` — new `OrganizationAdminInviteRequest` / `OrganizationAdminInviteResponse`.
- `backend/app/services/provisioning_service.py` — new `invite_organization_admin` + `InviteOrganizationAdminResult`.
- `backend/tests/integration/test_provisioning.py` — new `TestInviteAdminToExistingOrganization` class (6 tests; no existing tests modified or deleted).
- `frontend/lib/api/platform.ts` — new `inviteOrganizationAdmin` client method.
- `frontend/app/(app)/platform/organizations/[organizationId]/page.tsx` — new "Invite Org Admin" UI panel.

No other files touched. `frontend/next-env.d.ts` was auto-modified by tooling and reverted before committing (not part of this change).

## 4. Database changes / migrations

**None needed.** No schema change — reuses `AuthVerificationCode`, `User`, `UserRole`, `Organization`, `AuditEvent` exactly as they exist today. No migration was created; none was necessary.

## 5. API endpoints

New: `POST /api/v1/platform/organizations/{organization_id}/invite-admin` → `201`, body `{id, email, full_name, onboarding_email_sent}`. Gated on `Permission.PLATFORM_MANAGE`. 404 if the organization doesn't exist; 409 if the email is already in use anywhere (see Section 9).

Reused unmodified: `POST /api/v1/auth/onboarding/complete` (accept + set password), `POST /api/v1/platform/admins/{user_id}/resend-invitation`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`, `GET /api/v1/users`.

## 6. Email architecture

Unchanged, reused as-is: `email_service.send_verification_code_email` → console-sink `ConsoleEmailSender` (confirmed in `backend/.env`: no `SMTP_HOST` set, so the app falls back to console capture — no real email was ever sent this session). Verified live in the uvicorn log:
```
EMAIL (console sink, SMTP not configured) to=curl-orga-admin@example.com subject='KOTA AEROSPACE — Account setup code'
Your account setup code is: 649720
```

## 7. Invitation security

- Token: the existing `AuthVerificationCode` OTP — cryptographically random, **stored hashed** (not raw — matches the existing password-reset/email-verification convention; confirmed by reading `auth_verification.py`/`auth_service._issue_code`), single-use (`_consume_code` marks it consumed; replaying the same code returned `401 Invalid or expired code` in live verification), time-limited (10 minutes, per the captured email text).
- No password ever passes through the invite endpoint, its request schema, or its response — the platform admin never sees or sets it (random `secrets.token_urlsafe(32)`, immediately discarded).
- organization_id is taken only from the server-validated path parameter; `create_organization_admin` 404s if it doesn't exist. Never trusted from any other client input.

## 8. RBAC verification

- `PLATFORM_MANAGE` required: a tenant `ORG_ADMIN` calling the invite endpoint got `403` (test: `test_only_platform_admin_can_invite`; live-verified: org A's own new admin got `{"message":"Missing required permission: platform:manage"}` / `403` when attempting to invite into org B).
- Unauthenticated: `401` (test: `test_unauthenticated_rejected`).

## 9. Edge cases handled

- **Nonexistent organization** → `404` (test + live-verified via the initial pre-restart curl attempt, which correctly differs from routing 404 — confirmed via the dedicated test using a random UUID against a running server post-restart).
- **Duplicate email** (covers "existing user with no org", "existing user in another org", and "already a member of this org" — all rejected identically, matching the pre-existing `create_organization_admin` global-uniqueness convention rather than silently moving/merging accounts) → `409` (test: `test_duplicate_email_rejected`).
- **Expired/replayed invitation code** → `401 Invalid or expired code` (live-verified: replaying the already-consumed code failed).
- **Revoked invitation**: **NOT IMPLEMENTED.** There is no revoke action for a pending `ACCOUNT_ONBOARDING` code distinct from letting it expire; out of scope for this slice (mission said "only if you implement revoke" — not implemented).
- **Login before acceptance** → `401` (random discarded password is unusable; live-verified).

## 10. Tenant isolation results

**PROVEN**, both via automated test and live HTTP against local Postgres:
- New org A admin's `GET /users` returns only org A's own user, never org B's (test + live curl).
- New org A admin cannot invite into org B, cannot list platform organizations, cannot read org B's entitlements — all `403 Missing required permission: platform:manage` (org-scoped role has no `PLATFORM_MANAGE` grant at all, so this is enforced at the permission layer, not by an organization-id comparison that a manipulated UUID could bypass).
- An invitation issued for org A can only ever activate a `User` row already permanently bound to org A's `organization_id` at creation time — there is no code path where accepting an invitation lets the caller choose or change the organization.

## 11. Audit events

Verified live by querying `audit_events` directly in `aerocomply_dev` for the test organization, in order:
```
platform.organization.create
platform.organization.admin_created
auth.onboarding_email_requested
auth.onboarding_completed
auth.login  (x2 — the blocked pre-acceptance attempt is a 401 with no event; the two rows are the successful post-acceptance logins)
```
All four "at each step" events the mission asked for (org exists, admin created, invite email sent, invitation accepted) are present and immutable — confirmed the hard way: attempting to `DELETE` these rows for cleanup was **rejected by a database trigger** (`audit_events is append-only: DELETE is not permitted`), so the local dev-DB test rows from this session's live verification (orgs "M19.1 Curl Org A/B", users `curl-orga-admin@example.com` / `curl-orgb-admin@example.com`, platform admin `m19-1-platform-admin@example.com`) were **left in place** rather than force-deleted — they are local-only, harmless, and their audit trail is (correctly, by design) immutable.

## 12. Browser verification

**NOT PERFORMED THIS SESSION.** Browser tooling was not exercised for this task; verification was done via targeted pytest integration tests plus direct `curl` calls against the real local `uvicorn` + local Postgres (see Section 15), not a driven browser session. The frontend UI panel was type-checked, linted, and built successfully (Sections 17–19) but **was not clicked through in an actual browser** — this is an explicit gap, not a claimed-and-skipped step.

## 13. PostgreSQL verification

Performed directly (not just via the ORM/API): queried `audit_events` table rows by `organization_id` after the live curl flow and confirmed all four expected audit actions exist in the real `aerocomply_dev` database in the correct order (Section 11). Also confirmed the OTP codes captured from the console-sink log were the actual values consumed successfully by `/auth/onboarding/complete`.

## 14. Backend test results

Targeted: `pytest tests/integration/test_provisioning.py` → **27 passed, 0 failed** (21 pre-existing + 6 new for the invite-admin slice), against `TEST_DATABASE_URL=postgresql+psycopg://postgres:aerocomplydevpw@localhost:55432/aerocomply_test` (native Windows Postgres on port 55432 — the same instance the dev app itself uses; Docker was not needed this session since a `aerocomply_test` database already existed on this port).

Full suite: `pytest` (backend, all tests) → **990 passed, 16 deselected, 0 failed**, 93.34s. No regressions from this session's changes.

## 15. Frontend test results

`npx vitest run` → **133/133 tests passed, 8/8 test files**. No new tests were added for the new UI panel (no existing pattern of component-level tests for platform-admin panels was found to extend, and adding a new test harness for one panel was judged lower-value than the backend integration coverage for this slice); this is a real gap, noted rather than hidden.

## 16. TypeScript result

`npx tsc --noEmit` → **clean, no errors.**

## 17. ESLint result

`npx eslint` on the two changed frontend files → **0 errors, 1 warning** (`react-hooks/set-state-in-effect` on line 241, calling `loadAll()` inside a `useEffect` — this is **pre-existing code, not introduced by this session's changes**; confirmed by checking the line is part of the original `useEffect` block, unmodified).

## 18. Production build result

`npm run build` → **succeeded**, all routes compiled including `/platform/organizations/[organizationId]` (dynamic route, unchanged route list from before this session).

## 19. Remaining limitations (explicit, not glossed over)

- **Browser/E2E verification: NOT COMPLETE.** Verified via automated integration tests + direct curl/Postgres inspection only, not a driven browser session (Section 12).
- **Invitation revocation: NOT IMPLEMENTED.** No way to invalidate a pending invite before it's accepted or expires, beyond letting the 10-minute OTP lapse.
- **No frontend automated test added** for the new "Invite Org Admin" panel (Section 15).
- **The older `POST /organizations/{organization_id}/admins` endpoint (caller-supplied password) was left in place, unmodified.** It is a weaker, pre-existing pattern that arguably should be deprecated in favor of the new invite-by-email endpoint, but removing/changing it was out of scope (constraint: don't touch what isn't necessary, don't delete existing tests) and is flagged here rather than silently left inconsistent.
- **"Existing user in another org" is rejected, not offered a choice** (e.g., no "move this user" or "add as a second membership" flow) — matches the mission's instruction to reject rather than silently move accounts, but is a hard rejection with no admin-facing remediation UI beyond "use a different email."
- Local dev-DB test data from live verification (two throwaway organizations, three throwaway users, and their audit trail) was **not** cleaned up, because the audit trail is correctly immutable at the DB level (Section 11) and forcibly deleting the users/orgs without their audit rows would leave dangling audit references. This is inert local-only data, not staging/production.

## 20. Staging / production untouched confirmation

- Staging (Render `aerocomply-backend-staging`, Neon `small-meadow-85982633`): **not queried, not connected to, not migrated.** No staging URL or credential appears anywhere in this session's commands.
- Production Neon (`bitter-tooth-52841705`): **not touched at all.**
- No push to `origin/main`. All work is local commits only.
- No new Alembic migration was created (none was needed), so there is nothing that could accidentally run against staging/production schemas.

## 21. Local commit hash

`028dc76` — `feat(platform): invite an ORG_ADMIN into an existing organization by email`, on branch `main`, 6 files changed, 392 insertions, 0 deletions. This is a new commit created this session (not an amend); the repo's prior head was `abc2e86`.

---

## Final status

**This one slice — PLATFORM_ADMIN invites an ORG_ADMIN into an existing organization by email, with a secure single-use hashed token, real local console-captured email, server-side-validated acceptance, tenant-scoped account activation, RBAC enforcement, tenant isolation, and audit events at each step — is implemented and verified end-to-end via automated tests (27/27 targeted, 990/990 full backend suite) and live curl/Postgres inspection against a real local `uvicorn` + Postgres instance.**

**NOT COMPLETE / explicitly out of scope for this session:** live browser-driven verification of the new UI panel and the acceptance page; invitation revocation; a frontend automated test for the new panel. These are named explicitly here rather than implied as done.
