"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import {
  StatusBadge,
  operationalStateBadge,
  intelligenceAerospaceStatusBadge,
  intelligenceReadinessBadge,
  intelligenceRiskLevelBadge,
  intelligenceDecisionBadge,
} from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  intelligenceApi,
  type FleetAssetIntelligence,
  type FleetIntelligenceSummary,
  type FleetCorrelationContext,
  type FleetIntelligenceContext,
  type FleetSignalContext,
  type FleetMROContext,
  type MaintenanceCandidate,
} from "@/lib/api/intelligence";
import { PLATFORM_NAME } from "@/lib/brand";

type ActiveTab = "OVERVIEW" | "SIGNALS" | "CORRELATION" | "PREDICTIVE_MRO";
type AttentionFilter = "ALL" | "CRITICAL" | "HIGH" | "ACTION_REQUIRED" | "MONITOR" | "INSUFFICIENT_DATA";

const UNKNOWN_TOKENS = new Set(["UNKNOWN", "UNKNOWN_INTEL"]);

export function isUncertain(a: FleetAssetIntelligence): boolean {
  return (
    a.aerospace_intelligence_status === "UNKNOWN_INTEL" ||
    a.readiness_state === "UNKNOWN" ||
    a.risk_level === "UNKNOWN" ||
    a.decision_state === "INSUFFICIENT_DATA"
  );
}

export function distinctValues(assets: FleetAssetIntelligence[], key: keyof FleetAssetIntelligence): string[] {
  const set = new Set<string>();
  for (const a of assets) {
    const v = a[key];
    if (typeof v === "string") set.add(v);
  }
  return Array.from(set).sort();
}

