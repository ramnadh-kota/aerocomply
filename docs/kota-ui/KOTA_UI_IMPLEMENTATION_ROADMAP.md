# KOTA UI Implementation Roadmap

| # | Milestone | Status |
|---|---|---|
| 0 | Audit, direction, ownership, roadmap | Done |
| 1 | Design tokens (typography, motion, elevation, focus) | Done (additive `app/kota-ui.css`) |
| 2 | Premium sign-in + aerospace showcase | Done; see `KOTA_UI_TEST_REPORT.md` |
| 3 | App shell: SVG icon set replacing glyphs, regrouped nav, command palette | Next; needs Antigravity coordination |
| 4 | Fleet, asset detail, HUMS and telemetry visualization | Planned |
| 5 | LISA, proactive intelligence, maintenance/compliance forms and tables | Planned |
| 6 | Platform admin | Planned |
| 7 | Public marketing site and solution pages (not present in this repo; needs a hosting decision) | Planned |
| 8 | Polish, a11y audit, performance, handoff | Planned |

## Open decisions for the product owner
1. Where the public site lives (new routes in this app, or a separate project). Showcase CTAs currently open an in-page capability panel because no solution pages exist.
2. Licensed photography for the showcase. Slides already accept a `photo` path.
3. Whether to add SSO or username/mobile login. Neither exists in the auth contract, so neither is shown.
