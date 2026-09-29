# M20 — Subscription Lifecycle Validation

Evidence: `backend/tests/integration/test_m20_commercial_entitlement_lifecycle.py` (service + API) and live run against a migrated clone of the dev database (see COMMERCIAL_SECURITY_REPORT).

| Scenario | Result |
|---|---|
| TRIALING → PAST_DUE → grants (ACTIVE resolution) | verified |
| CANCELED → NO_SUBSCRIPTION, empty features | verified |
| `ends_at` in the past → NO_SUBSCRIPTION | verified |
| Plan A → Plan B same suite: features + limits refresh, audit has `previous_plan_id` | verified |
| Plan change to another suite | rejected `suite_plan_mismatch`, subscription unchanged |
| Plan change to inactive plan | rejected `inactive_plan` |
| Scheduled subscription carries plan's `suite_id` | fixed + verified |
| Cancelled subscription with live token | next call 403 |
| Org suspended with live token | next call 401 |
| Feature override disable/enable/remove | effective map follows each step; audit has previous value |
| Limit override 25 → 50 → 1 | effective limit follows; asset creation blocked at 1 |

Not implemented (documented, not invented): SUSPENDED/EXPIRED subscription statuses, auto-activation of SCHEDULED rows, billing/payment behaviour (no billing model exists).