export default function FleetIntelligencePage() {
  const { accessToken, isAuthenticated, sessionType } = useSession();
  const [activeTab, setActiveTab] = useState<ActiveTab>("OVERVIEW");

  // Core Data States
  const [summary, setSummary] = useState<FleetIntelligenceSummary | null>(null);
  const [overview, setOverview] = useState<FleetIntelligenceContext | null>(null);
  const [signals, setSignals] = useState<FleetSignalContext | null>(null);
  const [mroContext, setMroContext] = useState<FleetMROContext | null>(null);
  const [correlation, setCorrelation] = useState<FleetCorrelationContext | null>(null);
  const [candidates, setCandidates] = useState<MaintenanceCandidate[]>([]);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  // Filters & Selection
  const [attentionFilter, setAttentionFilter] = useState<AttentionFilter>("ALL");
  const [assetTypeFilter, setAssetTypeFilter] = useState<string>("ALL");
  const [operationalStateFilter, setOperationalStateFilter] = useState<string>("ALL");
  const [decisionFilter, setDecisionFilter] = useState<string>("ALL");
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

  // Maintenance action states
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || sessionType === "DEMO" || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    Promise.all([
      intelligenceApi.getFleet(accessToken).catch(() => null),
      intelligenceApi.getFleetOverview(accessToken).catch(() => null),
      intelligenceApi.getFleetSignals(accessToken).catch(() => null),
      intelligenceApi.getFleetMRO(accessToken).catch(() => null),
      intelligenceApi.getFleetCorrelation(accessToken).catch(() => null),
      intelligenceApi.listMROCandidates(accessToken).catch(() => []),
    ])
      .then(([fleetSummary, fleetOverview, fleetSignals, fleetMro, corr, mroCandidates]) => {
        setSummary(fleetSummary);
        setOverview(fleetOverview);
        setSignals(fleetSignals);
        setMroContext(fleetMro);
        setCorrelation(corr);
        setCandidates(mroCandidates ?? []);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [accessToken, isAuthenticated, sessionType]);

  const assets = summary?.assets ?? [];

  const distribution = useMemo(() => {
    const tally = (key: keyof FleetAssetIntelligence) => {
      const counts: Record<string, number> = {};
      for (const a of assets) {
        const v = a[key];
        if (typeof v === "string") counts[v] = (counts[v] ?? 0) + 1;
      }
      return counts;
    };
    return {
      operational: tally("operational_state"),
      aerospace: tally("aerospace_intelligence_status"),
      readiness: tally("readiness_state"),
      risk: tally("risk_level"),
      priority: tally("priority_level"),
      decision: tally("decision_state"),
    };
  }, [assets]);

  const attentionCounts = useMemo(() => {
    return {
      CRITICAL: assets.filter((a) => a.priority_level === "CRITICAL").length,
      HIGH: assets.filter((a) => a.priority_level === "HIGH").length,
      ACTION_REQUIRED: assets.filter(
        (a) => a.decision_state === "ACTION_REQUIRED" || a.decision_state === "IMMEDIATE_ACTION_REQUIRED"
      ).length,
      MONITOR: assets.filter((a) => a.decision_state === "MONITOR").length,
      INSUFFICIENT_DATA: assets.filter((a) => a.decision_state === "INSUFFICIENT_DATA").length,
    };
  }, [assets]);

  const uncertainAssets = useMemo(() => assets.filter(isUncertain), [assets]);
  const assetTypes = useMemo(() => distinctValues(assets, "asset_type"), [assets]);
  const operationalStates = useMemo(() => distinctValues(assets, "operational_state"), [assets]);
  const decisionStates = useMemo(() => distinctValues(assets, "decision_state"), [assets]);

  const filtered = useMemo(() => {
    return assets.filter((a) => {
      if (assetTypeFilter !== "ALL" && a.asset_type !== assetTypeFilter) return false;
      if (operationalStateFilter !== "ALL" && a.operational_state !== operationalStateFilter) return false;
      if (decisionFilter !== "ALL" && a.decision_state !== decisionFilter) return false;
      switch (attentionFilter) {
        case "CRITICAL":
          return a.priority_level === "CRITICAL";
        case "HIGH":
          return a.priority_level === "HIGH";
        case "ACTION_REQUIRED":
          return a.decision_state === "ACTION_REQUIRED" || a.decision_state === "IMMEDIATE_ACTION_REQUIRED";
        case "MONITOR":
          return a.decision_state === "MONITOR";
        case "INSUFFICIENT_DATA":
          return a.decision_state === "INSUFFICIENT_DATA";
        default:
          return true;
      }
    });
  }, [assets, attentionFilter, assetTypeFilter, operationalStateFilter, decisionFilter]);

  const allBlockers = useMemo(
    () => assets.flatMap((a) => a.blockers.map((b) => ({ asset: a, blocker: b }))),
    [assets]
  );
  const allWarnings = useMemo(
    () => assets.flatMap((a) => a.warnings.map((w) => ({ asset: a, warning: w }))),
    [assets]
  );

  const selectedAsset = assets.find((a) => a.asset_id === selectedAssetId) ?? null;

  // H8.7 Predictive Maintenance Handlers
  const handleCandidateAction = async (
    candidateId: string,
    action: "review" | "accept" | "reject" | "defer"
  ) => {
    if (!accessToken) return;
    setActionLoading(candidateId);
    setActionError(null);
    setActionSuccess(null);
    try {
      if (action === "review") await intelligenceApi.reviewCandidate(accessToken, candidateId, "Reviewed via console");
      if (action === "accept") await intelligenceApi.acceptCandidate(accessToken, candidateId, "Accepted via console");
      if (action === "reject") await intelligenceApi.rejectCandidate(accessToken, candidateId, "Rejected via console");
      if (action === "defer") await intelligenceApi.deferCandidate(accessToken, candidateId, "Deferred via console");

      const refreshed = await intelligenceApi.listMROCandidates(accessToken);
      setCandidates(refreshed);
      setActionSuccess(`Candidate status updated to ${action.toUpperCase()}`);
    } catch (err: any) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDraftWorkOrder = async (candidateId: string) => {
    if (!accessToken) return;
    setActionLoading(candidateId);
    setActionError(null);
    setActionSuccess(null);
    try {
      const resp = await intelligenceApi.draftWorkOrderFromCandidate(accessToken, candidateId, {
        notes: "Drafted via H8.8 Unified Fleet Intelligence Console",
      });
      const refreshed = await intelligenceApi.listMROCandidates(accessToken);
      setCandidates(refreshed);
      setActionSuccess(`Drafted Work Order ${resp.work_order_number} successfully!`);
    } catch (err: any) {
      setActionError(normalizeApiError(err).message);
    } finally {
      setActionLoading(null);
    }
  };

  if (!isAuthenticated) return null;

  if (sessionType === "DEMO") {
    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Fleet Intelligence" }]} />
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            The Fleet Intelligence Control Center is not available in unauthenticated demo preview.
            Sign in to an authorized organization to view real-time fleet intelligence.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Fleet Intelligence" }]} />

      <div className="ac-section-header">
        <div>
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME} DECISION & INTELLIGENCE SYSTEMS</p>
          <h1 className="ac-h1">Unified Fleet Intelligence Console</h1>
          <p className="ac-subtitle">
            Consolidated cross-domain intelligence: population metrics, canonical M7 signals, H8.3 vibration correlations,
            and human-authorized predictive maintenance.
            {summary && <> Evaluated at {new Date(summary.evaluated_at).toLocaleString()}.</>}
          </p>
        </div>
      </div>

      {/* ACTION ALERTS */}
      {actionSuccess && (
        <div className="ac-card" style={{ backgroundColor: "rgba(16, 185, 129, 0.1)", borderColor: "#10b981", padding: 12, marginBottom: 16 }}>
          <p className="ac-text-sm" style={{ color: "#065f46", margin: 0, fontWeight: 500 }}>
            ✓ {actionSuccess}
          </p>
        </div>
      )}
      {actionError && (
        <div className="ac-card" style={{ backgroundColor: "rgba(239, 68, 68, 0.1)", borderColor: "#ef4444", padding: 12, marginBottom: 16 }}>
          <p className="ac-text-sm" style={{ color: "#991b1b", margin: 0, fontWeight: 500 }}>
            ✕ {actionError}
          </p>
        </div>
      )}

      {/* TOP NAVIGATION TABS */}
      <div style={{ display: "flex", gap: 8, borderBottom: "1px solid var(--ac-border)", marginBottom: 20 }}>
        {(
          [
            ["OVERVIEW", "Overview & Population"],
            ["SIGNALS", `Fleet Signals (${signals?.total_active_signals ?? 0})`],
            ["CORRELATION", `Anomaly Patterns (${correlation?.anomaly_correlations?.length ?? 0})`],
            ["PREDICTIVE_MRO", `Predictive MRO (${candidates?.length ?? 0})`],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setActiveTab(key)}
            className="ac-btn"
            style={{
              padding: "10px 16px",
              borderBottom: activeTab === key ? "2px solid var(--ac-accent)" : "2px solid transparent",
              background: activeTab === key ? "var(--ac-bg-surface-hover)" : "transparent",
              fontWeight: activeTab === key ? 600 : 400,
              borderRadius: "4px 4px 0 0",
              cursor: "pointer",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <RealDataPanel
        loading={loading}
        error={error}
        isEmpty={!loading && !error && assets.length === 0}
        emptyMessage="No assets exist for this organization yet."
      >
        <>
          {/* TAB 1: OVERVIEW & POPULATION */}
          {activeTab === "OVERVIEW" && (
            <>
              {/* Population KPI Bar */}
              {overview && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginBottom: 20 }}>
                  <div className="ac-card" style={{ padding: 14 }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Total Assets</p>
                    <p className="ac-mono" style={{ fontSize: 24, fontWeight: 700, margin: "4px 0 0" }}>
                      {overview.overview.asset_count}
                    </p>
                    <span className="ac-text-sm ac-text-muted">{overview.overview.active_asset_count} active</span>
                  </div>
                  <div className="ac-card" style={{ padding: 14 }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Component Count</p>
                    <p className="ac-mono" style={{ fontSize: 24, fontWeight: 700, margin: "4px 0 0" }}>
                      {overview.overview.component_count}
                    </p>
                    <span className="ac-text-sm ac-text-muted">Monitored units</span>
                  </div>
                  <div className="ac-card" style={{ padding: 14 }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Telemetry Freshness</p>
                    <div style={{ display: "flex", gap: 8, marginTop: 6, flexWrap: "wrap" }}>
                      <span className="ac-badge" style={{ backgroundColor: "rgba(16, 185, 129, 0.15)", color: "#10b981" }}>
                        {overview.telemetry_context.fresh_count} Fresh
                      </span>
                      <span className="ac-badge" style={{ backgroundColor: "rgba(245, 158, 11, 0.15)", color: "#f59e0b" }}>
                        {overview.telemetry_context.stale_count} Stale
                      </span>
                      <span className="ac-badge" style={{ backgroundColor: "rgba(107, 114, 128, 0.15)", color: "#6b7280" }}>
                        {overview.telemetry_context.unknown_count + overview.telemetry_context.missing_count} Missing
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* FLEET STATE */}
              <section className="ac-section">
                <h2 className="ac-h2" style={{ marginBottom: 10 }}>Fleet Operational & Health State</h2>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12 }}>
                  {(
                    [
                      ["Operational State", distribution.operational, operationalStateBadge],
                      ["Intelligence State", distribution.aerospace, intelligenceAerospaceStatusBadge],
                      ["Readiness", distribution.readiness, intelligenceReadinessBadge],
                      ["Risk", distribution.risk, intelligenceRiskLevelBadge],
                      ["Priority", distribution.priority, intelligenceRiskLevelBadge],
                      ["Decision", distribution.decision, intelligenceDecisionBadge],
                    ] as const
                  ).map(([label, counts, badgeFn]) => (
                    <div key={label} className="ac-card" style={{ padding: 14 }}>
                      <p className="ac-eyebrow" style={{ marginBottom: 8 }}>{label}</p>
                      <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                        {Object.entries(counts).length === 0 && (
                          <span className="ac-text-sm ac-text-muted">No data</span>
                        )}
                        {Object.entries(counts).map(([value, count]) => (
                          <StatusBadge key={value} {...badgeFn(value)} label={`${badgeFn(value).label}: ${count}`} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* ATTENTION REQUIRED KPIS */}
              <section className="ac-section">
                <h2 className="ac-h2" style={{ marginBottom: 10 }}>Attention Required</h2>
                <div className="ac-kpi-grid">
                  {(
                    [
                      ["Critical", attentionCounts.CRITICAL, "CRITICAL"],
                      ["High", attentionCounts.HIGH, "HIGH"],
                      ["Action Required", attentionCounts.ACTION_REQUIRED, "ACTION_REQUIRED"],
                      ["Monitor", attentionCounts.MONITOR, "MONITOR"],
                      ["Insufficient Data", attentionCounts.INSUFFICIENT_DATA, "INSUFFICIENT_DATA"],
                    ] as const
                  ).map(([label, value, key]) => (
                    <div
                      key={key}
                      role="button"
                      tabIndex={0}
                      onClick={() => setAttentionFilter(attentionFilter === key ? "ALL" : key)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") setAttentionFilter(attentionFilter === key ? "ALL" : key);
                      }}
                      className="ac-kpi-card"
                      style={{
                        textAlign: "left",
                        cursor: "pointer",
                        border: attentionFilter === key ? "1px solid var(--ac-accent)" : undefined,
                      }}
                    >
                      <p className="ac-kpi-label">{label}</p>
                      <p className="ac-kpi-value">{value}</p>
                    </div>
                  ))}
                </div>
                {attentionFilter !== "ALL" && (
                  <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
                    Filtered by {attentionFilter.replace(/_/g, " ")}.{" "}
                    <button className="ac-btn" style={{ padding: "2px 8px" }} onClick={() => setAttentionFilter("ALL")}>
                      Clear filter
                    </button>
                  </p>
                )}
              </section>

              {/* FLEET ASSET INTELLIGENCE TABLE */}
              <section className="ac-section">
                <div className="ac-section-header">
                  <h2 className="ac-h2" style={{ margin: 0 }}>Fleet Asset Register</h2>
                  <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                    <select className="ac-select" value={assetTypeFilter} onChange={(e) => setAssetTypeFilter(e.target.value)}>
                      <option value="ALL">All Types</option>
                      {assetTypes.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                    <select
                      className="ac-select"
                      value={operationalStateFilter}
                      onChange={(e) => setOperationalStateFilter(e.target.value)}
                    >
                      <option value="ALL">All Operational States</option>
                      {operationalStates.map((s) => (
                        <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                      ))}
                    </select>
                    <select className="ac-select" value={decisionFilter} onChange={(e) => setDecisionFilter(e.target.value)}>
                      <option value="ALL">All Decision States</option>
                      {decisionStates.map((s) => (
                        <option key={s} value={s}>{s.replace(/_/g, " ")}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
                  <table className="ac-table">
                    <thead>
                      <tr>
                        <th>Asset</th>
                        <th>Type</th>
                        <th>Operational State</th>
                        <th>Intelligence State</th>
                        <th>Readiness</th>
                        <th>Risk</th>
                        <th>Priority</th>
                        <th>Decision</th>
                        <th>Recommendation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.map((a) => (
                        <Fragment key={a.asset_id}>
                          <tr
                            onClick={() => setSelectedAssetId(selectedAssetId === a.asset_id ? null : a.asset_id)}
                            style={{ cursor: "pointer" }}
                          >
                            <td>
                              <Link href={`/assets/${a.asset_id}?tab=INTELLIGENCE`} className="ac-mono" onClick={(e) => e.stopPropagation()}>
                                {a.registration ?? a.asset_id.slice(0, 8)}
                              </Link>
                            </td>
                            <td>{a.asset_type}</td>
                            <td><StatusBadge {...operationalStateBadge(a.operational_state)} /></td>
                            <td><StatusBadge {...intelligenceAerospaceStatusBadge(a.aerospace_intelligence_status)} /></td>
                            <td><StatusBadge {...intelligenceReadinessBadge(a.readiness_state)} /></td>
                            <td><StatusBadge {...intelligenceRiskLevelBadge(a.risk_level)} /></td>
                            <td><StatusBadge {...intelligenceRiskLevelBadge(a.priority_level)} /></td>
                            <td><StatusBadge {...intelligenceDecisionBadge(a.decision_state)} /></td>
                            <td className="ac-text-sm">{a.top_recommendation_action ?? "—"}</td>
                          </tr>
                          {selectedAssetId === a.asset_id && (
                            <tr>
                              <td colSpan={9}>
                                <div className="ac-card" style={{ background: "var(--ac-bg-surface-hover)", margin: "4px 0" }}>
                                  <p className="ac-eyebrow" style={{ marginBottom: 6 }}>
                                    Traceability: {a.registration ?? a.asset_id}
                                  </p>
                                  <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>
                                    <strong>Decision:</strong> {a.decision_reason}
                                  </p>
                                  {a.top_recommendation_action && (
                                    <p className="ac-text-sm" style={{ margin: "0 0 8px" }}>
                                      <strong>Recommendation:</strong> {a.top_recommendation_action}
                                    </p>
                                  )}
                                  {a.blockers.length > 0 && (
                                    <>
                                      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>
                                        Blockers ({a.blockers.length}):
                                      </p>
                                      <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13 }}>
                                        {a.blockers.map((b, idx) => (
                                          <li key={idx}>
                                            [{b.source_domain}] {b.description}
                                          </li>
                                        ))}
                                      </ul>
                                    </>
                                  )}
                                  <Link href={`/assets/${a.asset_id}?tab=INTELLIGENCE`} className="ac-btn" style={{ padding: "2px 8px" }}>
                                    Open Asset Intelligence →
                                  </Link>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}

          {/* TAB 2: SIGNALS & ATTENTION (M7 CANONICAL) */}
          {activeTab === "SIGNALS" && (
            <section className="ac-section">
              <div className="ac-section-header">
                <div>
                  <h2 className="ac-h2" style={{ margin: 0 }}>Canonical M7 Fleet Signals</h2>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                    Proactive intelligence signals from canonical M7 service ownership. Deduplicated and ranked by operational severity.
                  </p>
                </div>
              </div>

              {signals && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 16 }}>
                  <div className="ac-card" style={{ padding: 12, borderLeft: "4px solid #ef4444" }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Critical</p>
                    <p className="ac-mono" style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
                      {signals.severity_distribution?.CRITICAL ?? 0}
                    </p>
                  </div>
                  <div className="ac-card" style={{ padding: 12, borderLeft: "4px solid #f97316" }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Warning</p>
                    <p className="ac-mono" style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
                      {signals.severity_distribution?.WARNING ?? 0}
                    </p>
                  </div>
                  <div className="ac-card" style={{ padding: 12, borderLeft: "4px solid #3b82f6" }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Info</p>
                    <p className="ac-mono" style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
                      {signals.severity_distribution?.INFO ?? 0}
                    </p>
                  </div>
                  <div className="ac-card" style={{ padding: 12 }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Affected Assets</p>
                    <p className="ac-mono" style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>
                      {signals.affected_asset_count}
                    </p>
                  </div>
                </div>
              )}

              {signals && signals.recent_signals.length > 0 ? (
                <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
                  <table className="ac-table">
                    <thead>
                      <tr>
                        <th>Asset</th>
                        <th>Category</th>
                        <th>Severity</th>
                        <th>Headline</th>
                        <th>Status</th>
                        <th>Timestamp</th>
                      </tr>
                    </thead>
                    <tbody>
                      {signals.recent_signals.map((sig) => (
                        <tr key={sig.id}>
                          <td>
                            {sig.asset_id ? (
                              <Link href={`/assets/${sig.asset_id}?tab=INTELLIGENCE`} className="ac-mono">
                                {sig.asset_id.slice(0, 8)}
                              </Link>
                            ) : (
                              <span className="ac-text-muted">Fleet-wide</span>
                            )}
                          </td>
                          <td className="ac-text-sm">{sig.signal_type}</td>
                          <td>
                            <span
                              className="ac-badge"
                              style={{
                                backgroundColor:
                                  sig.severity === "CRITICAL"
                                    ? "rgba(239, 68, 68, 0.15)"
                                    : sig.severity === "WARNING"
                                    ? "rgba(245, 158, 11, 0.15)"
                                    : "rgba(59, 130, 246, 0.15)",
                                color:
                                  sig.severity === "CRITICAL"
                                    ? "#ef4444"
                                    : sig.severity === "WARNING"
                                    ? "#f59e0b"
                                    : "#3b82f6",
                              }}
                            >
                              {sig.severity}
                            </span>
                          </td>
                          <td className="ac-text-sm">{sig.title}</td>
                          <td><span className="ac-badge">{sig.status}</span></td>
                          <td className="ac-text-sm ac-text-muted">{new Date(sig.detected_at).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="ac-card" style={{ padding: 20, textAlign: "center" }}>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                    No active M7 proactive signals across the fleet.
                  </p>
                </div>
              )}
            </section>
          )}

          {/* TAB 3: CROSS-ASSET ANOMALY CORRELATION (H8.3) */}
          {activeTab === "CORRELATION" && (
            <section className="ac-section">
              <div className="ac-section-header">
                <div>
                  <h2 className="ac-h2" style={{ margin: 0 }}>Cross-Asset Vibration & HUMS Anomaly Patterns</h2>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                    Multi-asset anomaly clustering powered by H8.3 engine. Discovers shared mechanical degradation patterns without false causation.
                  </p>
                </div>
              </div>

              {correlation && correlation.anomaly_correlations.length > 0 ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  {correlation.anomaly_correlations.map((corr) => (
                    <div key={corr.id} className="ac-card" style={{ padding: 16 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                            <span className="ac-mono" style={{ fontWeight: 600, fontSize: 14 }}>
                              {corr.feature_family.toUpperCase()}
                            </span>
                            <span className="ac-badge">{corr.pattern_type.replace(/_/g, " ")}</span>
                            <span className="ac-badge">{corr.confidence} CONFIDENCE</span>
                            {corr.is_simulation && (
                              <span className="ac-badge" style={{ backgroundColor: "rgba(99, 102, 241, 0.15)", color: "#6366f1" }}>
                                SIMULATED
                              </span>
                            )}
                          </div>
                          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                            Participating assets: {corr.participating_asset_count} | Observations: {corr.observation_count}
                          </p>
                        </div>
                        <div style={{ textAlign: "right" }}>
                          <p className="ac-eyebrow" style={{ margin: 0 }}>Similarity Score</p>
                          <p className="ac-mono" style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>
                            {(corr.similarity_score * 100).toFixed(1)}%
                          </p>
                        </div>
                      </div>

                      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "10px 0 8px" }}>
                        <span className="ac-text-sm" style={{ fontWeight: 500 }}>Assets:</span>
                        {corr.participating_asset_ids.map((aid) => (
                          <Link key={aid} href={`/assets/${aid}?tab=INTELLIGENCE`} className="ac-mono ac-badge" style={{ textDecoration: "none" }}>
                            {aid.slice(0, 8)}
                          </Link>
                        ))}
                      </div>

                      <p className="ac-text-sm ac-text-muted" style={{ fontStyle: "italic", margin: "6px 0 0", fontSize: 12 }}>
                        {corr.disclaimer}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="ac-card" style={{ padding: 20, textAlign: "center" }}>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                    No cross-asset anomaly clusters currently active.
                  </p>
                </div>
              )}
            </section>
          )}

          {/* TAB 4: PREDICTIVE MAINTENANCE & HUMAN-AUTHORIZED MRO (H8.4 / H8.7) */}
          {activeTab === "PREDICTIVE_MRO" && (
            <section className="ac-section">
              <div className="ac-section-header">
                <div>
                  <h2 className="ac-h2" style={{ margin: 0 }}>Predictive Maintenance & Human-Authorized Drafting</h2>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                    Lifecycle-managed recommendations derived from HUMS anomalies and MRO intelligence. Requires explicit human authorization before drafting work orders.
                  </p>
                </div>
              </div>

              {/* MRO Aggregates */}
              {mroContext && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12, marginBottom: 20 }}>
                  <div className="ac-card" style={{ padding: 14 }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Total Candidates</p>
                    <p className="ac-mono" style={{ fontSize: 22, fontWeight: 700, margin: "4px 0 0" }}>
                      {mroContext.candidates.candidate_count}
                    </p>
                    <span className="ac-text-sm ac-text-muted">
                      {mroContext.candidates.affected_asset_count} asset(s) affected
                    </span>
                  </div>
                  <div className="ac-card" style={{ padding: 14 }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Readiness At Risk</p>
                    <p className="ac-mono" style={{ fontSize: 22, fontWeight: 700, margin: "4px 0 0" }}>
                      {mroContext.readiness_impact.by_readiness_impact?.READINESS_AT_RISK ?? 0}
                    </p>
                    <span className="ac-text-sm ac-text-muted">
                      {mroContext.readiness_impact.by_readiness_impact?.RESTRICTED_OPERATION ?? 0} restricted
                    </span>
                  </div>
                  <div className="ac-card" style={{ padding: 14 }}>
                    <p className="ac-eyebrow" style={{ margin: 0 }}>Maintenance Conflicts</p>
                    <p className="ac-mono" style={{ fontSize: 22, fontWeight: 700, margin: "4px 0 0" }}>
                      {mroContext.conflicts.conflict_count}
                    </p>
                    <span className="ac-text-sm ac-text-muted">Dispatch/maintenance limits</span>
                  </div>
                </div>
              )}

              {/* Candidates Register */}
              <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
                <table className="ac-table">
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Category</th>
                      <th>Priority</th>
                      <th>Confidence</th>
                      <th>Reason & Evidence</th>
                      <th>Status</th>
                      <th>Human Authorization Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidates.map((c) => (
                      <tr key={c.id}>
                        <td>
                          <Link href={`/assets/${c.asset_id}?tab=INTELLIGENCE`} className="ac-mono">
                            {c.asset_id.slice(0, 8)}
                          </Link>
                        </td>
                        <td className="ac-text-sm">{c.candidate_type}</td>
                        <td>
                          <span
                            className="ac-badge"
                            style={{
                              backgroundColor:
                                c.priority === "HIGH" ? "rgba(239, 68, 68, 0.15)" : "rgba(245, 158, 11, 0.15)",
                              color: c.priority === "HIGH" ? "#ef4444" : "#f59e0b",
                            }}
                          >
                            {c.priority}
                          </span>
                        </td>
                        <td className="ac-mono ac-text-sm">{(c.confidence * 100).toFixed(0)}%</td>
                        <td className="ac-text-sm" style={{ maxWidth: 300 }}>
                          <div>{c.reason}</div>
                          {c.review_notes && (
                            <div className="ac-text-muted" style={{ fontSize: 12, marginTop: 4 }}>
                              Note: {c.review_notes}
                            </div>
                          )}
                        </td>
                        <td>
                          <span className="ac-badge">{c.status}</span>
                        </td>
                        <td>
                          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                            {c.status === "OPEN" && (
                              <button
                                className="ac-btn"
                                style={{ padding: "4px 8px", fontSize: 12 }}
                                disabled={actionLoading === c.id}
                                onClick={() => handleCandidateAction(c.id, "review")}
                              >
                                Review
                              </button>
                            )}
                            {(c.status === "OPEN" || c.status === "UNDER_REVIEW") && (
                              <button
                                className="ac-btn"
                                style={{ padding: "4px 8px", fontSize: 12 }}
                                disabled={actionLoading === c.id}
                                onClick={() => handleCandidateAction(c.id, "accept")}
                              >
                                Accept
                              </button>
                            )}
                            {c.status !== "RESOLVED" && c.status !== "REJECTED" && (
                              <button
                                className="ac-btn"
                                style={{ padding: "4px 8px", fontSize: 12, color: "#ef4444" }}
                                disabled={actionLoading === c.id}
                                onClick={() => handleCandidateAction(c.id, "reject")}
                              >
                                Reject
                              </button>
                            )}
                            {c.status !== "RESOLVED" && c.status !== "REJECTED" && (
                              <button
                                className="ac-btn"
                                style={{
                                  padding: "4px 10px",
                                  fontSize: 12,
                                  backgroundColor: "var(--ac-accent)",
                                  color: "#fff",
                                  fontWeight: 600,
                                }}
                                disabled={actionLoading === c.id}
                                onClick={() => handleDraftWorkOrder(c.id)}
                              >
                                {actionLoading === c.id ? "Drafting..." : "Draft Work Order"}
                              </button>
                            )}
                            {c.status === "RESOLVED" && (
                              <span className="ac-text-muted" style={{ fontSize: 12 }}>
                                Converted to Work Order
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                    {candidates.length === 0 && (
                      <tr>
                        <td colSpan={7} className="ac-text-sm ac-text-muted" style={{ padding: 16, textAlign: "center" }}>
                          No maintenance intelligence candidates pending review.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              {/* LISA Grounded Query Assist Card */}
              <div className="ac-card" style={{ marginTop: 24, padding: 16, backgroundColor: "var(--ac-bg-surface-hover)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h3 className="ac-h3" style={{ margin: 0 }}>LISA AI Fleet Intelligence Copilot</h3>
                    <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                      Ask grounded natural-language questions about fleet vibration patterns, M7 signals, and maintenance evidence.
                    </p>
                  </div>
                  <Link href="/ai" className="ac-btn" style={{ padding: "6px 14px" }}>
                    Open LISA Chat →
                  </Link>
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                  {[
                    "Which assets in our fleet have critical vibration signals?",
                    "What evidence supports the high-frequency motor bearing finding?",
                    "Are multiple drones showing correlated sensor exceedances?",
                    "Summarize fleet telemetry freshness across all active assets.",
                  ].map((prompt, idx) => (
                    <Link
                      key={idx}
                      href={`/ai?prompt=${encodeURIComponent(prompt)}`}
                      className="ac-badge"
                      style={{ textDecoration: "none", cursor: "pointer", padding: "6px 10px" }}
                    >
                      &quot;{prompt}&quot;
                    </Link>
                  ))}
                </div>
              </div>
            </section>
          )}
        </>
      </RealDataPanel>
    </div>
  );
}
