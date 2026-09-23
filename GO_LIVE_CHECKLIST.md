# AeroComply / Kota Aerospace — Go-Live Checklist

Staging is functional for internal testing (981/982 backend tests, 133/133 frontend
tests, migrations applied, RBAC/tenant isolation verified in earlier sessions). This
checklist is what's actually left before real customers touch this product. Nothing
on this list has been executed — it's scoped, not done.

## Blocking (must fix before any customer sees the product)

- [ ] **Email delivery.** Render's free tier blocks outbound SMTP entirely — password
      reset/verification emails currently only reach server logs, invisible to real
      users. Switch `backend/app/services/email_service.py` to an HTTP-based provider
      (Resend, SendGrid, Postmark) instead of raw `smtplib`. Needs: provider account +
      API key (you), a new `EmailSender` implementation (small, scoped change), a
      Render env var for the API key.
- [ ] **Material-readiness data gap.** `PartRequirement.fulfilled_quantity` is never
      incremented automatically on parts receipt — only `.status` gets recomputed.
      The MATERIAL release-readiness blocker can misreport for a real work order.
      Needs a decision on correct semantics before fixing (flagged in
      `M17_OVERNIGHT_QA_REPORT.md`).
- [ ] **Production infrastructure doesn't exist yet.** Everything so far is on
      staging (Neon `small-meadow-85982633`, Render `aerocomply-backend-staging`).
      Going live means provisioning real production Neon usage, a production Render
      service (or equivalent), a real domain, and a deliberate first production
      migration — this is a distinct, planned step, not a byproduct of more bug
      fixes.
- [ ] **Security review.** No dedicated pass has been done. At minimum: secrets
      rotation plan (the JWT secret was regenerated ad hoc tonight — production
      needs its own, generated and stored properly), dependency vulnerability scan,
      confirm no debug/test endpoints are reachable, confirm CORS/production origins
      are exact (not wildcarded).
- [ ] **Legal/compliance basics.** Terms of service, privacy policy, and — given this
      is an aviation MRO compliance tool — a clear statement of what the product does
      and does not certify/authorize. This is a business decision, not something to
      generate unreviewed.

## High priority (should fix before onboarding real customers, even if not day-one blockers)

- [ ] **Live browser QA.** Tonight's verification was service-layer/API/test-suite
      only — no human or browser-driven click-through of the actual UI end-to-end
      across drones, flights, maintenance, inspections, evidence, compliance,
      release readiness. Needed before trusting the UX with real users.
- [ ] **Monitoring/alerting.** No uptime monitoring, error tracking (e.g. Sentry), or
      alerting exists. You'd currently find out about an outage from a customer, not
      a dashboard.
- [ ] **Backup/retention policy** for the production database — what's backed up, how
      often, how it's restored, tested at least once.
- [ ] **Rate limiting / abuse protection** on public endpoints (login, forgot-password,
      registration) — not reviewed.
- [ ] **Support process.** Who real customers contact when something breaks, and how
      that gets triaged.

## Already done / verified (do not redo)

- [x] Backend migrations 0001–0035 applied cleanly on staging (upgrade/downgrade/
      upgrade verified).
- [x] PLATFORM_ADMIN account bootstrapped on staging for `ramnadhkota@gmail.com`
      (password must still be set via reset flow — done tonight).
- [x] Backend test suite: 981 passed / 1 failed (the material-readiness gap above) /
      16 deselected.
- [x] Frontend: 133/133 tests, `tsc` clean, `eslint` clean, production build succeeds.
- [x] RBAC and tenant isolation spot-checked in earlier sessions (see
      `M17_FINAL_VALIDATION_REPORT.md`, `M17_AUTH_STAGING_AUDIT.md`).
- [x] Plans/Product Catalog "empty state" and Lisa's `PERMISSION_DENIED` banner
      confirmed correct-by-design, not bugs (see `M17_OVERNIGHT_QA_REPORT.md`).

## Explicitly not in scope for go-live (per earlier decision)

- Lisa (the AI assistant) taking autonomous actions on compliance/inspection/release/
  airworthiness data. The product's own UI states it "never makes or overrides" such
  decisions — that stays advisory-only unless you make a deliberate, separate call to
  change it.

## Suggested order of operations

1. Fix email delivery (blocking, small, well-scoped).
2. Decide + fix the material-readiness gap.
3. Do the live browser QA pass.
4. Security review pass.
5. Legal basics (parallel-track with the above — doesn't block engineering work).
6. Provision production infrastructure deliberately, with you present for the first
   production migration and admin bootstrap (same pattern as tonight's staging setup,
   but on production, which needs your explicit sign-off at each step, not an
   overnight run).
7. Monitoring/alerting + backup verification before first real customer traffic.
