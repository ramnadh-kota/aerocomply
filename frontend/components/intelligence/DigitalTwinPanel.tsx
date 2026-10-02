"use client";

// H6: Digital Asset & Component Twin panel. Renders the unified current-
// state view (identity/health/diagnostics/prognostics/maintenance/
// compliance/readiness), the component tree, consistency warnings, and the
// unified lifecycle timeline -- all read-only aggregation over existing
// H1-H5 + MRO/compliance/readiness data. This panel never computes a new
// health/diagnosis/RUL/compliance/readiness value itself.

import { useEffect, useState } from "react";
import { StatusBadge, humsHealthIntelligenceStateBadge } from "@/components/status/StatusBadge";
import {
  digitalTwinApi,
  type DigitalTwinAssetSnapshot,
  type DigitalTwinComponentNode,
  type DigitalTwinConsistencyWarning,
  type DigitalTwinTimelineEvent,
} from "@/lib/api/digitalTwin";

interface DigitalTwinPanelProps {
  assetId: string;
  accessToken?: string | null;
}

function SnapshotOverview({ snapshot }: { snapshot: DigitalTwinAssetSnapshot }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10, marginBottom: 14 }}>
      <div>
        <div style={{ fontSize: 11, color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>Configuration</div>
        <div style={{ fontSize: 13 }}>{snapshot.identity.model || snapshot.identity.asset_type}</div>
      </div>
      <div>
        <div style={{ fontSize: 11, color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>Operational State</div>
        <div style={{ fontSize: 13 }}>{snapshot.identity.status}</div>
      </div>
      <div>
        <div style={{ fontSize: 11, color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>Health</div>
        {snapshot.health ? <StatusBadge {...humsHealthIntelligenceStateBadge(snapshot.health.state)} /> : <span style={{ fontSize: 12, color: "var(--ac-text-muted)" }}>N/A</span>}
      </div>
      <div>
        <div style={{ fontSize: 11, color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>Diagnostics</div>
        <div style={{ fontSize: 13 }}>{snapshot.diagnostics.length} candidate(s)</div>
      </div>
      <div>
        <div style={{ fontSize: 11, color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>RUL</div>
        <div style={{ fontSize: 13 }}>
          {(() => {
            const withRul = snapshot.prognostics.find((p) => p.rul_estimate !== null);
            return withRul ? `${withRul.rul_estimate} ${withRul.rul_unit?.toLowerCase()}` : "N/A";
          })()}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 11, color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>Readiness</div>
        <div style={{ fontSize: 13 }}>{snapshot.readiness.readiness_state ?? "UNKNOWN"}</div>
      </div>
      <div>
        <div style={{ fontSize: 11, color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>Usage</div>
        <div style={{ fontSize: 13 }}>{snapshot.usage.total_flight_hours} FH / {snapshot.usage.total_cycles} cyc</div>
      </div>
      <div>
        <div style={{ fontSize: 11, color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>Open Findings/WOs</div>
        <div style={{ fontSize: 13 }}>{snapshot.maintenance.open_finding_count} / {snapshot.maintenance.open_work_order_count}</div>
      </div>
    </div>
  );
}

function ComponentTree({ nodes }: { nodes: DigitalTwinComponentNode[] }) {
  if (nodes.length === 0) return <p style={{ fontSize: 12, color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No components on this asset.</p>;
  return (
    <div>
      {nodes.map((n) => (
        <div key={n.component.id} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--ac-border)", fontSize: 12.5 }}>
          <span>{n.component.name} <span style={{ color: "var(--ac-text-muted)" }}>({n.component.component_type})</span></span>
          <span style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {n.health_state && <StatusBadge {...humsHealthIntelligenceStateBadge(n.health_state)} />}
            {n.diagnostic_count > 0 && <span style={{ color: "var(--ac-status-non-compliant)" }}>{n.diagnostic_count} diag</span>}
          </span>
        </div>
      ))}
    </div>
  );
}

function Timeline({ events }: { events: DigitalTwinTimelineEvent[] }) {
  if (events.length === 0) return <p style={{ fontSize: 12, color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No timeline events yet.</p>;
  return (
    <div>
      {events.slice(0, 15).map((e, i) => (
        <div key={i} style={{ display: "flex", gap: 10, padding: "5px 0", borderBottom: "1px solid var(--ac-border)", fontSize: 12 }}>
          <span style={{ color: "var(--ac-text-muted)", minWidth: 130 }}>{new Date(e.occurred_at).toLocaleString()}</span>
          <span style={{ color: "var(--ac-text-secondary)", minWidth: 160 }}>{e.event_type.replace(/_/g, " ")}</span>
          <span>{e.summary}</span>
        </div>
      ))}
    </div>
  );
}

function ConsistencyWarnings({ warnings }: { warnings: DigitalTwinConsistencyWarning[] }) {
  if (warnings.length === 0) return null;
  return (
    <div style={{ marginBottom: 14, padding: 10, borderRadius: 6, background: "rgba(248,113,113,0.08)", border: "1px solid rgba(248,113,113,0.3)" }}>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ac-status-non-compliant)", marginBottom: 4 }}>⚠ Data consistency warnings</div>
      {warnings.map((w, i) => (
        <div key={i} style={{ fontSize: 12, color: "var(--ac-status-non-compliant)" }}>
          [{w.severity}] {w.message}
        </div>
      ))}
    </div>
  );
}

export function DigitalTwinPanel({ assetId, accessToken }: DigitalTwinPanelProps) {
  const [snapshot, setSnapshot] = useState<DigitalTwinAssetSnapshot | null>(null);
  const [components, setComponents] = useState<DigitalTwinComponentNode[]>([]);
  const [timeline, setTimeline] = useState<DigitalTwinTimelineEvent[]>([]);
  const [warnings, setWarnings] = useState<DigitalTwinConsistencyWarning[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken || !assetId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      digitalTwinApi.getAssetSnapshot(accessToken, assetId),
      digitalTwinApi.getAssetComponents(accessToken, assetId).catch(() => []),
      digitalTwinApi.getAssetTimeline(accessToken, assetId).catch(() => []),
      digitalTwinApi.getAssetConsistency(accessToken, assetId).catch(() => []),
    ])
      .then(([snap, comps, tl, warn]) => {
        setSnapshot(snap);
        setComponents(comps);
        setTimeline(tl);
        setWarnings(warn);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load digital twin"))
      .finally(() => setLoading(false));
  }, [accessToken, assetId]);

  if (loading) return <p style={{ fontSize: 13, color: "var(--ac-text-secondary)" }}>Loading digital twin…</p>;
  if (error) return <p style={{ fontSize: 13, color: "var(--ac-status-non-compliant)" }}>{error}</p>;
  if (!snapshot) return <p style={{ fontSize: 13, color: "var(--ac-text-secondary)", fontStyle: "italic" }}>Digital twin unavailable.</p>;

  return (
    <div>
      <ConsistencyWarnings warnings={warnings} />
      <SnapshotOverview snapshot={snapshot} />

      <div style={{ fontSize: 12, color: "var(--ac-text-secondary)", marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.5 }}>Components</div>
      <ComponentTree nodes={components} />

      <div style={{ fontSize: 12, color: "var(--ac-text-secondary)", margin: "14px 0 6px", textTransform: "uppercase", letterSpacing: 0.5 }}>Timeline</div>
      <Timeline events={timeline} />

      <p style={{ fontSize: 11, color: "var(--ac-text-muted)", marginTop: 10 }}>
        Digital twin: a read-only, evidence-linked view of authoritative Kota Aerospace data. PostgreSQL remains the system
        of record — nothing here is a second source of truth.
      </p>
    </div>
  );
}
