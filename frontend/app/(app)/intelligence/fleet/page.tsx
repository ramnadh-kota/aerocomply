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
import { intelligenceApi, type FleetAssetIntelligence, type FleetIntelligenceSummary } from "@/lib/api/intelligence";
import { PLATFORM_NAME } from "@/lib/brand";

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
  const [summary, setSummary] = useState<FleetIntelligenceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [attentionFilter, setAttentionFilter] = useState<AttentionFilter>("ALL");
  const [assetTypeFilter, setAssetTypeFilter] = useState<string>("ALL");
  const [operationalStateFilter, setOperationalStateFilter] = useState<string>("ALL");
  const [decisionFilter, setDecisionFilter] = useState<string>("ALL");
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated || sessionType === "DEMO") {
      setLoading(false);
      return;
    }
    if (!accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    intelligenceApi
      .getFleet(accessToken)
      .then(setSummary)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [accessToken, isAuthenticated, sessionType]);

  const assets = summary?.assets ?? [];

  // Pure presentation tallies over already-computed backend values -- no
  // readiness/risk/priority/decision logic is derived here, only counted.
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

  if (!isAuthenticated) {
    return null;
  }

  if (sessionType === "DEMO") {
    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Fleet Intelligence" }]} />
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            The D2.2 Fleet Intelligence Control Center is not available in demo mode — it requires a real
            organization&apos;s deterministic backend intelligence. Sign in to a real organization to view it.
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
          <p className="ac-eyebrow" style={{ marginBottom: 4 }}>{PLATFORM_NAME}</p>
          <h1 className="ac-h1">Fleet Intelligence Control Center</h1>
          <p className="ac-subtitle">
            Deterministic readiness → risk → priority → decision → recommendation for every asset in your
            organization. Every value below is computed by the backend and only labeled/formatted here.
            {summary && (
              <> Evaluated at {new Date(summary.evaluated_at).toLocaleString()}.</>
            )}
          </p>
        </div>
      </div>

      <RealDataPanel
        loading={loading}
        error={error}
        isEmpty={!loading && !error && assets.length === 0}
        emptyMessage="No assets exist for this organization yet."
      >
        <>
          {/* FLEET STATE */}
          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Fleet State</h2>
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

          {/* ATTENTION REQUIRED */}
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
              <h2 className="ac-h2" style={{ margin: 0 }}>Fleet Asset Intelligence</h2>
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
                                        {b.related_record_type && b.related_record_id && (
                                          <span className="ac-text-muted"> — {b.related_record_type} #{b.related_record_id.slice(0, 8)}</span>
                                        )}
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
                  {filtered.length === 0 && (
                    <tr>
                      <td colSpan={9} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>
                        No assets match the current filters.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* BLOCKERS */}
          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Blockers</h2>
            <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
              <table className="ac-table">
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Condition</th>
                    <th>Category</th>
                    <th>Source</th>
                    <th>Required Action</th>
                    <th>Resolution Action</th>
                  </tr>
                </thead>
                <tbody>
                  {allBlockers.map(({ asset, blocker }, idx) => (
                    <tr key={idx}>
                      <td>
                        <Link href={`/assets/${asset.asset_id}?tab=INTELLIGENCE`} className="ac-mono">
                          {asset.registration ?? asset.asset_id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="ac-text-sm">{blocker.description}</td>
                      <td className="ac-text-sm">{blocker.category}</td>
                      <td className="ac-text-sm">{blocker.source_domain}</td>
                      <td className="ac-text-sm">{blocker.required_action ?? "—"}</td>
                      <td className="ac-text-sm">{blocker.resolution_action ?? "—"}</td>
                    </tr>
                  ))}
                  {allBlockers.length === 0 && (
                    <tr>
                      <td colSpan={6} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>
                        No active blockers across the fleet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* WARNINGS */}
          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Warnings</h2>
            <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
              <table className="ac-table">
                <thead>
                  <tr>
                    <th>Asset</th>
                    <th>Condition</th>
                    <th>Why</th>
                    <th>Source</th>
                  </tr>
                </thead>
                <tbody>
                  {allWarnings.map(({ asset, warning }, idx) => (
                    <tr key={idx}>
                      <td>
                        <Link href={`/assets/${asset.asset_id}?tab=INTELLIGENCE`} className="ac-mono">
                          {asset.registration ?? asset.asset_id.slice(0, 8)}
                        </Link>
                      </td>
                      <td className="ac-text-sm">{warning.category}</td>
                      <td className="ac-text-sm">{warning.message}</td>
                      <td className="ac-text-sm">{warning.dimension}</td>
                    </tr>
                  ))}
                  {allWarnings.length === 0 && (
                    <tr>
                      <td colSpan={4} className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>
                        No active warnings across the fleet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          {/* UNCERTAINTY */}
          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Uncertainty</h2>
            <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 8 }}>
              Assets where intelligence state, readiness, or risk could not be determined — never treated as
              nominal, ready, or low risk.
            </p>
            {uncertainAssets.length > 0 ? (
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                {uncertainAssets.map((a) => (
                  <Link key={a.asset_id} href={`/assets/${a.asset_id}?tab=INTELLIGENCE`} className="ac-card" style={{ padding: 10, display: "block" }}>
                    <strong className="ac-mono">{a.registration ?? a.asset_id.slice(0, 8)}</strong>
                    <div className="ac-flex ac-gap-2" style={{ marginTop: 4, flexWrap: "wrap" }}>
                      {UNKNOWN_TOKENS.has(a.aerospace_intelligence_status) && (
                        <StatusBadge {...intelligenceAerospaceStatusBadge(a.aerospace_intelligence_status)} />
                      )}
                      {a.readiness_state === "UNKNOWN" && <StatusBadge {...intelligenceReadinessBadge("UNKNOWN")} />}
                      {a.risk_level === "UNKNOWN" && <StatusBadge {...intelligenceRiskLevelBadge("UNKNOWN")} label="Risk Unknown" />}
                      {a.decision_state === "INSUFFICIENT_DATA" && <StatusBadge {...intelligenceDecisionBadge("INSUFFICIENT_DATA")} />}
                    </div>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="ac-text-sm ac-text-muted">No assets currently have unresolved/uncertain intelligence.</p>
            )}
          </section>

          {/* TRACEABILITY */}
          {selectedAsset && (
            <section className="ac-section">
              <h2 className="ac-h2" style={{ marginBottom: 10 }}>
                Traceability — {selectedAsset.registration ?? selectedAsset.asset_id}
              </h2>
              <div className="ac-card" style={{ padding: 16 }}>
                <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
                  <strong>Decision:</strong> {selectedAsset.decision_reason}
                </p>
                <p className="ac-text-sm" style={{ margin: "0 0 6px" }}>
                  <strong>Recommendation:</strong> {selectedAsset.top_recommendation_action ?? "No action required."}
                </p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 6px" }}>
                  ↓ {selectedAsset.blocker_count} blocker(s), {selectedAsset.warning_count} warning(s) — see
                  Blockers/Warnings sections above, or open the asset&apos;s own Intelligence tab for full
                  source-record traceability.
                </p>
                <Link href={`/assets/${selectedAsset.asset_id}?tab=INTELLIGENCE`} className="ac-btn" style={{ padding: "2px 8px" }}>
                  Open Asset Intelligence →
                </Link>
              </div>
            </section>
          )}
        </>
      </RealDataPanel>
    </div>
  );
}
