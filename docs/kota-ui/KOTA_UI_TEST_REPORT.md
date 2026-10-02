# KOTA UI Test Report (Milestones 0-2)

Run 2026-10-02 from `frontend/`.

| Check | Baseline | After Milestone 2 |
|---|---|---|
| `tsc --noEmit` | clean | clean |
| `eslint .` | 0 errors, 132 warnings | 0 errors, 132 warnings (no new warnings in new files) |
| `vitest run` | 44 files / 424 tests pass | 45 files / 430 tests pass |
| `next build` | not run | succeeds |

## Manual browser verification (dev server, `/login`)
- Desktop 1600x900: split layout renders; carousel scrolls; card hover lifts the card and eases the carousel to a stop; card click opens the panel; Esc closes it and the page has no horizontal overflow.
- Mobile 375x812: form first, showcase below; descriptions and CTA visible without hover.
- Submit with a throwaway invalid email/password against the running backend: the real validation error from the API appears in the alert region and the inputs show the invalid state. No successful login was attempted, so the post-login redirect was not exercised in the browser. It is unchanged code.
- Console: only 401 responses from the session check on an unauthenticated load. These come from existing code, not this change.

## Not verified
- Behaviour in Safari and Firefox; drag and swipe were not exercised in the browser (only the layout was checked in an emulated mobile viewport), and prev/next arrows were not clicked.
- Screen-reader pass and a formal WCAG audit.
- Successful sign-in and redirect for tenant and platform users (needs real credentials).
- Performance profiling beyond the code design (transform-only animation, no React re-renders in the loop).
- Light/dark app themes were not both screenshotted; the form side consumes `--ac-*` tokens, the showcase is fixed dark.
