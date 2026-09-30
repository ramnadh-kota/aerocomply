"""Ingest profiling harness (run explicitly: pytest tests/perf -s). Reports SQL statements/event and top CPU."""
import cProfile
import collections
import io
import pstats
import time

from sqlalchemy import event

from tests.integration.test_acquisition_pipeline import _csv, _drone, _ingest, _org, _source


def test_profile_csv_ingest(client, db_session):
    org_id, h = _org(client, db_session)
    reg = "PROF-1"
    _drone(client, h, reg=reg)
    sid = _source(client, h, "CSV_BATCH")
    n = 300
    rows = [{"asset_id": reg, "sensor_code": "VIB", "value": f"{1 + (i % 50) / 100:.2f}", "unit": "g",
             "timestamp": f"2026-01-01T{(i // 3600) % 24:02d}:{(i // 60) % 60:02d}:{i % 60:02d}Z"} for i in range(n)]
    body = _csv(rows)
    stmts = collections.Counter()
    engine = db_session.get_bind()

    def before(conn, cur, statement, *a):
        stmts[" ".join(statement.split())[:90]] += 1

    event.listen(engine, "before_cursor_execute", before)
    pr = cProfile.Profile()
    t0 = time.perf_counter()
    pr.enable()
    r = _ingest(client, h, sid, body)
    pr.disable()
    wall = time.perf_counter() - t0
    event.remove(engine, "before_cursor_execute", before)
    assert r.status_code == 200, r.text
    total = sum(stmts.values())
    print(f"\nEVENTS={n} accepted={r.json()['accepted']} wall={wall:.2f}s ({wall / n * 1000:.1f} ms/event) statements={total} ({total / n:.1f}/event)")
    for s, c in stmts.most_common(14):
        print(f"{c:6d}  {s}")
    out = io.StringIO()
    pstats.Stats(pr, stream=out).sort_stats("cumulative").print_stats(22)
    print(out.getvalue()[:5000])
