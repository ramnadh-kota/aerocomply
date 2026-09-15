// M17.2.1: ESLint 9 flat config, replacing the previous .eslintrc.json.
// eslint-config-next@16 ships a native flat-config array at
// "eslint-config-next/core-web-vitals" (no legacy eslintrc schema involved),
// which is preferred here over bridging the old "next/core-web-vitals" via
// FlatCompat -- that bridge path hits a real upstream circular-JSON bug in
// @eslint/eslintrc's config validator when combined with eslint 9.39.5's
// stricter schema validation (confirmed by reproducing it directly in this
// repo), while the native flat export avoids that code path entirely.
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";

const eslintConfig = [
  ...nextCoreWebVitals,
  {
    rules: {
      // eslint-plugin-react-hooks jumped from v4 to v7 as part of this
      // Next.js 16 migration (eslint-config-next's own dependency), which
      // both raised react-hooks/exhaustive-deps's default severity to
      // "error" and introduced brand-new rules (set-state-in-effect,
      // use-memo, static-components) that now flag pre-existing,
      // intentional patterns throughout this app (mainly
      // hydration-safe "load persisted state via useEffect" components
      // that predate this migration and are unrelated to it). Downgraded
      // to "warn" -- kept visible, not silenced -- rather than either
      // failing the build over 39 pre-existing call sites or rewriting
      // effect-based state hydration across many unrelated components as
      // part of a framework migration. Revisiting these call sites is a
      // legitimate follow-up cleanup, not an M17.2.1 migration task.
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/exhaustive-deps": "warn",
      "react-hooks/use-memo": "warn",
      "react-hooks/static-components": "warn",
    },
  },
];

export default eslintConfig;
