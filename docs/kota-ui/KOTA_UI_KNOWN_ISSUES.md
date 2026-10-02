# KOTA UI Known Issues and Open Items

1. **No public site or solution pages exist in this repo.** Showcase CTAs open an in-page capability panel instead of navigating. Decision needed: where the marketing site and solution pages live.
2. **No photography.** The showcase uses original vector illustrations. To add licensed photos, set `photo` on a slide in `components/auth-showcase/slides.ts` (local `/images/...` path); the vector scene is the fallback if it fails to load. No images were downloaded or invented.
3. **No SSO / username / mobile login.** The auth contract takes an email and password only, so none is shown. The reference design's Google button and "Register now" link were deliberately not copied. No register route exists.
4. **No security/support links** on the login page, because no such routes exist.
5. **Display font** is a system serif stack (Iowan Old Style, Palatino, Georgia), so it varies by OS. Adding a web font is a design decision with a performance cost.
6. **Logo** is the existing raster mark with built-in padding; the login page crops it with a negative margin. A tight SVG of the mark would be cleaner.
7. **Carousel hand-off:** the two-copy loop assumes the pane is narrower than five cards' width (about 1,500 px). On a pane wider than that, a third copy is needed.
8. **Pre-existing:** 132 ESLint warnings (mostly `react-hooks/set-state-in-effect`); two 401s on unauthenticated page load from the session check.
9. Milestones 3-8 are not started.
