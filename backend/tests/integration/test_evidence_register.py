"""GET /evidence: the tenant-scoped evidence register."""
import uuid

from tests.integration.test_acquisition_pipeline import _drone, _org


def _mk(client, h, title, **extra):
    r = client.post("/api/v1/evidence", headers=h, json={"title": title, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def test_register_lists_only_own_tenant_newest_first_with_filters_and_paging(client, db_session):
    _, ha = _org(client, db_session, "evA")
    _, hb = _org(client, db_session, "evB")
    asset = _drone(client, ha, reg="EV-1")
    a1 = _mk(client, ha, "first", asset_id=asset)
    a2 = _mk(client, ha, "second")
    a3 = _mk(client, ha, "third", asset_id=asset)
    _mk(client, hb, "other tenant")

    body = client.get("/api/v1/evidence", headers=ha).json()
    assert body["total"] == 3 and {e["title"] for e in body["items"]} == {"first", "second", "third"}
    stamps = [e["created_at"] for e in body["items"]]
    assert stamps == sorted(stamps, reverse=True)          # newest first (rows of one test transaction share now())
    assert {e["id"] for e in client.get("/api/v1/evidence", headers=hb).json()["items"]}.isdisjoint({a1["id"], a2["id"], a3["id"]})

    by_asset = client.get("/api/v1/evidence", headers=ha, params={"asset_id": asset}).json()
    assert by_asset["total"] == 2 and {e["title"] for e in by_asset["items"]} == {"first", "third"}
    assert client.get("/api/v1/evidence", headers=ha, params={"asset_id": str(uuid.uuid4())}).json()["total"] == 0
    assert client.get("/api/v1/evidence", headers=ha, params={"status": "NOPE"}).json()["total"] == 0

    page = client.get("/api/v1/evidence", headers=ha, params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["limit"] == 2
    assert client.get("/api/v1/evidence", headers=ha, params={"limit": 100000}).json()["limit"] == 200   # bounded


def test_register_requires_authentication_and_permission(client, db_session):
    assert client.get("/api/v1/evidence").status_code == 401
    assert client.get("/api/v1/evidence", headers={"Authorization": "Bearer nope"}).status_code == 401
