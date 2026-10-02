# Handoff to Antigravity (Milestones 0-2)

Branch: `feature/kota-ui-2046`. Not merged, not deployed.

## Files added
- `frontend/app/kota-ui.css`, `frontend/app/login/login.module.css`
- `frontend/components/auth-showcase/{AerospaceShowcase.tsx, Scenes.tsx, slides.ts, showcase.module.css}`
- `frontend/tests/auth-showcase.test.ts`
- `docs/kota-ui/*`

## Files modified
- `frontend/app/login/page.tsx` (UI rewrite; auth logic unchanged)
- `frontend/app/layout.tsx` (one import line)

## Safe to reuse
- `--kota-*` tokens in `kota-ui.css` for new surfaces. Use `--kota-dur-*` and `--kota-ease-*` for motion so reduced-motion works automatically.
- `ShowcaseScene` and `slides.ts` helpers `wrapOffset` and `easeToward`.
- Login form classes are CSS-module scoped. Copy the pattern, do not import them elsewhere.

## Please do not overwrite independently
- `app/login/page.tsx`, `app/login/login.module.css`, `components/auth-showcase/**`. If you must change the sign-in flow, keep the duplicate-submit guard, `onRetry` wiring and the role-based redirect. `tests/login-resilience.test.ts` covers the API layer.

## Not touched
Backend, `app/(app)/**`, `components/layout/**`, `app/globals.css`, `lib/**`.

## Follow-up tests
- Sign in as a tenant user and a platform user and confirm the redirects.
- Check the page in Safari, Firefox, and on a real phone.
- Run a screen-reader and keyboard-only pass.

## Next milestone dependency
Milestone 3 (app shell) edits `components/layout/Sidebar.tsx`, which you probably also touch. Tell me what you have in flight there before I start.
