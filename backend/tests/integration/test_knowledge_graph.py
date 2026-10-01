"""Knowledge graph: PostgreSQL-backed lineage traversal (no second store), tenant-isolated, bounded, cycle-safe."""
from __future__ import annotations

import uuid

import pytest

from app.services import knowledge_graph as kg
from tests.integration.test_acquisition_pipeline import _drone, _ingest, _org, _source
from tests.unit.test_m20_mavlink_integrity import heartbeat, vibration


def _excursion(client, h, reg):
    asset = _drone(client, h, reg=reg)
    sid = _source(client, h, "MAVLINK", {"system_id_map": {"1": asset}})
    frames = [heartbeat(seq=1)] + [vibration(1.5, 1.6, 1.7, seq=2 + i) for i in range(6)] + [vibration(45.0, 52.0, 48.0, seq=9)]
    assert _ingest(client, h, sid, b"".join(frames)).status_code in (200, 202)
    return asset


def _graph(client, h, node_type, node_id, depth=3):
    return client.get("/api/v1/digital-twin/graph", headers=h, params={"node_type": node_type, "node_id": node_id, "depth": depth})


def test_lineage_connects_sensor_exceedance_finding_signal_and_asset(client, db_session):
    _, h = _org(client, db_session, "kg1")
    asset = _excursion(client, h, "KG-1")
    r = _graph(client, h, "ASSET", asset, depth=4)
    assert r.status_code == 200, r.text
    g = r.json()
    types = {n["type"] for n in g["nodes"]}
    assert {"ASSET", "SENSOR", "EXCEEDANCE", "FINDING", "SIGNAL"} <= types, types
    rels = {e["rel"] for e in g["edges"]}
    assert {"INSTALLED_ON", "OBSERVED_BY", "RAISED", "CONCERNS_ASSET"} <= rels, rels
    assert g["root"] == {"type": "ASSET", "id": asset} and g["truncated"] is False
    # walking from the finding reaches the same asset and the signal that cites it
    fid = next(n["id"] for n in g["nodes"] if n["type"] == "FINDING")
    from_finding = _graph(client, h, "FINDING", fid, depth=2).json()
    assert {"ASSET", "EXCEEDANCE", "SIGNAL"} <= {n["type"] for n in from_finding["nodes"]}
    assert any(e["rel"] == "EVIDENCED_BY" for e in from_finding["edges"])
    assert all(n["type"] and uuid.UUID(n["id"]) for n in g["nodes"])


def test_depth_is_respected(client, db_session):
    _, h = _org(client, db_session, "kg2")
    asset = _excursion(client, h, "KG-2")
    zero = _graph(client, h, "ASSET", asset, depth=0).json()
    assert [n["type"] for n in zero["nodes"]] == ["ASSET"] and zero["edges"] == []
    one = _graph(client, h, "ASSET", asset, depth=1).json()
    assert "EXCEEDANCE" not in {n["type"] for n in one["nodes"]}          # two hops away
    assert _graph(client, h, "ASSET", asset, depth=9).status_code == 422   # above the hard cap


def test_other_tenant_cannot_start_from_or_see_foreign_nodes(client, db_session):
    _, ha = _org(client, db_session, "kg3a")
    _, hb = _org(client, db_session, "kg3b")
    asset_a = _excursion(client, ha, "KG-3A")
    assert _graph(client, hb, "ASSET", asset_a).status_code == 404        # not a disclosure oracle: same as missing
    assert _graph(client, hb, "ASSET", str(uuid.uuid4())).status_code == 404
    mine = _excursion(client, hb, "KG-3B")
    ids_b = {n["id"] for n in _graph(client, hb, "ASSET", mine, depth=4).json()["nodes"]}
    ids_a = {n["id"] for n in _graph(client, ha, "ASSET", asset_a, depth=4).json()["nodes"]}
    assert ids_a.isdisjoint(ids_b)


def test_unknown_node_type_and_unauthenticated(client, db_session):
    _, h = _org(client, db_session, "kg4")
    assert _graph(client, h, "SPACESHIP", str(uuid.uuid4())).status_code == 422
    assert client.get("/api/v1/digital-twin/graph", params={"node_type": "ASSET", "node_id": str(uuid.uuid4())}).status_code == 401


# ------------------------------------------------------------------ pure traversal properties (no database)
class FakeRepo:
    """A ring A-B-C-A plus a hub with many leaves: proves cycle safety and the node cap."""

    def __init__(self, n_leaves=0):
        self.org = uuid.uuid4()
        self.a, self.b, self.c = (kg.Node("ASSET", uuid.uuid4()), kg.Node("COMPONENT", uuid.uuid4()), kg.Node("SENSOR", uuid.uuid4()))
        self.leaves = [kg.Node("FINDING", uuid.uuid4()) for _ in range(n_leaves)]
        self.edges = [kg.Edge(self.a, self.b, "X"), kg.Edge(self.b, self.c, "Y"), kg.Edge(self.c, self.a, "Z")]
        self.edges += [kg.Edge(self.a, leaf, "L") for leaf in self.leaves]

    def exists(self, organization_id, node):
        return organization_id == self.org

    def neighbors(self, organization_id, node):
        assert organization_id == self.org
        return [e for e in self.edges if node in (e.source, e.target)]


def test_traversal_terminates_on_cycles_and_dedupes():
    repo = FakeRepo()
    g = kg.traverse(repo, repo.org, repo.a, depth=4)
    assert len(g.nodes) == 3 and len(g.edges) == 3 and g.truncated is False


def test_traversal_node_cap_marks_truncated():
    repo = FakeRepo(n_leaves=50)
    g = kg.traverse(repo, repo.org, repo.a, depth=2, max_nodes=10)
    assert len(g.nodes) == 10 and g.truncated is True


def test_traversal_requires_the_start_node_in_the_callers_organization():
    repo = FakeRepo()
    with pytest.raises(kg.NotFoundError):
        kg.traverse(repo, uuid.uuid4(), repo.a)


def test_lisa_tool_trace_lineage_is_registered_with_permission_and_feature():
    from app.services.ai.tools import TOOL_REGISTRY

    spec = next(t for t in TOOL_REGISTRY if t.name == "trace_lineage")
    assert spec.required_permission is not None and spec.required_feature == "digital_twin"
