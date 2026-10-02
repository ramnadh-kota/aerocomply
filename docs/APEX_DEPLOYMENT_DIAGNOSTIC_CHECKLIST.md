# Apex deployed 404 — diagnostic checklist (evidence still required)

Status: **unresolved; no deployed-environment evidence has been available to this review.** Nothing below is a finding. Do not treat
any item as a root cause until the evidence is attached. Read-only collection only; do not deploy or alter production/staging data.
Never paste secrets (tokens, passwords, connection strings, cookies) into the report — redact them.

Affected routes: **Fleet Intelligence**, **Fleet Registry**, **Tenant Dashboard**.

## 1. Environment identity
- [ ] Deployed frontend URL and deployed API base URL.
- [ ] Vercel project/deployment id (and environment: production / staging / preview) serving the failing pages. Local link metadata only
      shows project `aerocomply` (`.vercel/project.json`); it does not identify the deployment.
- [ ] Git SHA of that deployment, for both frontend and backend, and whether each was built from `feature/post-freeze-productionization`
      (current local branch; local HEAD `6bd38ce` plus uncommitted work) or an older commit. Compare with `git log`.
- [ ] Backend hosting target and build/revision id (container image tag or release).

## 2. Frontend build configuration
- [ ] Value of `NEXT_PUBLIC_API_BASE_URL` baked into that build (it is inlined at build time; the local example uses `/api/v1` on port 8000).
      Is it the deployed API (not `localhost`)? Does it end in `/api/v1`?
- [ ] Build log excerpt showing the route list; confirm the three page routes exist in that build.

## 3. Network evidence (browser DevTools, one HAR or screenshots per route)
For each of the three routes, signed in as an Apex user:
- [ ] Page document request: URL, status, `x-vercel-id`, `x-matched-path`. A 404 here points at a missing route/rewrite in the deployed
      build; a 200 followed by API 404s points at the backend.
- [ ] Every XHR/fetch: method, URL, status, response body `error.code` (redact tokens). Expected tenant calls include
      `/tenant/dashboard`, `/entitlements`, the fleet/asset list calls.
- [ ] Console errors and any CORS failures.

## 4. Backend data and schema
- [ ] Deployed database Alembic revision (`alembic current`); local head is `0070`. A lower revision implies missing tables/columns/endpoints.
- [ ] Apex organization row: id, status (must not be SUSPENDED/deleted), suite assignment.
- [ ] Apex subscriptions: status (ACTIVE/TRIALING), plan code, suite id, start/end dates.
- [ ] Output of `GET /entitlements` as an Apex user: `active_suites`, `effective_features` (check the fleet feature for their suite),
      `subscription_status`.
- [ ] Apex user roles and `GET /auth/me` permissions (tenant dashboard needs only authentication; usage/contact need `org:manage`).
- [ ] Backend log lines for the failing requests (request id, status, route) around the failure time.

## 5. Decision table once evidence exists
| Evidence | Likely direction |
|---|---|
| Page document is 404 (Vercel) | Frontend build/route/rewrite mismatch — compare SHA, redeploy decision belongs to the owner |
| API returns 404 for a route that exists locally | Backend older than frontend — check revision and SHA |
| API returns 403 `feature_not_entitled` / `suite` | Apex subscription/suite/plan data — verify rows above |
| API returns 401/CORS | Auth/base-URL configuration |

Access needed to complete: read access to the deployment (Vercel dashboard or authorized CLI/connector) and read-only access to the
backend logs and database revision. If you provide URLs or credentials through an authorized tool, diagnosis will be read-only.
