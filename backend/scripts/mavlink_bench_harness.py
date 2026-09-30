"""MAVLink bench harness: measure what a REAL link delivers, with the SAME parser production uses.

This is the tool for MAVLINK_HARDWARE_VALIDATION_PLAN.md. It reads raw MAVLink bytes from a source,
runs them through `MAVLinkConnector` (CRC/CRC_EXTRA, per-(sysid,compid) sequence, duplicate/late/loss
accounting, component filtering) and writes JSON-lines evidence. Optionally it also forwards the bytes to
a running Kota API (`POST /data-sources/{id}/ingest`) and records request latency and failures.

Sources
  sim                          synthesised frames with configurable loss/duplication/corruption (SELF-TEST ONLY --
                               proves the harness and parser, says NOTHING about RF hardware)
  file:PATH                    replay a raw capture (e.g. from `mavlink-router --tlog` or a serial dump)
  udp://HOST:PORT              listen for UDP datagrams (GCS/router output)
  serial:PORT:BAUD             serial radio (needs `pip install pyserial`)

Examples
  python -m scripts.mavlink_bench_harness --source sim --duration 5 --loss 0.2 --dup 0.05 --corrupt 0.02
  python -m scripts.mavlink_bench_harness --source udp://0.0.0.0:14550 --duration 1800 \
      --api http://localhost:8001 --data-source <uuid> --token $KOTA_TOKEN --log bench_TEST01.jsonl
  python -m scripts.mavlink_bench_harness --source file:capture.bin --expect-loss-max 0.02

Exit status is non-zero when an acceptance threshold (--expect-*) is violated, so it can gate a bench run.
"""

from __future__ import annotations

import argparse
import json
import random
import socket
import struct
import sys
import time
from collections import defaultdict
from pathlib import Path

from app.services.edge.mavlink_connector import MAVLinkConnector, mavlink_checksum


