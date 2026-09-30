# Browser validation (headless Chrome over the DevTools Protocol)

No automation library is required: Node 24 + Chrome. Runs against a SCRATCH environment only.

1. `alembic upgrade head` on a scratch database; start the API (`uvicorn app.main:app --port 8001`) with that `DATABASE_URL`.
2. `NEXT_PUBLIC_API_BASE_URL=http://localhost:8001/api/v1 npx next build && npx next start -p 3000`
3. Seed: `python seed_browser.py` (drone org, assets, MAVLink telemetry; needs `platform@example.com` and
   `aircraft-admin@example.com` from the platform seed) and `python seed_heli.py` (helicopter + eVTOL orgs).
   Set `BROWSER_SCRATCH` to a writable directory (screenshots, seed json).
4. `node browser_validate.mjs` (auth, drone flows, data sources, LISA, platform, cross-suite), `node browser_validate2.mjs` (strict sidebar, mock-only notices, live pages, helicopter and eVTOL UI journeys) and `node browser_validate3.mjs` (sample-data marker scan over 20 pages x 2 organizations + live control center).
   `node browser_validate2.mjs` (strict sidebar, mock-only notices, live pages, helicopter and eVTOL UI journeys).

Last run (2026-09-30): 44 + 56 + 42 checks, 0 console errors, 0 failed HTTP responses. This is scripted
validation, not human UAT.
