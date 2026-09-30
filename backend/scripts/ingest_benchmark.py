"""Ingest/read benchmark over real HTTP against a running API (use a SCRATCH database, never production).

  python -m scripts.ingest_benchmark --api http://localhost:8001 --email X --password Y \
      --asset-registration BRW-001 --data-source <CSV_BATCH source id> --sizes 100 1000 10000 --batch 500

Sends CSV_BATCH events in batches of --batch (unique timestamps => no dedup), then times the telemetry read APIs.
Reports wall time, events/s and per-batch latency percentiles. Numbers are for THIS machine + scratch DB only.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx


def batch_csv(reg: str, n: int, start: datetime, offset: int, tag: str) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["asset_id", "sensor_code", "value", "unit", "timestamp"])
    for i in range(n):
        ts = start + timedelta(seconds=offset + i)
        w.writerow([reg, f"BENCH-{tag}", f"{1.0 + (i % 50) / 100:.3f}", "g", ts.strftime("%Y-%m-%dT%H:%M:%SZ")])
    return out.getvalue().encode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--asset-registration", required=True)
    ap.add_argument("--asset-id", required=True)
    ap.add_argument("--data-source", required=True)
    ap.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 10000])
    ap.add_argument("--batch", type=int, default=500)
    a = ap.parse_args()
    B = a.api.rstrip("/") + "/api/v1"
    c = httpx.Client(timeout=300)
    tok = c.post(B + "/auth/login", json={"email": a.email, "password": a.password}).json()["access_token"]
    h = {"Authorization": "Bearer " + tok, "Content-Type": "text/csv"}
    tag = uuid.uuid4().hex[:6]
    start = datetime.now(UTC) - timedelta(days=2)
    offset, results = 0, []
    for size in a.sizes:
        lat, accepted, t0 = [], 0, time.perf_counter()
        sent = 0
        while sent < size:
            n = min(a.batch, size - sent)
            t1 = time.perf_counter()
            r = c.post(f"{B}/data-sources/{a.data_source}/ingest", headers=h,
                       content=batch_csv(a.asset_registration, n, start, offset, tag))
            lat.append((time.perf_counter() - t1) * 1000)
            r.raise_for_status()
            accepted += r.json()["accepted"]
            sent += n
            offset += n
        wall = time.perf_counter() - t0
        lat.sort()
        results.append({"events": size, "accepted": accepted, "wall_s": round(wall, 2),
                        "events_per_s": round(size / wall, 1),
                        "batch_ms_p50": round(statistics.median(lat), 1),
                        "batch_ms_p95": round(lat[int(len(lat) * 0.95) - 1] if len(lat) > 1 else lat[0], 1)})
    ah = {"Authorization": "Bearer " + tok}
    reads = {}
    for name, path in {"status": "status", "latest": "latest", "history": "history?limit=500", "flights": "flights"}.items():
        ts = []
        for _ in range(5):
            t1 = time.perf_counter()
            r = c.get(f"{B}/telemetry/assets/{a.asset_id}/{path}", headers=ah)
            ts.append((time.perf_counter() - t1) * 1000)
        reads[name] = {"status": r.status_code, "ms_median": round(statistics.median(ts), 1)}
    print(json.dumps({"ingest": results, "reads_after": reads}, indent=2))


if __name__ == "__main__":
    main()
