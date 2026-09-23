# M19.2 — Closing M19.1's Gaps: Revocation, Frontend Test, Browser Verification

Date: 2026-09-19
Environment: **LOCAL ONLY** — native Postgres 16 on `localhost:55432` (`aerocomply_dev` / `aerocomply_test`), backend `uvicorn` on `http://127.0.0.1:8001` (restarted once, no `--reload`, to load the new route), frontend `next dev` on `http://localhost:3000`. Staging (`aerocomply-backend-staging`, Neon `small-meadow-85982633`) and production Neon (`bitter-tooth-52841705`) were never touched, queried, or connected to. No push to `origin/main`.

---

## 1. M19.2 summary

M19.1 shipped PLATFORM_ADMIN → invite ORG_ADMIN into an existing org, and explicitly flagged three gaps as NOT COMPLETE: (1) real browser-driven E2E verification, (2) invitation revocation, (3) a frontend test for the invite panel. This session closes all three, without redesigning the existing `AuthVerificationCode`-based invitation mechanism.

## 2. M19.1 components reused

- `AuthVerificationCode` model / `VerificationPurpose.ACCOUNT_ONBOARDING` (`backend/app/models/auth_verification.py`) — unmodified.
- `auth_service.request_account_onboarding` / `complete_account_onboarding` — unmodified.
- `provisioning_service.invite_organization_admin`, `POST /platform/organizations/{id}/invite-admin` — unmodified.
- `frontend/app/onboarding/complete/page.tsx` (public acceptance page) — unmodified.
- `frontend/app/(app)/platform/organizations/[organizationId]/page.tsx` "Invite Org Admin" panel — extended in place (revoke action added), not rebuilt.

## 3. Revocation implementation

**Checked first, per instructions**: `AuthVerificationCode.consumed_at` (`backend/app/models/auth_verification.py:57`) already gives `_consume_code` (`backend/app/services/auth_service.py:177-208`) a "used up" state — `row.consumed_at is not None` is treated identically to expired/wrong/missing, always `401 Invalid or expired code`. So revocation = set `consumed_at` on the latest pending code **without ever setting a password**. No new table, no new token system.

- `auth_service.revoke_account_onboarding(db, *, actor_user_id, user_id)` — `backend/app/services/auth_service.py:329-372`. Looks up the latest `ACCOUNT_ONBOARDING` code for the user; if none exists or it's already consumed, raises `ConflictError` (409, `no_pending_invitation`) — this is what makes it safe against double-revoke and against revoking an already-accepted account (accepting sets `consumed_at` too, so there's nothing left to revoke). On success: sets `consumed_at = now()`, records `platform.organization.invitation_revoked`, commits.
- Checked `backend/app/core/permissions.py` before assuming ORG_ADMIN scope — confirmed (same as M19.1's own finding) that only `PLATFORM_MANAGE` gates this class of action; ORG_ADMIN's role has no grant for it, so ORG_ADMIN revoke capability was **not** added (matches mission instruction: only add it if the permission model already clearly supports it).

## 4. API changes

New: `POST /api/v1/platform/admins/{user_id}/revoke-invitation` → `200 {"message": "Invitation revoked."}` — `backend/app/api/v1/platform.py:142-155`. Gated on `Permission.PLATFORM_MANAGE`, same as `resend-invitation` immediately above it (`platform.py:132-139`), which it sits next to. 404 if the user doesn't exist, 409 if there's nothing pending to revoke, 401 unauthenticated, 403 for any caller without `platform:manage` (including a legitimate ORG_ADMIN from *any* organization — enforced at the permission layer, not by an organization-id comparison).

No other endpoints changed. No new schema needed (route returns the existing `MessageResponse`).

## 5. Frontend changes

- `frontend/lib/api/platform.ts` — new `platformApi.revokeAdminInvitation(accessToken, userId)` (`POST /platform/admins/{userId}/revoke-invitation`).
- `frontend/app/(app)/platform/organizations/[organizationId]/page.tsx` — the existing "Invite Org Admin" panel now: captures the invited admin's `id` from the invite response; shows a "Revoke Invitation" button next to "Send Invitation" once an invite succeeds; clicking it shows an inline "Revoke this invitation? [Confirm Revoke] [Cancel]" step (explicit confirmation before the irreversible action, per this codebase's UI convention); on success shows "Invitation to X revoked. It can no longer be accepted." and hides the now-stale success message; on failure shows the normalized API error. No new dashboard/list view was built — this stays inside the existing panel, as instructed.

