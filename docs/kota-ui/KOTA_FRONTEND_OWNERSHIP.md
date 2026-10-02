# KOTA Frontend Ownership

Status: other agents' in-flight edits cannot be observed from this repo. At start, `git status` showed only one untracked backend test. Working branch: `feature/kota-ui-2046` (from `feature/drone-ops-dashboard`).

| Area | Files | Owner for this effort | Rule |
|---|---|---|---|
| Auth pages | `app/login/**`, `components/auth-showcase/**` | UI/UX lead (this branch) | Antigravity: coordinate before editing |
| Design tokens | `app/kota-ui.css` (new) | UI/UX lead | New tokens go here only |
| Global CSS | `app/globals.css` | **Shared** | Not modified in Milestones 0-2 |
| Root layout | `app/layout.tsx` | **Shared** | One additive import line only |
| Shell | `components/layout/*`, `app/(app)/layout.tsx` | **Hold** (Milestone 3) | Untouched until coordinated |
| Feature pages | `app/(app)/**` | Antigravity | Untouched in Milestones 0-2 |
| Backend | `backend/**` | Claude Code (backend) | Untouched |
| Auth logic | `lib/apiClient.ts`, `lib/auth/**` | Backend/auth owners | Read only |

Conflict protocol: if a file outside the UI/UX-owned rows needs a change, stop and record it in `KOTA_UI_KNOWN_ISSUES.md`.
