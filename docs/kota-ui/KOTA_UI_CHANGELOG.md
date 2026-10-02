# KOTA UI Changelog

Branch: `feature/kota-ui-2046` (from `feature/drone-ops-dashboard`).

## Milestone 0: audit and direction
- Added the four discovery documents in `docs/kota-ui/`.

## Milestone 1: design tokens
- New `frontend/app/kota-ui.css`: display font stack, eyebrow tracking, motion easing and duration tokens (zeroed under reduced motion), three elevation levels, a focus-ring token, and hero surface colours. No existing `--ac-*` token was changed.
- `frontend/app/layout.tsx`: one added import line for `kota-ui.css`.

## Milestone 2: premium sign-in
- `frontend/app/login/page.tsx` rewritten as a split-screen page. Submit logic is unchanged: duplicate-submit guard, `authApi.login` with `onRetry`, `login(tokens)`, `setMode("REAL")`, and the same role-based redirect. New: label/input wiring, password show/hide toggle, `aria-invalid`/`aria-describedby` on error, spinner in the loading state.
- `frontend/app/login/login.module.css` (new): scoped styles for the form side.
- `frontend/components/auth-showcase/` (new): `AerospaceShowcase.tsx` (carousel), `Scenes.tsx` (original vector scenes; reuses the existing narrowbody and helicopter silhouettes), `slides.ts` (approved copy plus the `wrapOffset` and `easeToward` helpers), `showcase.module.css`.
- `frontend/tests/auth-showcase.test.ts` (new): 6 tests.

### Showcase behaviour
- Continuous loop at about 26 px/s from two copies of the track, so there is no visible jump. Pause and resume are eased.
- Pauses on hover, keyboard focus, drag, and while the details panel is open.
- Visible pause/play control, prev/next arrows, mouse drag and touch swipe.
- Reduced motion: auto-scroll off, orbit/star animation off, hover transforms off. Arrows and drag still work.
- Card hover or focus: lift, restrained image zoom, description and CTA reveal. On touch devices the text is always visible.
- Card click opens an in-page capability panel (Esc to close, focus moved in and restored for keyboard users).
- On screens under 960px the showcase stacks below the form.