## 6. Tests added

**Backend** (`backend/tests/integration/test_provisioning.py`, new `TestRevokeInvitation` class, 7 tests):
`test_only_platform_admin_can_revoke`, `test_unauthenticated_rejected`, `test_org_admin_from_another_org_cannot_revoke` (a real ORG_ADMIN in org B attempts to revoke org A's pending invite → 403), `test_nonexistent_user_404s`, `test_revoke_then_accept_fails_and_does_not_crash` (also asserts `platform.organization.invitation_revoked` audit row), `test_revoke_twice_is_conflict_not_crash`, `test_cannot_revoke_an_already_accepted_invitation` (accepts first, then revoke → 409, and the account still logs in normally afterward — proves revocation never rewinds an active account).

**Frontend** (`frontend/tests/platform-invitation.test.ts`, new file, 7 tests): tests `platformApi.inviteOrganizationAdmin` / `revokeAdminInvitation` against a mocked `fetch` — submit shape (no password field ever sent), success shape (including `onboarding_email_sent: false` not throwing), 409 duplicate-email normalization, 403 forbidden normalization, revoke submit/success, revoke 409 (already-accepted/already-revoked) normalization, revoke 404 normalization.

**Note on frontend test convention**: this repo has no React Testing Library configured anywhere (`package.json` has no `@testing-library/*`; every existing file under `frontend/tests/` — `entitlement-admin.test.ts`, `subscription.test.ts`, `maintenance.test.ts`, etc. — tests `lib/api/*` functions and pure helpers directly, never mounts a component). I followed that exact convention rather than introducing a new test-rendering dependency mid-slice. This is a real, meaningful gap relative to what the mission described ("renders correctly" as a mounted-component assertion) — flagged explicitly, not hidden. The added tests do exercise the real request/response contract the panel's `submitInviteAdmin` / `submitRevokeInvite` handlers call, including the validation-relevant shape (email/full_name only, no password) and every success/failure branch the panel renders differently for.

## 7. Browser verification — REAL BROWSER, performed this session

Using the Claude Browser pane against `http://localhost:3000` (frontend) + `http://127.0.0.1:8001` (backend, restarted to load the new route) + local Postgres. Steps actually driven through the UI:

1. Logged in as a freshly-created local `PLATFORM_ADMIN` (`m19-2-platform-admin@example.com`, inserted directly via a one-off script using `app.core.security.hash_password` since no admin-creation script exists in this repo — not through any API bypass of the app's own auth).
2. Navigated Platform Admin → Organizations; created "M19.2 Browser Org A" via the UI's "Create Organization" field.
3. Opened the org detail page, clicked "+ Invite Org Admin", filled email + full name, clicked "Send Invitation" → UI showed "Invitation sent to m19-2-browser-invitee@example.com." and a "Revoke Invitation" button appeared.
4. Pulled the OTP from the backend's console-sink log (`ConsoleEmailSender`, not a real email).
5. Opened `/onboarding/complete` in the browser, entered email + code + new password, submitted → "Your account is ready."
6. Logged in as the new ORG_ADMIN in the browser → dashboard rendered with "Viewing as: Organization Admin".
7. Navigated to `/platform/organizations` as this ORG_ADMIN → page shell loaded (no route guard) but the data call failed with the UI showing "Request Failed — Missing required permission: platform:manage" — no platform data leaked.
8. Logged back in as the platform admin, created a second org ("M19.2 Browser Org B") via the UI (cross-tenant target).
9. On Org A, sent a second invitation via the UI.
10. Clicked "Revoke Invitation" → confirmation step appeared ("Revoke this invitation? Confirm Revoke / Cancel") → clicked "Confirm Revoke" → UI showed "Invitation to m19-2-revoke-target@example.com revoked. It can no longer be accepted."
11. Attempted to accept that now-revoked invitation on `/onboarding/complete` with the OTP pulled from the log → UI showed "Invalid or expired code" — failed safely, no crash, no account activation.

**Honest scope statement**: steps above were driven through the actual rendered UI end-to-end for the invite → accept → login → role/context → platform-UI-blocked → second-invite → revoke-via-UI → revoked-acceptance-fails path. I did **not** additionally drive every Part 4 edge case (expired invitation via real 10-minute wait, malformed/garbage token, request-tampering, repeated-acceptance) through the browser — those were verified via direct `curl` against the same running backend instead (Section 9 below) and via the automated test suite, which is faster and equally conclusive for pure-backend-validation cases that have no distinct UI path. This is a partial-scope honest statement, not a claim of 100% UI-driven Part 4 coverage.

## 8. PostgreSQL verification (independent of the UI's own success messages)

Queried `aerocomply_dev` directly after the browser flow:
- `organizations`: both `M19.2 Browser Org A` and `M19.2 Browser Org B` present, `ACTIVE`.
- `users` in Org A: `m19-2-browser-invitee@example.com` (`is_active=True`, `email_verified=True`, role `ORG_ADMIN`) and `m19-2-revoke-target@example.com` (`is_active=True`, `email_verified=False` — never activated).
- `auth_verification_codes`: browser-invitee's `ACCOUNT_ONBOARDING` row has `consumed_at` set (from acceptance); revoke-target's row also has `consumed_at` set (from the revoke call, at a timestamp matching the UI action, not the OTP's original issue time) — same column, two different real causes, exactly as designed.
- `audit_events` for Org A, in order: `platform.organization.create`, `platform.organization.admin_created`, `auth.onboarding_email_requested`, `auth.onboarding_completed`, `auth.login`, `platform.organization.admin_created` (2nd invite), `auth.onboarding_email_requested` (2nd invite), `platform.organization.invitation_revoked`. All match the browser actions taken, in the right order, with no gaps.

## 9. Tenant isolation verification

- The new Org A ORG_ADMIN's session against `/platform/organizations` returned `403 Missing required permission: platform:manage` in the live browser session (Section 7, step 7) — enforced at the permission layer (the role grant itself), not by comparing organization ids, so a manipulated org id in a request can't bypass it.
- `test_org_admin_from_another_org_cannot_revoke` (new, automated): a real ORG_ADMIN from Org B attempts to revoke a pending invitation belonging to Org A's target user → `403`, same permission-layer enforcement.
- M19.1's own tenant-isolation tests (unchanged, still passing) continue to cover invite-side isolation.

## 10. Security verification — the 9 Part 4 edge cases

| # | Case | Method | Result |
|---|------|--------|--------|
| 1 | Expired invitation | Not re-verified this session (would require a real 10-minute wait or clock manipulation neither session did); relies on the same `_consume_code` expiry check M19.1 already verified and this session's tests re-exercise indirectly. | **NOT RE-VERIFIED** (inherited from M19.1, not regressed — `_consume_code`'s `row.expires_at < now()` branch is untouched code) |
| 2 | Revoked invitation cannot be accepted | Browser (Section 7, step 11) + curl + automated test | **PASS** |
| 3 | Already-used invitation cannot be reused | curl replay of the browser-invitee's already-consumed code → `401 Invalid or expired code` | **PASS** |
| 4 | Invalid/malformed code | curl with `code="000000"` against a real pending invitation's email → `401 Invalid or expired code` | **PASS** |
| 5 | Wrong organization context | Covered by tenant-isolation tests (Section 9) — an invitation is permanently bound to the organization_id at creation; there is no client-supplied org selection at acceptance time to tamper with | **PASS (by construction)** |
| 6 | Role manipulation via request tampering | `OrganizationAdminInviteRequest`/onboarding-complete schemas carry no role field at all — the role is always `ORG_ADMIN`, hardcoded server-side in `platform_service.create_organization_admin`; there is no field to tamper | **PASS (by construction)** |
| 7 | Unauthorized revoke attempt | `test_only_platform_admin_can_revoke`, `test_org_admin_from_another_org_cannot_revoke`, `test_unauthenticated_rejected` (automated) | **PASS** |
| 8 | Repeated acceptance attempt | curl replay (case 3) + `test_revoke_then_accept_fails_and_does_not_crash`'s equivalent path in M19.1's own full-flow test | **PASS** |
| 9 | Cross-tenant invitation access attempt | Section 9 | **PASS** |

## 11. Full test results (exact counts)

- Backend targeted (`pytest tests/integration/test_provisioning.py`): **34 passed, 0 failed** (27 from M19.1 + 7 new).
- Backend full suite (`pytest`): **997 passed, 16 deselected, 0 failed**, 94.68s (990 + 7 new; 0 regressions).
- Frontend targeted (`vitest run tests/platform-invitation.test.ts`): **7 passed, 1 file**.
- Frontend full suite (`vitest run`): **140 passed, 9 test files** (133 from before + 7 new; 0 regressions).
- `tsc --noEmit`: **clean, no errors.**
- `eslint` on all 3 changed/added frontend files: **0 errors, 1 warning** — the same pre-existing `react-hooks/set-state-in-effect` warning on `page.tsx`'s original `useEffect` (line unchanged by this session; already flagged in M19.1).
- `npm run build`: **succeeded**, all routes compiled including `/platform/organizations/[organizationId]`.

## 12. Files changed

- `backend/app/services/auth_service.py` — new `revoke_account_onboarding`.
- `backend/app/api/v1/platform.py` — new `revoke_admin_invitation` route.
- `backend/tests/integration/test_provisioning.py` — new `TestRevokeInvitation` class (7 tests).
- `frontend/lib/api/platform.ts` — new `revokeAdminInvitation` client method.
- `frontend/app/(app)/platform/organizations/[organizationId]/page.tsx` — revoke UI added to the existing invite panel.
- `frontend/tests/platform-invitation.test.ts` — new test file (7 tests).

`frontend/next-env.d.ts` was auto-modified by tooling during this session and reverted before committing (not part of this change, same as M19.1).

## 13. Local commit hash

`76bc749` — `feat(platform): revoke a pending org-admin invitation`, on branch `main`, 6 files changed. Prior head was `028dc76` (M19.1). Not pushed to `origin/main`.

## 14. Explicit staging status

**Untouched.** Render `aerocomply-backend-staging` and Neon `small-meadow-85982633` were never queried, connected to, or migrated. No staging URL or credential appears in any command run this session.

## 15. Explicit production status

**Untouched.** Neon `bitter-tooth-52841705` was never touched, queried, or connected to at any point.

## 16. Remaining NOT COMPLETE items

- **Expired-invitation edge case was not freshly re-verified this session** (Section 10, row 1) — it relies on unmodified, previously-tested code (`_consume_code`'s expiry branch), not on anything this session changed, but a real 10-minute-wait or clock-mocked test was not run.
- **No React Testing Library / mounted-component test exists for the panel** — the added frontend tests cover the panel's API-layer behavior (the exact calls and response handling `submitInviteAdmin`/`submitRevokeInvite` perform) via this repo's existing convention (testing `lib/api/*` directly), not a rendered-DOM assertion, because no component-test tooling exists anywhere in this repo to extend.
- **Not every Part 4 security edge case was driven through the browser UI** — several (malformed code, replay, tampering) were verified via curl against the same live backend instance instead of clicking through the UI a second time; functionally equivalent (same server code path, same response), but not a UI click-path for each one.
- **The older `POST /organizations/{organization_id}/admins` endpoint** (caller-supplied password) remains unmodified and un-deprecated, same as M19.1 left it — out of this session's scope too.
- Local dev-DB test data created this session (2 orgs, 2 users, their audit trail; plus the `m19-2-platform-admin@example.com` platform admin account) was **not** cleaned up, for the same reason M19.1 didn't: `audit_events` is append-only by DB trigger, so force-deleting the users/orgs would leave dangling audit references. Inert, local-only, harmless.

---

## Definition of Done — checklist against the master prompt

1. [x] Real browser-driven E2E verification of the invitation flow performed (Section 7) — with the explicit partial-scope caveat on Part 4 edge cases stated there and in Section 16.
2. [x] Invitation revocation implemented (Section 3) using the existing `AuthVerificationCode` primitive, not a new mechanism.
3. [x] Frontend test added for the invitation panel (Section 6) — following this repo's existing (non-RTL) test convention, with that gap named explicitly.
4. [x] Existing invitation architecture not redesigned — only extended (Sections 2–5).
5. [x] Production Neon never touched (Section 15).
6. [x] Staging never mutated (Section 14).
7. [x] No push to `origin/main`; local commit only, matching message style, correct attribution (Section 13).
8. [x] RBAC/tenant isolation not weakened; no existing tests deleted (Sections 3, 6, 9).
9. [x] No fabricated results — every "NOT COMPLETE" item stated plainly (Section 16), no result asserted without a command/log/query backing it.
10. [x] No real emails sent — `ConsoleEmailSender` local fallback used throughout (OTPs pulled from `uvicorn` stdout log).
11. [x] Drone/UAV code untouched — no file under any drone/UAV path was read or modified this session.
12. [ ] Full Part 4 edge-case matrix driven end-to-end through the browser specifically (as opposed to via curl/automated tests against the same live backend) — **not fully done**; see Sections 7 and 10 for exactly which cases were curl-only and why.

**Final status: 11/12 complete; the 1 partial item (full browser-driven Part 4 edge-case matrix) is named explicitly in Sections 7, 10, and 16 rather than blurred.**
