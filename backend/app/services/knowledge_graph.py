"""Knowledge-graph traversal over the PostgreSQL source of truth.

Decision (ADR-002/003, docs/AEROSPACE_INTELLIGENCE_GRAPH.md): PostgreSQL is the only store. A graph database would be
a derived, rebuildable read index that is never required for correctness, and ADR-003 says to reconsider it only if
Postgres cannot serve the traversals actually needed. The traversals we need (evidence lineage and impact analysis over
asset / component / sensor / exceedance / finding / M7 signal / work order) are short, bounded and selective, so they
are answered here by a breadth-first walk whose every hop is an indexed, organization-scoped query. No second copy of
the data exists, so there is nothing to synchronise, drift or rebuild.

`GraphRepository` is the seam: a future Neo4j (or other) adapter can implement `neighbors()` and reuse `traverse()`
unchanged. Until a measured need exists no such adapter is built.

Tenant isolation: every query filters on `organization_id`, and the start node must belong to the caller's organization.
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AeroComplyError, NotFoundError
from app.models.asset import Asset
from app.models.component import Component
from app.models.finding import Finding
from app.models.hums import HUMSExceedance, HUMSSensor
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.work_order import WorkOrder

MAX_DEPTH = 4
MAX_NODES = 200

NODE_TYPES = ("ASSET", "COMPONENT", "SENSOR", "EXCEEDANCE", "FINDING", "SIGNAL", "WORK_ORDER")


@dataclass(frozen=True)
class Node:
    type: str
    id: uuid.UUID


@dataclass(frozen=True)
class Edge:
    source: Node
    target: Node
    rel: str


class GraphRepository(Protocol):
    def exists(self, organization_id: uuid.UUID, node: Node) -> bool: ...

    def neighbors(self, organization_id: uuid.UUID, node: Node) -> list[Edge]: ...


@dataclass(frozen=True)
class _Relation:
    """`src` rows reference `dst` through one column; the walk follows it in both directions."""

    rel: str
    src_type: str
    src_model: type
    dst_type: str
    dst_column: object  # InstrumentedAttribute (or expression) on src_model holding the dst id


_RELATIONS: tuple[_Relation, ...] = (
    _Relation("CONCERNS_ASSET", "FINDING", Finding, "ASSET", Finding.asset_id),
    _Relation("CONCERNS_COMPONENT", "FINDING", Finding, "COMPONENT", Finding.component_id),
    _Relation("TRACKED_BY", "FINDING", Finding, "WORK_ORDER", Finding.work_order_id),
    _Relation("INSTALLED_ON", "SENSOR", HUMSSensor, "ASSET", HUMSSensor.asset_id),
    _Relation("MONITORS", "SENSOR", HUMSSensor, "COMPONENT", HUMSSensor.component_id),
    _Relation("OBSERVED_BY", "EXCEEDANCE", HUMSExceedance, "SENSOR", HUMSExceedance.sensor_id),
    _Relation("RAISED", "EXCEEDANCE", HUMSExceedance, "FINDING", HUMSExceedance.finding_id),
    _Relation("ABOUT_ASSET", "SIGNAL", ProactiveSignalRecord, "ASSET", ProactiveSignalRecord.asset_id),
    _Relation("ABOUT_COMPONENT", "SIGNAL", ProactiveSignalRecord, "COMPONENT", ProactiveSignalRecord.component_id),
)

_MODELS: dict[str, type] = {
    "ASSET": Asset, "COMPONENT": Component, "SENSOR": HUMSSensor, "EXCEEDANCE": HUMSExceedance,
    "FINDING": Finding, "SIGNAL": ProactiveSignalRecord, "WORK_ORDER": WorkOrder,
}


def _as_uuid(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


class PostgresGraphRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def exists(self, organization_id: uuid.UUID, node: Node) -> bool:
        model = _MODELS[node.type]
        q = select(model.id).where(model.id == node.id, model.organization_id == organization_id)
        return self._db.execute(q).first() is not None

    def neighbors(self, organization_id: uuid.UUID, node: Node) -> list[Edge]:
        db, out = self._db, []
        for r in _RELATIONS:
            m = r.src_model
            if r.src_type == node.type:  # outgoing: this node's own reference column
                row = db.execute(select(r.dst_column).where(m.id == node.id, m.organization_id == organization_id)).first()
                target = _as_uuid(row[0]) if row else None
                if target is not None:
                    out.append(Edge(node, Node(r.dst_type, target), r.rel))
            if r.dst_type == node.type:  # incoming: rows that reference this node
                ids = db.execute(select(m.id).where(r.dst_column == node.id, m.organization_id == organization_id)).scalars()
                out.extend(Edge(Node(r.src_type, i), node, r.rel) for i in ids)
        if node.type == "SIGNAL" or node.type == "FINDING":
            out.extend(self._signal_finding_edges(organization_id, node))
        return out

    def _signal_finding_edges(self, organization_id: uuid.UUID, node: Node) -> list[Edge]:
        """M7 signals carry the finding they were raised for in contributing_factors_json (evidence lineage)."""
        db = self._db
        col = ProactiveSignalRecord.contributing_factors_json["finding_id"].astext
        if node.type == "SIGNAL":
            row = db.execute(select(col).where(ProactiveSignalRecord.id == node.id,
                                               ProactiveSignalRecord.organization_id == organization_id)).first()
            fid = _as_uuid(row[0]) if row else None
            return [Edge(node, Node("FINDING", fid), "EVIDENCED_BY")] if fid else []
        ids = db.execute(select(ProactiveSignalRecord.id).where(
            col == str(node.id), ProactiveSignalRecord.organization_id == organization_id)).scalars()
        return [Edge(Node("SIGNAL", i), node, "EVIDENCED_BY") for i in ids]


@dataclass
class Subgraph:
    root: Node
    depth: int
    nodes: list[Node]
    edges: list[Edge]
    truncated: bool


def traverse(
    repo: GraphRepository, organization_id: uuid.UUID, start: Node, *, depth: int = 2, max_nodes: int = MAX_NODES
) -> Subgraph:
    """Breadth-first walk to `depth` hops (cycle-safe, node-capped). The start node must exist in the organization."""
    if start.type not in NODE_TYPES:
        raise AeroComplyError(
            f"node type must be one of {', '.join(NODE_TYPES)}", code="invalid_node_type", status_code=422
        )
    depth = max(0, min(depth, MAX_DEPTH))
    max_nodes = max(1, min(max_nodes, MAX_NODES))
    if not repo.exists(organization_id, start):
        raise NotFoundError("Graph node not found", code="graph_node_not_found")

    seen: set[Node] = {start}
    order: list[Node] = [start]
    edges: dict[tuple[Node, Node, str], Edge] = {}
    truncated = False
    queue: deque[tuple[Node, int]] = deque([(start, 0)])
    while queue:
        node, d = queue.popleft()
        if d >= depth:
            continue
        for e in repo.neighbors(organization_id, node):
            other = e.target if e.source == node else e.source
            if other not in seen:
                if len(seen) >= max_nodes:
                    truncated = True
                    continue
                seen.add(other)
                order.append(other)
                queue.append((other, d + 1))
            if other in seen:
                edges[(e.source, e.target, e.rel)] = e
    return Subgraph(start, depth, order, list(edges.values()), truncated)


def get_subgraph(db: Session, *, organization_id: uuid.UUID, node_type: str, node_id: uuid.UUID, depth: int = 2) -> Subgraph:
    return traverse(PostgresGraphRepository(db), organization_id, Node(node_type.upper(), node_id), depth=depth)


def to_dict(g: Subgraph) -> dict:
    return {
        "root": {"type": g.root.type, "id": str(g.root.id)},
        "depth": g.depth,
        "truncated": g.truncated,
        "nodes": [{"type": n.type, "id": str(n.id)} for n in g.nodes],
        "edges": [
            {"source": {"type": e.source.type, "id": str(e.source.id)},
             "target": {"type": e.target.type, "id": str(e.target.id)}, "rel": e.rel}
            for e in g.edges
        ],
    }
