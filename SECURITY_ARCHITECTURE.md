# Security Architecture

## Identity and sessions
JWT bearer tokens (`app/core/security.py`), Argon2 password hashes. The JWT carries **no entitlement or
feature claims**; entitlements are resolved server-side per request (`resolve_entitlements`), so plan changes,
cancellation and expiry take effect immediately.

## Authorization layers (all enforced server-side)
1. **Authentication** - valid token, active user.
2. **RBAC** - `require_permission(Permission.X)`; platform routes require `PLATFORM_MANAGE`.
3. **Tenant scoping** - every query filters `organization_id`; foreign ids return 404, not 403 (no existence leak).
   Proven by `test_tenant_isolation_end_to_end.py` (automated cross-tenant probe over the route table;
   mutation-tested by removing a filter and observing the probe fail).
4. **Entitlement** - `require_feature(...)`; outside-suite features return `SUITE_ENTITLEMENT_REQUIRED`,
   in-suite-but-unpurchased return `forbidden`. Expired/cancelled subscriptions lose gated routes
   (`/data-sources` is gated router-wide by `flight_telemetry`).
The frontend guard (`RouteEntitlementGuard`) is UX only; it is never the control.

## Ingest hardening
* Ingest body capped at 25 MB (HTTP 413); deeply nested/recursion-bomb JSON is rejected with 4xx, not 500 (regression test).
* Events with no valid measurement are rejected, not stored.
* MAVLink: CRC_EXTRA validation, sequence tracking, component/system filtering, arrival-time timestamps
  (a vehicle cannot backdate or future-date events). MAVLink 2 **signing is counted but not verified** -
  see gaps.
* `default_asset_id` / `system_id_map` targets are tenant-checked at write time.
* Per-event SAVEPOINT: a hostile event cannot poison the batch or the transaction.
* DJI webhook: mandatory HMAC signature (`X-DJI-Signature`) keyed by `DJI_WEBHOOK_SECRET`; if the secret is unset the endpoint fails closed (503). Signature verification is `telemetry_service.verify_webhook_signature`.

## Secrets
Environment only (`.env` untracked; `SECRET_KEY`, DB URL, `DJI_WEBHOOK_SECRET`, provider keys). No secrets in
the repo. Test billing provider is refused in production.

## Known gaps (honest list)
* **No rate limiting / brute-force lockout** on login or ingest - put a WAF/reverse-proxy limit in front until
  implemented. NOT IMPLEMENTED.
* MAVLink 2 signature **verification** not implemented; unsigned links are trusted only via the per-source auth token.
* Compliance/assessment endpoints are not entitlement-gated on the backend (RBAC + tenant scoping still apply).
* No external penetration test, dependency-CVE audit in CI, or SAST beyond ruff `E9,F63,F7,F82`: EXTERNAL VALIDATION REQUIRED.
* Metrics endpoint is protected by platform permission, not network policy; restrict at the proxy as well.
