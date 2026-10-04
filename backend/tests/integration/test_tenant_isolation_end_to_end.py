"""End-to-end tenant isolation over real HTTP.

Two fully seeded tenants (users, subscription/plan, drone, battery, HUMS sensor
+ readings, work order, finding, flight, telemetry mapping, ...). Tenant B then
attacks Tenant A's data through EVERY OpenAPI operation, automatically:

  1. Direct-ID probe: for each operation with path parameters that map to one of
     A's real ids, call it as B. Acceptable answers are 4xx only; a 2xx means B
     reached (or mutated) A's record.
  2. Leak probe: for each operation without path parameters (lists, dashboards,
     aggregates, search, reports, audit, subscriptions, users...), call it as B
     and assert NO identifier belonging to A appears anywhere in the response
     body -- catches list/filter/aggregate leaks that a by-id 404 check cannot.
  3. Sanity: the same list operations as A DO contain A's data (proves the leak
     probe is not vacuously passing because nothing was seeded).

Ids are compared as strings against the raw response text, so nested/embedded
leaks (e.g. an aggregate embedding another tenant's asset id) are caught too.
"""
from __future__ import annotations

import re
import uuid

import pytest

from app.main import app

_SKIP = re.compile(
    r"/auth/|/telemetry/dji/webhook|/health|/platform/|/storage|/export|/data-import/.*/validate|/upload|/live/stream|/stream"
)
_PW = "supersecret123"


def _auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


def _register(client, db_session, name: str, email: str) -> dict:
    from tests.integration.conftest import make_platform_admin_headers

    admin = make_platform_admin_headers(client, db_session)
    r = client.post(
        "/api/v1/auth/register-organization",
        json={"organization_name": name, "admin_email": email,
              "admin_full_name": "Admin", "admin_password": _PW},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=_auth(tok)).json()
    return {"token": tok, "org_id": me["organization_id"], "user_id": me["id"], "email": email}


def _seed(client, db_session, tag: str) -> dict:
    t = _register(client, db_session, f"Iso {tag} {uuid.uuid4().hex[:6]}", f"iso-{tag}-{uuid.uuid4().hex[:6]}@example.com")
    h = _auth(t["token"])
    ids = {"user_id": t["user_id"], "organization_id": t["org_id"]}
    reg = f"ISO-{tag}-{uuid.uuid4().hex[:6].upper()}"

    r = client.post("/api/v1/drones", headers=h, json={"registration": reg, "manufacturer": "DJI", "model": "M300"})
    assert r.status_code == 201, r.text
    ids["asset_id"] = ids["drone_id"] = r.json()["id"]
    ids["registration"] = reg

    r = client.post(f"/api/v1/drones/{ids['asset_id']}/batteries", headers=h, json={"serial_number": f"BATT-{tag}-{uuid.uuid4().hex[:6]}"})
    assert r.status_code == 201, r.text
    ids["battery_id"] = r.json()["id"]

    r = client.post("/api/v1/hums/sensors", headers=h, json={
        "asset_id": ids["asset_id"], "sensor_code": f"SENS-{tag}-{uuid.uuid4().hex[:6]}",
        "sensor_type": "ACCELEROMETER", "measurement_type": "vibration", "unit": "mm/s"})
    assert r.status_code == 200, r.text
    ids["sensor_id"] = r.json()["id"]
    import datetime as dt
    now = dt.datetime.now(dt.UTC)
    readings = [{"recorded_at": (now - dt.timedelta(seconds=20 - i)).isoformat(),
                 "value": 1.0 + 0.1 * i, "unit": "mm/s"} for i in range(20)]
    r = client.post(f"/api/v1/hums/sensors/{ids['sensor_id']}/readings", headers=h, json={"readings": readings})
    assert r.status_code == 200, r.text

    r = client.post("/api/v1/findings", headers=h, json={
        "title": f"ISO finding {tag} {uuid.uuid4().hex[:6]}", "description": "seed", "severity": "MINOR",
        "asset_id": ids["asset_id"]})
    if r.status_code in (200, 201):
        ids["finding_id"] = r.json()["id"]

    r = client.post("/api/v1/work-orders", headers=h, json={
        "asset_id": ids["asset_id"], "work_order_number": f"WO-ISO-{tag}-{uuid.uuid4().hex[:6]}"})
    if r.status_code in (200, 201):
        ids["work_order_id"] = r.json()["id"]

    r = client.post("/api/v1/telemetry/asset-mappings", headers=h, json={
        "source_system": "DJI_FLIGHTHUB", "external_asset_id": f"EXT-{tag}-{uuid.uuid4().hex[:6]}",
        "asset_id": ids["asset_id"]})
    if r.status_code in (200, 201):
        ids["mapping_id"] = r.json().get("id")
    ids = {k: v for k, v in ids.items() if v}
    return {"h": h, "ids": ids, "email": t["email"]}


def _operations():
    for path, ops in sorted(app.openapi()["paths"].items()):
        if _SKIP.search(path):
            continue
        for method in ops:
            if method.lower() in {"get", "post", "put", "patch", "delete"}:
                yield method.upper(), path


