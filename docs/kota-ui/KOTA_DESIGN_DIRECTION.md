# KOTA Design Direction

**Principle:** calm, precise, editorial. Aerospace seriousness, not sci-fi. Motion only where it carries meaning.

## Identity
- **Palette**: deep navy `#050b14` / graphite ground, light surfaces `#f6f8fa`, one electric-blue accent (`#1f56d6` light, `#5a9bff` dark, existing). A muted brass `#c8a96a` is a rare editorial accent on dark hero surfaces only.
- **Type**: a display serif for hero and editorial headings (`--kota-font-display`: Iowan Old Style / Palatino / Georgia stack, no web-font download), the existing system sans for UI, mono for telemetry. Wide-tracked small-caps eyebrows.
- **Geometry**: fine 1px grids, orbital ellipses, constellation points, telemetry paths drawn as single hairlines.
- **Avoid**: neon, glow borders, glassmorphism, large gradients, ticker-style motion.

## Tokens (added in `app/kota-ui.css`; additive, no existing token changed)
`--kota-font-display`, `--kota-ease-out`, `--kota-ease-in-out`, `--kota-dur-{fast,base,slow}`, `--kota-focus-ring`, `--kota-shadow-{1,2,3}`, `--kota-hero-*`. Motion durations collapse to `0ms` under `prefers-reduced-motion`.

## Motion rules
1. Transform and opacity only. 2. One ambient layer per screen. 3. Pause on hover and focus. 4. Never delay a task. 5. Everything must read well with motion off.

## Truthfulness rules
- No fabricated operational metrics. Showcase copy describes capability, not live data.
- Illustrations are original vector art and are not presented as photographs. Unlicensed imagery is not used. Showcase slides accept an optional `photo` that falls back to the vector scene.
- HUMS and telemetry views (later milestones) must distinguish live, historical, derived, predicted and confirmed data. AI output is always labelled.
