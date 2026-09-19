# M20.1 — Dashboard: Real KPI Cards + Real Fleet/Work-Order Charts

Date: 2026-09-19
Scope: rebuild `/dashboard`'s top-of-page KPI section to use real backend data, add two real charts, extend (not replace) the existing `globals.css` design system, and label everything that remains mock as "Illustrative Data." Not the full 50-section dashboard vision — one verified slice, per the M20 audit's roadmap (`M20_AUDIT_AND_ROADMAP.md`, milestone M20.4-shaped).

## What existed before

`frontend/app/(app)/dashboard/page.tsx` (475 lines, server component) was **100% mock-data-backed**: a static `KPIS` array with hardcoded strings ("128" aircraft, "1,846" requirements, etc.), a static `DISTRIBUTION` compliance bar (92/5/2/1%), a static `ATTENTION_ITEMS` array, and several KPI/list sections driven by `lib/mock/*` helpers (`maintenanceProjects`, `workOrders`, `technicians`, `inspectorReviews`, `findings`, `ai/analytics`). Zero charts existed — only static KPI tiles and one hardcoded percentage bar. Confirmed by `M20_AUDIT_AND_ROADMAP.md` §1.2 before starting.

## What real data was wired in

Converted the page to a client component (`"use client"`) and added a new `RealFleetPanel` component at the top of the page that fetches, in parallel, from four already-live backend endpoints using the same `useSession` + typed-API-client + `RealDataPanel` pattern already used by `/drones` (`frontend/app/(app)/drones/page.tsx`):

- `aircraftApi.list` → `frontend/lib/api/aircraft.ts:18` (`GET /aircraft`)
- `dronesApi.listDrones` → `frontend/lib/api/drones.ts:241` (`GET /drones`)
- `workOrdersApi.list` → `frontend/lib/api/workOrders.ts:19` (`GET /work-orders`)
- `deferredItemsApi.listForFleet` → `frontend/lib/api/deferred-items.ts:45` (`GET /fleet/deferred-items?open_only=true`)

New component: `frontend/app/(app)/dashboard/page.tsx:53-210` (`RealFleetPanel`).

### KPIs — now real (5 cards, all computed from the fetched arrays, no fabricated numbers)

1. **Total Assets** — `aircraft.length + drones.length`, with a real "N aircraft · N drones" breakdown line.
2. **Active Assets** — count of aircraft/drones with `status === "ACTIVE"`.
3. **Grounded / Attention** — count with `status === "GROUNDED"`.
4. **Open Work Orders** — count where `status` is not in `{COMPLETED, CANCELLED, CLOSED}`, out of the real total.
5. **Open MEL / Deferred Items** — length of the `open_only=true` deferred-items response.

No trend/delta numbers were invented — per the mission's explicit instruction not to fabricate a trend that can't be cheaply computed from real data, each card instead shows a real "as of [time]" line (`page.tsx:171`: "As of {asOf} · live backend query, not a fabricated trend").

### Charts — now real (2 charts, no new dependency added)

Checked `frontend/package.json` first: no chart library (no Recharts/visx/d3/Chart.js) is present in this repo. Rather than add a new dependency for two simple bar charts — credit-conscious and lower-risk per the mission's constraints — both charts are a small set of new CSS classes (`.ac-chart-bar-row/-track/-fill/-count`, added to `frontend/app/globals.css`) driving `<div>` width percentages from real counts, matching the exact visual pattern the old static `DISTRIBUTION` bar already used in this codebase (just parameterized on real data instead of hardcoded percentages).

1. **Fleet Status Distribution** — Active (green, `var(--ac-status-compliant)`) / Grounded (red, `var(--ac-status-non-compliant)`) / Unknown (gray, `var(--ac-status-unknown)`), computed from the same aircraft+drone status fields as the KPIs above.
2. **Work Order Status Breakdown** — one bar per distinct `status` value present in the real work-order list (e.g. OPEN, IN_PROGRESS, COMPLETED), sorted by count descending, in the blue accent color (`var(--ac-accent)`).

