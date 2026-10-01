# Security Architecture (as implemented, 2026-09-30)

Each control names the code and the test that pins it. **EXTERNAL VALIDATION REQUIRED:** penetration test, dependency
audit in CI, infrastructure hardening.

## Identity and sessions
* JWT bearer tokens (`app/core/security.py`), Argon2 password hashes. Tokens **must** carry `exp` and `sub`; `alg=none`,
  tampered payloads, wrong secrets, expired tokens, refresh/other-typed tokens are rejected (`test_security_hardening`).
* **The database is the authority per request** (`deps.get_current_user`): the user must exist, be active and belong to
  the token's organization, and **roles are read from `user_roles`, not from the token**. Deactivating a user or revoking a
  role takes effect on the next request, not at token expiry; a forged `roles` claim grants nothing.
* The JWT carries no entitlement claims; entitlements are resolved server-side per request.
* Suspended or deletion-pending organizations are refused on every request.
* Bearer-token API with no cookies → no ambient credentials → no CSRF surface (asserted: login sets no cookie).
  CORS allows only configured origins (`CORS_ALLOW_ORIGINS`); untrusted origins are not reflected.

## Authorization layers (all server-side)
1. Authentication (above). 2. RBAC `require_permission`. 3. Tenant scoping: every query filters `organization_id`;
foreign ids return 404 (no existence oracle) — `test_tenant_isolation_end_to_end` (cross-tenant probe over the route
table, mutation-tested). 4. Commercial entitlement `require_feature` / `require_any_feature` at **router level** for:
fleet families (aircraft, drone, helicopter, eVTOL), telemetry/data sources, HUMS, digital twin, MRO intelligence, LISA,
work orders, inspections, release readiness, TAT, missions, **compliance + regulatory (`compliance_management`),
assessments (`advanced_compliance_intelligence`), and the procurement family — parts, vendors, vendor availability,
purchase orders, receiving, inventory, part requirements, warehouses (`procurement_management`)**. Outside-suite
features answer `SUITE_ENTITLEMENT_REQUIRED`, in-suite-but-unpurchased answer `forbidden`.
Not entitlement-gated by design (baseline / cross-cutting): findings, evidence, deferred items, maintenance
requirements, AOG, control center, intelligence and proactive signals, technicians, facilities, users/tenant admin.
The frontend guard mirrors the backend (sidebar = route guard) but is never the control.
5. Cross-references are ownership-checked at write time: facility, asset, component, data-source default asset and MAVLink
`system_id_map` targets, HUMS sensor asset/component (`test_airframes`, `test_hums_thresholds`).

## Ingest and acquisition hardening
* Body cap 25 MB (413); recursion-bomb / binary / non-finite payloads → 4xx, never 500.
* Per-event SAVEPOINT: a hostile event cannot poison the batch. Events with no valid measurement are rejected.
* **MAVLink**: CRC_EXTRA, sequence tracking, component filtering, arrival-time stamping, **MAVLink-2 signature
  verification with replay protection, unsigned frames refused when a key is configured, fail-closed on a missing key**.
* **Listeners** refuse to start without a CIDR allow-list and/or signing (UDP/TCP) or TLS/loopback (MQTT); bounded buffers;
  per-organization back-pressure; TCP connection cap and idle timeout.
* **Webhooks**: DJI (HMAC, 503 until configured) and generic (`X-Kota-Signature` HMAC over `timestamp.body`, ±5 min,
  one acceptance per signature, identical 401 for every failure so the endpoint is not an oracle).
* **OEM polling SSRF guard**: https only, no credentials in URL, every resolved address must be public (loopback,
  private, link-local incl. cloud metadata, CGNAT, multicast, reserved, IPv4-mapped forms refused), no redirects,
  streaming size cap; private hosts only via operator config `OEM_ALLOWED_PRIVATE_HOSTS`. Residual risk: DNS rebinding
  between validation and connect — run workers with egress filtering.

## Secrets
Environment only (`SECRET_KEY`/`JWT_SECRET_KEY`, DB URL, `DJI_WEBHOOK_SECRET`, provider keys). Data-source credentials
are **references** (`secret_reference`) resolved at runtime by `app/core/secrets.py` from `KOTA_SECRET_<REF>`
environment variables (populate from your secret manager); values are never stored on rows, returned by the API or
logged (`test_logs_never_contain_passwords_tokens_secrets_or_raw_telemetry`). The test billing provider is refused in
production. Startup refuses default JWT/DB placeholders outside development.

## Rate limiting (pluggable: in-memory or shared Redis)
Auth endpoints and evidence upload: per-IP dependency limits. Everything else: middleware policies `webhook` (IP),
`ingest` (tenant), `lisa` (user), `analytics` (user), `admin` (user), `default` (tenant), overridable with
`RATE_LIMIT_OVERRIDES='{"lisa":"10/60","default":"off"}'`; tenant/user keys come from a signature-verified token, anything
else is keyed by client IP (`X-Forwarded-For` only if `RATE_LIMIT_TRUST_FORWARDED_FOR`). 429 + `Retry-After`,
`kota_rate_limited_total{policy}`.

**Backends** (`app/core/rate_limit.py`, one `RateLimiter` interface): `RATE_LIMIT_BACKEND=memory` (default; process-local,
deterministic, used by tests and single-process deployments) or `redis` (shared across API workers/instances through
`REDIS_URL`; `pip install aerocomply-backend[redis]`). With `memory` and several workers each process counts on its own, so
the effective limit is multiplied — use `redis` for multi-instance deployments. The Redis server is deployment infrastructure.

**Failure policy**: when the shared store fails, the auth/upload dependency limits and every policy in
`RATE_LIMIT_FAIL_CLOSED_POLICIES` (default `webhook`, `admin`) answer **503** (fail closed — a limiter outage must not open
brute-force or unauthenticated-ingest paths); every other policy degrades to a local in-memory count (fail open, less
accurate). Backend failures are counted in `kota_rate_limit_backend_errors_total{policy,outcome}`. A bug inside the
middleware itself still allows the request (logged, `kota_rate_limiter_errors_total`).
Tested deterministically (fake clock, fake Redis shared by two "instances", broken Redis): `tests/unit/test_rate_limiter_backends.py`.
No per-account lockout after repeated failed logins.

## Audit
Compliance-state changes (obligation creation and every status change from an applicability evaluation), inspection
requirements, assessments, M7 signal lifecycle, HUMS sensor limits, retention policies, job requeue, import mapping
deletion, subscription/billing changes and platform actions write append-only audit events (DB trigger blocks
UPDATE/DELETE) with previous values where a value changes (`test_audit_coverage`, `test_hums_thresholds`).
Telemetry batches write one summary audit row per batch; per-event provenance is `telemetry_event_logs`.

## Known gaps
* Running Redis for the shared limiter (and validating it against a real Redis), account lockout, WAF — infrastructure/EXTERNAL.
* Signing interoperability with a real autopilot; a signed-frame timestamp window against wall clock is not enforced
  (only monotonicity), because vehicles define their own clock origin.
* The API metrics endpoint is protected by platform permission, not network policy; restrict at the proxy too. The worker/listener
  metrics endpoint (`METRICS_PORT`) has no authentication of its own and binds 127.0.0.1 by default.
* No external penetration test or dependency-CVE gate: EXTERNAL VALIDATION REQUIRED.
