"""Standalone metrics endpoint for processes that do not serve the API (the job worker and the listener supervisor).

The API exposes its registry at GET /api/v1/platform/metrics behind platform auth. A worker or listener process has no
HTTP surface, so its counters would be invisible; `start_metrics_server` serves the same Prometheus text on a tiny
stdlib HTTP server in a daemon thread:

    GET /metrics   Prometheus text exposition (this process's registry)
    GET /healthz   200 "ok"

Off unless a port is given (`--metrics-port` / `METRICS_PORT`). It binds 127.0.0.1 by default: expose it to a scraper
through the host's network policy (set `METRICS_HOST=0.0.0.0` only on a private network). Metrics carry no tenant,
user or asset identifiers (see metrics.py), so the endpoint has no authentication of its own.
"""

from __future__ import annotations

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app.core.metrics import REGISTRY


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        path = self.path.split("?")[0]
        if path == "/metrics":
            body, ctype = REGISTRY.render().encode(), "text/plain; version=0.0.4; charset=utf-8"
        elif path == "/healthz":
            body, ctype = b"ok", "text/plain; charset=utf-8"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:  # silence per-request stderr noise
        return


def start_metrics_server(port: int | None = None, host: str | None = None) -> ThreadingHTTPServer | None:
    """Start the endpoint (returns the server, or None when no port is configured). Port 0 picks a free port."""
    if port is None:
        raw = os.environ.get("METRICS_PORT", "").strip()
        if not raw:
            return None
        port = int(raw)
    server = ThreadingHTTPServer((host or os.environ.get("METRICS_HOST", "127.0.0.1"), port), _Handler)
    threading.Thread(target=server.serve_forever, name="metrics-server", daemon=True).start()
    return server