def build_v2(msgid: int, payload: bytes, *, seq: int, sysid: int = 1, compid: int = 1) -> bytes:
    payload = payload.rstrip(b"\x00") or b"\x00"
    header = struct.pack("<BBBBBBB", len(payload), 0, 0, seq & 0xFF, sysid, compid, msgid & 0xFF) + bytes(
        [(msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF]
    )
    crc = mavlink_checksum(header + payload, msgid)
    return b"\xfd" + header + payload + struct.pack("<H", crc)


def simulate(duration: float, rate_hz: float, vehicles: int, loss: float, dup: float, corrupt: float, seed: int):
    """Yield (chunk_bytes, meta) at wall-clock pace. `meta` counts what was truly injected."""
    rng = random.Random(seed)
    seqs = defaultdict(int)
    injected = {"sent": 0, "dropped": 0, "duplicated": 0, "corrupted": 0}
    t_end, period = time.monotonic() + duration, 1.0 / rate_hz
    nxt = time.monotonic()
    while time.monotonic() < t_end:
        for sysid in range(1, vehicles + 1):
            seqs[sysid] = (seqs[sysid] + 1) & 0xFF
            frame = build_v2(241, struct.pack("<QfffIII", int(time.time() * 1e6), 1.6, 1.6, 1.6, 0, 0, 0),
                             seq=seqs[sysid], sysid=sysid)
            injected["sent"] += 1
            if rng.random() < loss:
                injected["dropped"] += 1
                continue
            if rng.random() < corrupt:
                frame = frame[:10] + bytes([frame[10] ^ 0xFF]) + frame[11:]
                injected["corrupted"] += 1
            yield frame, injected
            if rng.random() < dup:
                injected["duplicated"] += 1
                yield frame, injected
        nxt += period
        time.sleep(max(0.0, nxt - time.monotonic()))


def read_file(path: str, chunk: int = 512):
    data = Path(path).read_bytes()
    for i in range(0, len(data), chunk):
        yield data[i:i + chunk], {}


def read_udp(host: str, port: int, duration: float, log):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(1.0)
    t_end, timeouts = time.monotonic() + duration, 0
    while time.monotonic() < t_end:
        try:
            data, _ = sock.recvfrom(65535)
            yield data, {"link_timeouts": timeouts}
        except TimeoutError:
            timeouts += 1
            log({"event": "link_timeout", "count": timeouts})


def read_serial(port: str, baud: int, duration: float):
    try:
        import serial  # type: ignore[import-not-found]
    except ImportError:  # pragma: no cover - hardware path
        sys.exit("pyserial is required for serial sources: pip install pyserial")
    with serial.Serial(port, baud, timeout=0.5) as s:  # pragma: no cover - hardware path
        t_end = time.monotonic() + duration
        while time.monotonic() < t_end:
            data = s.read(512)
            if data:
                yield data, {}


def run(args: argparse.Namespace) -> dict:
    log_fh = open(args.log, "a", encoding="utf-8") if args.log else None

    def log(obj: dict) -> None:
        obj["t"] = round(time.time(), 3)
        if log_fh:
            log_fh.write(json.dumps(obj) + "\n")

    if args.source == "sim":
        chunks = simulate(args.duration, args.rate, args.vehicles, args.loss, args.dup, args.corrupt, args.seed)
    elif args.source.startswith("file:"):
        chunks = read_file(args.source[5:])
    elif args.source.startswith("udp://"):
        host, port = args.source[6:].rsplit(":", 1)
        chunks = read_udp(host, int(port), args.duration, log)
    elif args.source.startswith("serial:"):
        _, port, baud = args.source.split(":")
        chunks = read_serial(port, int(baud), args.duration)
    else:
        sys.exit(f"unknown source {args.source!r}")

    conn = MAVLinkConnector(connector_id="bench")
    conn.connect()
    frames_events = 0
    api_ok = api_fail = 0
    api_lat: list[float] = []
    last_injected: dict = {}
    client = None
    if args.api:
        import httpx

        client = httpx.Client(base_url=args.api, headers={"Authorization": f"Bearer {args.token}",
                                                          "Content-Type": "application/octet-stream"}, timeout=15)
    t0 = time.monotonic()
    for chunk, injected in chunks:
        last_injected = injected or last_injected
        events = conn.feed_bytes(chunk)
        frames_events += len(events)
        if client is not None:
            t1 = time.perf_counter()
            try:
                r = client.post(f"/api/v1/data-sources/{args.data_source}/ingest", content=chunk)
                (api_ok := api_ok + 1) if r.status_code == 200 else (api_fail := api_fail + 1)
                api_lat.append((time.perf_counter() - t1) * 1000)
            except Exception as exc:  # noqa: BLE001 - a link/API failure is evidence, not a crash
                api_fail += 1
                log({"event": "api_error", "error": type(exc).__name__})
        if frames_events and frames_events % 50 == 0:
            log({"event": "progress", "events": frames_events, "integrity": dict(conn.integrity)})
    elapsed = time.monotonic() - t0

    lost, accepted = conn.integrity["lost"], frames_events
    summary = {
        "source": args.source, "elapsed_s": round(elapsed, 2), "events_decoded": accepted,
        "integrity": dict(conn.integrity), "vehicles_seen": sorted(conn.vehicles),
        "loss_ratio_measured": round(lost / (lost + accepted), 4) if (lost + accepted) else None,
        "injected_ground_truth": last_injected or None,
        "api": {"ok": api_ok, "failed": api_fail,
                "latency_ms_p50": round(sorted(api_lat)[len(api_lat) // 2], 1) if api_lat else None,
                "latency_ms_max": round(max(api_lat), 1) if api_lat else None},
        "verdict": [],
    }
    fails = summary["verdict"]
    if args.expect_loss_max is not None and (summary["loss_ratio_measured"] or 0) > args.expect_loss_max:
        fails.append(f"loss {summary['loss_ratio_measured']} > {args.expect_loss_max}")
    if args.expect_crc_errors_max is not None and conn.integrity["crc_errors"] > args.expect_crc_errors_max:
        fails.append(f"crc_errors {conn.integrity['crc_errors']} > {args.expect_crc_errors_max}")
    if args.expect_vehicles is not None and len(conn.vehicles) != args.expect_vehicles:
        fails.append(f"vehicles seen {len(conn.vehicles)} != {args.expect_vehicles}")
    if args.expect_api_failures_max is not None and api_fail > args.expect_api_failures_max:
        fails.append(f"api failures {api_fail} > {args.expect_api_failures_max}")
    summary["pass"] = not fails
    log({"event": "summary", **summary})
    if log_fh:
        log_fh.close()
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True)
    ap.add_argument("--duration", type=float, default=10.0, help="seconds (sim/udp/serial)")
    ap.add_argument("--rate", type=float, default=20.0, help="sim frames/s per vehicle")
    ap.add_argument("--vehicles", type=int, default=1)
    ap.add_argument("--loss", type=float, default=0.0, help="sim: probability a frame is dropped")
    ap.add_argument("--dup", type=float, default=0.0, help="sim: probability a frame is duplicated")
    ap.add_argument("--corrupt", type=float, default=0.0, help="sim: probability a frame is corrupted")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--log", help="append JSON-lines evidence here")
    ap.add_argument("--api", help="Kota base URL, e.g. http://localhost:8001")
    ap.add_argument("--data-source", help="ACTIVE MAVLINK data source id")
    ap.add_argument("--token", help="bearer token")
    ap.add_argument("--expect-loss-max", type=float)
    ap.add_argument("--expect-crc-errors-max", type=int)
    ap.add_argument("--expect-vehicles", type=int)
    ap.add_argument("--expect-api-failures-max", type=int)
    args = ap.parse_args(argv)
    if args.api and not (args.data_source and args.token):
        ap.error("--api needs --data-source and --token")
    summary = run(args)
    print(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
