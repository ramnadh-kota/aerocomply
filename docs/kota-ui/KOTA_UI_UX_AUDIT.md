# KOTA UI/UX Audit (Milestone 0)

Based on the repository at branch `feature/drone-ops-dashboard` (HEAD `dddcd16`), audited 2026-10-02. Everything below was read from the code, not assumed.

## 1. Architecture
- **One Next.js app** in `frontend/`: Next 16.3.5 (App Router), React 18.3.1, TypeScript 5.6, Vitest 2.1. Runtime deps are only `next`, `react`, `react-dom`, `leaflet`, `react-leaflet`. There is no Tailwind, no component library, no animation or chart library.
- `frontend/AGENTS.md` warns that this Next version has breaking changes. Docs ship in `node_modules/next/dist/docs/`.
- **Routing**: `app/login`, `app/forgot-password`, `app/reset-password`, `app/onboarding`, `app/page.tsx` (redirector). All product routes live in the `app/(app)/` route group, guarded by `app/(app)/layout.tsx`. It has about 25 areas: dashboard, fleet, aircraft, drones, helicopters, evtols, engines, drone-ops/*, maintenance/*, compliance/*, intelligence, ai, reports, organization/*, tenant/*, platform/*.
- **Org app and platform admin share one app.** Platform admin is `/platform/*` inside `(app)`. After login, users with `PLATFORM_ADMIN` or `PLATFORM_STAFF` go to `/platform/organizations`; everyone else goes to `/dashboard`. The domains `kotaaerospace.com`, `admin.kotaaerospace.com` and `aerocomply.vercel.app` are not referenced in the code. How domains map to deployments is a deployment setting, not a repo fact.
- **No public marketing website and no solution pages exist in this repo.** There are no `/solutions/*`, contact, privacy, or support routes. The `/` route only redirects. See Risks and the roadmap for how this affects the showcase CTAs.
- **Auth**: `lib/auth/SessionContext.tsx` and `lib/apiClient.ts` (`authApi.login(email, password, {onRetry})`, `forgotPassword`, `normalizeApiError`). Login takes an **email**. There is no username, mobile or Google/SSO option, so the UI must not offer one.
- **Styling**: a single 2,580-line `app/globals.css` with `--ac-*` tokens. Light is the default; dark is a deliberate separate palette via `[data-theme="dark"]`. A no-flash theme script is in `app/layout.tsx`. Components mostly use inline styles plus `ac-*` classes.
- **Shared components**: `components/ui` (only `ConfirmDialog`), `status/StatusBadge`, `tables/DataTable`, `layout/{Sidebar,Topbar,PageHeader,Breadcrumbs,ThemeToggle}`, `dashboard/*`, `aircraft-visual/*` (line-art silhouettes: narrowbody, widebody, turboprop, helicopter), `branding/Logo`.
- **Brand**: `lib/brand.ts` locks the brand to "KOTA'S AEROSPACE", assistant "Lisa", compliance module "AeroComply". Do not reintroduce "OS" naming. The logo is the raster `public/images/kotas-aerospace-logo.png` (677x369).

## 2. Baseline (before any change)
| Check | Result |
|---|---|
| `npm run typecheck` | clean |
| `npm run lint` | 0 errors, 132 warnings (existing, mostly `react-hooks/set-state-in-effect`) |
| `npm test` | 44 files, 424 tests, all passing |
| `next build` | not run at baseline; run at end of each milestone |

## 3. Key user journeys (existing)
1. Visit `/` -> redirect to `/login` -> sign in -> `/dashboard` or `/platform/organizations`.
2. Forgot password -> `/forgot-password` -> email -> `/reset-password`.
3. Org user: dashboard -> fleet or asset detail -> findings, maintenance, compliance, evidence -> reports.
4. Drone ops: `/drone-ops/*` (overview, live-map, telemetry, health, alerts, missions, copilot).
5. Platform admin: organizations, plans, entitlements, subscriptions, provisioning, audit.

## 4. Visual and UX findings
- **Login** was a centered 380px card, inline-styled, with no brand storytelling and no password toggle. It had good logic: duplicate-submit guard, retry state, `role="alert"` error.
- The nav uses Unicode glyphs as icons and has a flat, long Operations group of 11 items. These render inconsistently across platforms; this is the weakest part of the shell.
- Tokens exist for color, space, radius and one shadow. Missing: typography scale, display/serif face, motion tokens, elevation scale, focus-ring token.
- Duplicate or alias tokens in `:root` (`--primary`, `--ac-primary`, `--ac-text`...) show previous drift.
- Inline styles dominate, so the system cannot be restyled centrally.
- `prefers-reduced-motion` is already handled in three places in globals.css.

## 5. Must-keep functionality
- Auth flow, token handling, `SessionContext`, data-mode switching (`setMode("REAL")`), route permissions (`lib/rbac`), entitlement guards, role-sim, platform deletion governance.
- Tests that cover login/auth behavior: `login-resilience.test.ts`, `staging-demo-auth.test.ts`.

## 6. Redesign priorities
1. Design-system foundation: typography, motion, elevation, focus tokens (additive).
2. Premium login with aerospace showcase.
3. App shell and nav (icons and grouping).
4. Dashboard, fleet, asset detail.
5. HUMS and telemetry views, with a strict live / derived / predicted / confirmed distinction.
6. Platform admin and public site (the site does not exist in this repo yet).

## 7. Risks and conflicts
- Antigravity is the active frontend agent. Its in-flight changes are unknown, so shared files (`globals.css`, `Sidebar.tsx`, `(app)/layout.tsx`) carry conflict risk. Mitigation: new styles go in a new file, shared files change only additively. See `KOTA_FRONTEND_OWNERSHIP.md`.
- The showcase CTAs have no solution pages to link to, and no licensed photography exists locally.
- Production must not be edited directly. All work stays on a branch.