_PARAM = re.compile(r"\{([^}]+)\}")


def _fill(path: str, ids: dict) -> str | None:
    """Substitute path params with A's ids by name; None if any is unmappable."""
    def sub(m):
        name = m.group(1)
        if name in ids:
            return ids[name]
        if name == "id" or name.endswith("_id") and name.replace("_id", "") in {"drone", "aircraft"}:
            return ids["asset_id"]
        raise KeyError(name)
    try:
        return _PARAM.sub(sub, path)
    except KeyError:
        return None


@pytest.fixture
def tenants(client, db_session):
    a = _seed(client, db_session, "A")
    b = _seed(client, db_session, "B")
    # every seeded A identifier that must never surface for B
    secrets = {v for k, v in a["ids"].items() if k not in {"organization_id"}} | {a["ids"]["organization_id"], a["email"]}
    return a, b, secrets


def test_seed_is_meaningful(tenants):
    a, b, _ = tenants
    assert {"asset_id", "battery_id", "sensor_id"} <= set(a["ids"]), a["ids"]
    assert a["ids"]["asset_id"] != b["ids"]["asset_id"]


_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")


def _norm(text: str) -> str:
    return _TS_RE.sub("<TS>", _UUID_RE.sub("<ID>", text))


def _random_ids(ids: dict) -> dict:
    return {k: str(uuid.uuid4()) for k in ids}


def test_direct_id_probes_never_reach_other_tenant(client, tenants):
    """B calls every id-addressed operation with A's real ids and again with
    random non-existent ids. Isolation means the two answers are indistinguishable
    (same status, same normalised body): B learns nothing about A's records, neither
    their data nor their existence. A difference is either a data leak or an
    existence oracle."""
    a, b, secrets = tenants
    probed = 0
    bad: list[str] = []
    for method, path in _operations():
        if not _PARAM.search(path):
            continue
        real_url = _fill(path, a["ids"])
        if real_url is None:
            continue
        rand_url = _fill(path, _random_ids(a["ids"]))
        kwargs = {"headers": b["h"]}
        if method in {"POST", "PUT", "PATCH"}:
            kwargs["json"] = {}
        try:
            real = client.request(method, real_url, **kwargs)
            rand = client.request(method, rand_url, **kwargs)
        except Exception as exc:
            bad.append(f"{method} {path} raised {type(exc).__name__}: {str(exc)[:100]}")
            continue
        probed += 1
        if real.status_code >= 500 or rand.status_code >= 500:
            bad.append(f"{method} {path} -> {real.status_code}/{rand.status_code}")
        elif real.status_code != rand.status_code:
            bad.append(f"{method} {path}: A-id -> {real.status_code} but random-id -> {rand.status_code} (existence oracle)")
        elif real.status_code < 400 and _norm(real.text) != _norm(rand.text):
            bad.append(f"{method} {path}: 2xx body differs for A's real id (data leak): {real.text[:120]}")
        elif any(x in real.text for x in secrets if len(x) > 12 and x not in real_url):
            bad.append(f"{method} {path}: response embeds an A identifier")
    print(f"[isolation] id-addressed operations probed: {probed}")
    assert probed >= 40, f"probe covered too little ({probed})"
    assert not bad, "cross-tenant exposure:\n" + "\n".join(bad)


def test_list_and_aggregate_probes_do_not_leak_other_tenant_ids(client, tenants):
    a, b, secrets = tenants
    checked = 0
    leaks: list[str] = []
    a_visible = 0
    for method, path in _operations():
        if method != "GET" or _PARAM.search(path):
            continue
        rb = client.get(path, headers=b["h"])
        checked += 1
        if rb.status_code >= 500:
            leaks.append(f"GET {path} -> {rb.status_code}")
            continue
        hit = [s for s in secrets if s in rb.text]
        if hit:
            leaks.append(f"GET {path} (as B) contains A identifier {hit[0]}")
        ra = client.get(path, headers=a["h"])
        if ra.status_code == 200 and any(s in ra.text for s in secrets):
            a_visible += 1
    print(f"[isolation] list/aggregate operations probed: {checked}; A saw own data on {a_visible}")
    assert checked >= 50, checked
    assert not leaks, "list/aggregate leak:\n" + "\n".join(leaks)
    # sanity: the leak probe is not vacuous -- A sees its own data on several endpoints
    assert a_visible >= 5, f"only {a_visible} endpoints exposed A's own ids to A"


def test_query_filters_cannot_pivot_to_other_tenant(client, tenants):
    a, b, secrets = tenants
    a_asset = a["ids"]["asset_id"]
    for path in ("/api/v1/drones", "/api/v1/work-orders", "/api/v1/findings",
                 "/api/v1/hums/sensors", "/api/v1/telemetry/events"):
        for qs in (f"?asset_id={a_asset}", f"?organization_id={a['ids']['organization_id']}",
                   f"?registration={a['ids']['registration']}", f"?search={a['ids']['registration']}"):
            r = client.get(path + qs, headers=b["h"])
            assert r.status_code < 500, (path, qs, r.status_code)
            assert not any(s in r.text for s in secrets), f"{path}{qs} leaked A data to B"
