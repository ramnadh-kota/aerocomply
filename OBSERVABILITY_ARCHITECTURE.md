# Observability Architecture

## Logging
structlog, JSON in production. Ingest binds `organization_id`, `data_source_id`, `connector_type`; request
logs carry the route template, never raw payloads. Secrets, tokens and telemetry bodies are not logged
(`test_observability.py` asserts absence of user ids/tokens in metric labels and logs).

## Metrics
`GET /api/v1/platform/metrics` (Prometheus text, requires `PLATFORM_MANAGE`; scrape with a platform service
account token). Registry is **in-process** (`app/core/metrics.py`): each API worker exposes its own counters,
so aggregate across workers/instances in Prometheus (`sum by`). Counters reset on restart.

| Metric | Type | Labels |
|---|---|---|
| `kota_http_requests_total` | counter | method, route template, status |
| `kota_http_request_duration_seconds` | histogram | method, route template |
| `kota_auth_failures_total` / `kota_authorization_failures_total` | counter | - |
| `kota_ingest_requests_total`, `kota_ingest_events_total` | counter | connector_type, outcome |
| `kota_ingest_packets_lost_total` | counter | connector_type |
| `kota_ingest_duration_seconds`, `kota_ingest_event_age_seconds` | histogram | connector_type |
| `kota_lisa_tool_duration_seconds`, `kota_lisa_tool_errors_total` | histogram/counter | tool, code |
| `kota_data_sources` | gauge | health (HEALTHY/DEGRADED/FAILED/INACTIVE), refreshed on scrape (bounded to 5000 sources) |

Labels use route **templates** (no ids) and never include tenant or user identifiers -> bounded cardinality.

## Source health
Evidence-based, not heartbeat-based: `acquisition_service.compute_health_detail` derives status from recorded
ingest outcomes (recent success/failure, staleness vs expected interval). A source that never ingested is
`INACTIVE`, not `HEALTHY`.

## Suggested alerts (starting points; tune from real traffic)
* `kota_data_sources{health="FAILED"} > 0` for 10m
* 5xx ratio: `sum(rate(kota_http_requests_total{status=~"5.."}[5m])) / sum(rate(kota_http_requests_total[5m])) > 0.02`
* `rate(kota_ingest_packets_lost_total[5m])` sustained rise (link quality)
* `kota_ingest_event_age_seconds` p95 above freshness policy
* `rate(kota_authorization_failures_total[5m])` spike (probing)

## Not implemented
Distributed tracing, log shipping config, dashboards-as-code, SLO burn alerts, a dependency-aware health endpoint (`/health` is a liveness check only). Alert thresholds above are unvalidated defaults.
