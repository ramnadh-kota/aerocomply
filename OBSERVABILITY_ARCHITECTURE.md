# Observability Architecture (as implemented, 2026-09-30)

## Logging
structlog, JSON in production. Every request binds `request_id` (echoed as `X-Request-ID`), `endpoint`, and — once
authenticated — `organization_id` and `user_id`. Ingestion binds `data_source_id` and `connector_type`. Worker logs bind
`job_id`, `job_type`, `organization_id`, `data_source_id` and use the **originating correlation id** as `request_id`
(`listener-udp`, `listener-mqtt`, `webhook`, `schedule-poll`, or the HTTP request id that enqueued the job), so one
payload can be followed from socket/HTTP request to worker outcome. Passwords, JWTs, resolved secrets and raw telemetry
payloads are never logged (`test_logs_never_contain_passwords_tokens_secrets_or_raw_telemetry`).

## Health endpoints
| Endpoint | Meaning |
|---|---|
| `GET /health`, `/api/v1/health` | liveness only |
| `GET /api/v1/health/ready` | 200 only when the database answers **and** its Alembic revision equals this build's head (503 `schema_mismatch` otherwise, 503 `unavailable` if the DB is down); also reports `jobs {queued, dead, oldest_due_seconds}` |

## Metrics
`GET /api/v1/platform/metrics` (Prometheus text, `PLATFORM_MANAGE`). The registry is **in-process**: each API/worker/
listener process exposes only its own counters — scrape every API instance and sum in Prometheus. The **DB-derived gauges**
below are exact from any API instance. The worker and listener processes have no API, so they serve their own registry on a
small stdlib HTTP endpoint (`app/core/metrics_server.py`): `python -m app.worker --metrics-port 9101` /
`METRICS_PORT=9102 python -m app.listeners` expose `GET /metrics` (Prometheus text) and `GET /healthz` on 127.0.0.1
(`METRICS_HOST` to change; off unless a port is set). The format is Prometheus/OpenMetrics-compatible; no vendor is required.

| Metric | Type | Labels |
|---|---|---|
| `kota_http_requests_total`, `kota_http_request_duration_seconds` | counter/histogram | method, route template, status |
| `kota_auth_failures_total`, `kota_authorization_failures_total` | counter | route |
| `kota_rate_limited_total`, `kota_rate_limiter_errors_total`, `kota_rate_limit_backend_errors_total` | counter | policy (, outcome) |
| `kota_hums_evaluations_total`, `kota_hums_evaluation_duration_seconds`, `kota_hums_exceedances_total` | counter/histogram | outcome (ok/failed), severity |
| `kota_m7_signals_total` | counter | event (created / acknowledged / in_review / resolved / dismissed), signal_type |
| `kota_telemetry_newest_event_age_seconds`, `kota_telemetry_stale_sources` | gauge | — **DB-derived on scrape** (telemetry freshness) |
| `kota_worker_loop_errors_total`, `kota_worker_last_poll_timestamp_seconds` | counter/gauge | — per worker process (a stale poll timestamp = stuck worker) |
| `kota_ingest_requests_total`, `kota_ingest_events_total`, `kota_ingest_packets_lost_total`, `kota_ingest_duration_seconds`, `kota_ingest_event_age_seconds` | counter/histogram | connector |
| `kota_jobs_total` | counter | type, outcome (succeeded / retry / dead) — per worker process |
| `kota_job_queue` | gauge | status (QUEUED/RUNNING/SUCCEEDED/DEAD/CANCELED) — **DB-derived on scrape** |
| `kota_data_sources` | gauge | health (HEALTHY/DEGRADED/FAILED/INACTIVE) — **DB-derived on scrape**, evidence-based |
| `kota_listener_messages_total`, `kota_listener_dropped_total`, `kota_listener_flushes_total`, `kota_listener_reconnects_total`, `kota_listener_up` | counter/gauge | protocol, outcome/reason — per listener process |
| `kota_lisa_tool_duration_seconds`, `kota_lisa_tool_errors_total` | histogram/counter | tool, code |

Labels use route **templates** and never tenant/user/asset identifiers (bounded cardinality).

## Source health
Evidence-based (`acquisition_service.compute_health_detail`): recorded outcomes, staleness vs `expected_interval_seconds`,
consecutive failures, packet loss, quarantine rate. A source that never ingested is `INACTIVE`, not `HEALTHY`. Listener
refusals, OEM poll failures and signature rejections appear as the source's `last_error`.

## Operator views
`GET /platform/jobs?status=DEAD` (dead-letter queue), `POST /platform/jobs/{id}/requeue` (audited),
`GET /platform/retention/policies`, `POST /platform/retention/run` (dry-run by default).

## Suggested alerts (starting points; unvalidated defaults)
* `kota_job_queue{status="DEAD"} > 0` for 10 m; `/health/ready` `jobs.oldest_due_seconds` > 300 (workers down or stuck)
* `kota_data_sources{health="FAILED"} > 0` for 10 m
* 5xx ratio > 2 % over 5 m; `rate(kota_authorization_failures_total[5m])` spike
* `rate(kota_listener_dropped_total{reason="backpressure"}[5m]) > 0` (workers cannot keep up)
* `rate(kota_ingest_packets_lost_total[5m])` sustained rise (link quality)

## Not implemented
Distributed tracing (OpenTelemetry spans), log-shipping configuration, dashboards-as-code, SLO burn-rate alerts. These need
a chosen vendor/collector and are deployment work, not application code. Alert thresholds above are unvalidated defaults.
