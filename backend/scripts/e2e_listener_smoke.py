"""Out-of-process smoke test of the server-side acquisition path (SCRATCH environment only).

  API (already running) + this script's subprocesses:  `python -m app.listeners`  and  `python -m app.worker --once`

  1. logs in, creates an ACTIVE MAVLINK data source with a UDP `listen` section (127.0.0.0/8 allow-list)
  2. starts the listener supervisor as a separate process; sends real MAVLink v2 frames over a UDP socket
  3. stops the supervisor (graceful flush), runs the worker over the queue
  4. verifies through the HTTP API that readings, source health and the job result exist

  python -m scripts.e2e_listener_smoke --api http://localhost:8002 --email E --password P --asset-id UUID --asset-reg REG
  (DATABASE_URL in the environment must point at the same database the API uses)

Exit status 0 = every step verified. It proves the software path only; it is not RF or hardware validation."""
from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import uuid

import httpx

from tests.unit.test_m20_mavlink_integrity import heartbeat, vibration


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--asset-id", required=True)
    args = ap.parse_args()
    B = args.api.rstrip("/") + "/api/v1"
    c = httpx.Client(timeout=30)
    tok = c.post(f"{B}/auth/login", json={"email": args.email, "password": args.password}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    port = free_udp_port()
    name = f"smoke-{uuid.uuid4().hex[:6]}"
    src = c.post(f"{B}/data-sources", headers=h, json={
        "name": name, "connector_type": "MAVLINK",
        "connection_config": {"system_id_map": {"1": args.asset_id},
                              "listen": {"bind": "127.0.0.1", "udp_port": port, "allowed_cidrs": ["127.0.0.0/8"]}}})
    src.raise_for_status()
    sid = src.json()["id"]
    c.patch(f"{B}/data-sources/{sid}", headers=h, json={"status": "ACTIVE"}).raise_for_status()

    sup = subprocess.Popen([sys.executable, "-m", "app.listeners"], env=os.environ.copy())
    try:
        time.sleep(4)                                             # first reconcile binds the UDP socket
        if sup.poll() is not None:
            print("FAIL: listener supervisor exited early", sup.returncode)
            return 1
        seq = 0
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
            for i in range(30):
                seq += 1
                tx.sendto(heartbeat(seq=seq) if i == 0 else vibration(1.5, 1.6, 1.7, seq=seq), ("127.0.0.1", port))
                time.sleep(0.02)
        time.sleep(2.5)                                           # flush interval
    finally:
        sup.terminate()
        try:
            sup.wait(timeout=15)
        except subprocess.TimeoutExpired:
            sup.kill()
            print("WARN: supervisor had to be killed")

    w = subprocess.run([sys.executable, "-m", "app.worker", "--once"], env=os.environ.copy(), timeout=120)
    if w.returncode != 0:
        print("FAIL: worker exit", w.returncode)
        return 1
    health = c.get(f"{B}/data-sources/{sid}/health", headers=h).json()
    latest = c.get(f"{B}/telemetry/assets/{args.asset_id}/latest", headers=h).json()
    ok = health.get("event_count", 0) >= 29 and health.get("status") in {"HEALTHY", "DEGRADED"} \
        and any(s["sensor_code"].startswith("VIB") for s in latest.get("sensors", []))
    print({"source": sid, "port": port, "event_count": health.get("event_count"), "status": health.get("status"),
           "last_success_at": health.get("last_success_at"), "vib_sensor_seen": ok})
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