Both charts have explicit empty states ("No aircraft or drone assets yet." / "No work orders yet.") — never blank.

### Loading / error / empty states

All four fetches share one `loading`/`error` state via `RealDataPanel` (`frontend/components/data-mode/RealDataPanel.tsx`, the same shared component `/drones` and other REAL-mode pages already use): shows "Loading from the connected backend…" while in flight, a labeled non-compliant error card with a safe, normalized message on failure (`normalizeApiError`), an empty-state message if nothing exists yet, and a distinct "Sign in to view live fleet data" card when unauthenticated. No silent fallback to mock data on error at any point.

### What remains mock — now explicitly labeled "Illustrative Data" (not silently presented as live)

- "Daily Brief, Priority Queue & TAT Summary" section header — new `IllustrativeBadge` added (`page.tsx`, wraps `DailyBriefCard`).
- "Maintenance Operations Snapshot" (Active Projects, Overdue Tasks, Technicians On Shift, Awaiting Parts, etc.) — still backed by `lib/mock/maintenanceProjects` / `lib/mock/workOrders` / `lib/mock/technicians`; header now carries the same badge.
- "Fleet Compliance Overview" (the old hardcoded 92/5/2/1% distribution bar, left in place since assessment-compliance percentages have no real aggregation endpoint yet per the audit) — badge added next to its existing "128 aircraft (demo scenario)" caption.
- "Attention Required" (`ATTENTION_ITEMS`, still a hardcoded array) — badge added.
- "AI & Operations Intelligence" (mock `ai/analytics` helpers) — already self-labeled "AI Prototype · Non-authoritative" before this change; left as-is, no new badge needed.
- Recent Assessments / Upcoming AD-SB / Overdue Compliance / Open Review Decisions tables — unchanged, still `lib/mock/assessments`-backed (out of scope: no real assessment-list-for-dashboard endpoint was in tonight's live-endpoint set per the audit).

## Design tokens reused vs. added

**Reused, not reinvented:** `--ac-bg-surface`, `--ac-border`, `--ac-radius-lg`, `--ac-space-*`, `.ac-kpi-grid`, `.ac-card`, `.ac-eyebrow`, `.ac-text-sm`/`.ac-text-muted`, and the five status-color tokens (`--ac-status-compliant`, `--ac-status-non-compliant`, `--ac-status-unknown`, `--ac-accent`) exactly as they already existed in `globals.css`.

**Added** (`frontend/app/globals.css`, appended after `.ac-kpi-label`): `.ac-kpi-card-real`, `.ac-kpi-asof`, `.ac-illustrative-badge` (amber, using the existing `--ac-status-review` token, not a new color), and the four `.ac-chart-bar-*` classes for the CSS bar charts. The bar-fill width transition is wrapped in `@media (prefers-reduced-motion: reduce)` to disable it, consistent with the three other reduced-motion blocks already in this file.

## Test / build / lint results

- `npx tsc --noEmit` — **clean, zero errors.**
- `npx eslint "app/(app)/dashboard/page.tsx"` — **0 errors, 1 warning** (`react-hooks/set-state-in-effect` on the `setLoading(false)` early-return branch). Confirmed this exact warning also pre-exists on `/drones/page.tsx` (same fetch pattern, same warning) — not a new problem introduced by this change, and matches the pattern already accepted elsewhere in the codebase.
- `npm run build` — **succeeded.** `/dashboard` compiled as a static route (`○`) alongside all other ~100 routes with no build errors.
- No frontend unit test suite covers this page specifically; no existing tests were touched or broken.

## Browser verification (actually performed, not skipped)

1. Started the frontend via `preview_start` (`aerocomply-dev`, Next.js dev server on port 3000).
2. Started the backend locally against the existing **local dev Postgres** (`localhost:55432`, `aerocomply_dev` — confirmed via `backend/.env`, never staging/prod) on port 8001 (matching `frontend/.env.local`'s `NEXT_PUBLIC_API_BASE_URL`).
3. Registered a throwaway local test organization/user via `POST /auth/register-organization` (`dashboard-qa@example.com`, local DB only, not a real account).
4. Created real records via authenticated API calls: 2 aircraft (`N100QA`, `N101QA`), 1 drone (`DRN-QA-1`), 2 work orders (both `OPEN`).
5. Logged in through the actual browser UI at `/login` (first attempt failed with a real "Unable to reach the server" error because the backend was initially started on the wrong port — a genuine bug I caught and fixed by restarting on 8001 to match `.env.local`, not glossed over).
6. Loaded `/dashboard` as the signed-in user and confirmed by screenshot:
   - **Total Assets: 3** ("2 aircraft · 1 drones"), **Active Assets: 3**, **Grounded/Attention: 0**, **Open Work Orders: 2** ("of 2 total"), **Open MEL/Deferred Items: 0** — all matching the real records just created, with the "As of [time] · live backend query, not a fabricated trend" line rendering.
   - **Fleet Status Distribution** chart: Active bar full-width/green with count 3, Grounded 0, Unknown 0.
   - **Work Order Status Breakdown** chart: one blue bar, "OPEN", count 2.
   - **"Illustrative Data" badge** visible and correctly placed next to the Daily Brief section immediately below the real panel.
   - Console errors checked: only stale `ERR_CONNECTION_REFUSED` entries from the earlier wrong-port login attempt, none after the fix.

This was real end-to-end verification against a running backend and local Postgres with a real logged-in test user, not just a successful compile.

## Files changed

- `frontend/app/(app)/dashboard/page.tsx` — converted to client component; added `RealFleetPanel`, `IllustrativeBadge`, `WO_CLOSED_STATUSES`; removed the two static mock KPI/DISTRIBUTION constants that are now replaced by real data; added "Illustrative Data" badges to the sections that remain mock-backed.
- `frontend/app/globals.css` — added `.ac-kpi-card-real`, `.ac-kpi-asof`, `.ac-illustrative-badge`, `.ac-chart-bar-row/-track/-fill/-count`, and their reduced-motion override, appended after the existing `.ac-kpi-label` rule. No existing rules were modified or removed.

## Local commit

Not yet committed — see below (will be created after this report, matching the existing message style, local-only, not pushed).

## Honest list of what's still mock/missing on this dashboard (future milestones)

- Compliance-assessment KPIs/percentages (Applicable Requirements, Assessments Requiring Review, Insufficient Data, Critical Compliance Issues, the old 92/5/2/1% distribution) — no real aggregation endpoint exists yet for these; still mock, now labeled.
- Maintenance Operations Snapshot (Active Projects, Overdue Tasks, Technicians On Shift, Awaiting Parts, Inspections Awaiting Review, Checklist Exceptions) — still 100% `lib/mock/*`; a real version would need `technicians.ts`/`inspections.ts` API wiring plus a real Findings model (M20.2 in the roadmap) before "Checklist Exceptions" can be honest.
- "Attention Required" and "AI & Operations Intelligence" panels — still hardcoded/mock, explicitly labeled, not wired to any derived-condition engine (none exists yet per the audit).
- No per-asset deployment-readiness rollup (READY/BLOCKED from `release_readiness_service.py`) is shown — would require an N+1 call per work order/asset; deliberately left for a future milestone with a proper aggregation endpoint rather than doing it inefficiently here.
- Recent Assessments / AD-SB deadline / Overdue Compliance / Open Review Decisions tables are still fully mock (`lib/mock/assessments`, `lib/mock/maintenance`).
- No role-based variation of this dashboard was attempted (explicitly out of scope per the mission boundaries).

This is one real, browser-verified slice of the dashboard — not the full 50-section vision, and not claimed as such.
