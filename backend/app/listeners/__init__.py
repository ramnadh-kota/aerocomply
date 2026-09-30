"""Server-side acquisition listeners (UDP MAVLink, MQTT). Run with:  python -m app.listeners

A listener owns ONE data source (and therefore one tenant, taken from the data source row, never from the wire). It
does no telemetry processing itself: received bytes are enqueued as `acquisition.ingest` jobs (app/services/
job_service.py) and a worker runs them through the same acquisition pipeline the HTTP API uses, so validation,
normalization, dedup, health evidence and tenant isolation are identical for every entry path.
"""
