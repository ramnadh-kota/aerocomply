"use client";

// H7: MRO + Compliance + Readiness Intelligence Integration panel.
// Renders the H7 correlation layer (backend/app/api/v1/mro_intelligence.py)
// -- a read-mostly view over EXISTING authoritative outputs (HUMS H1-H5,
// aerospace_state_service, readiness_intelligence_service, maintenance,
// compliance). This panel never computes a new health/diagnosis/RUL/
// compliance/readiness value itself, and it NEVER merges the authoritative
// readiness_state with H7's own advisory readiness_impact classification --
// they are always rendered as two visually distinct fields (see
// backend/app/schemas/mro_intelligence.py ReadinessImpactResult docstring).
//
// Maintenance candidates are advisory ("Candidate Detected", "Review
// Recommended") -- never confirmed maintenance actions, work orders, or
// grounding directives. Candidate lifecycle buttons only ever call the H7
// review/accept/reject/defer endpoints, which mutate this module's own
// MaintenanceIntelligenceCandidate row -- never an authoritative domain
// table. A 409 (invalid transition per backend ALLOWED_CANDIDATE_TRANSITIONS)
// is always surfaced as a visible error, never swallowed.

import { useEffect, useState } from "react";
import { StatusBadge, type BadgeKind } from "@/components/status/StatusBadge";
import { normalizeApiError } from "@/lib/apiClient";
import {
  mroIntelligenceApi,
  type AssetMROIntelligence,
  type ComplianceImpactResult,
  type MaintenanceCandidateOut,
} from "@/lib/api/mroIntelligence";

interface MROIntelligencePanelProps {
  assetId: string;
  accessToken?: string | null;
  canWrite?: boolean;
}

// --- Candidate lifecycle: mirrors backend/app/models/mro_intelligence.py
// ALLOWED_CANDIDATE_TRANSITIONS exactly. A button is only enabled when its
// target status is reachable from the candidate's current status.
const ALLOWED_CANDIDATE_TRANSITIONS: Record<string, string[]> = {
  OPEN: ["UNDER_REVIEW", "ACCEPTED", "REJECTED", "DEFERRED", "RESOLVED"],
  UNDER_REVIEW: ["ACCEPTED", "REJECTED", "DEFERRED", "RESOLVED"],
  DEFERRED: ["UNDER_REVIEW", "ACCEPTED", "REJECTED", "RESOLVED"],
  ACCEPTED: ["RESOLVED"],
  REJECTED: [],
  RESOLVED: [],
};

function canTransition(currentStatus: string, target: string): boolean {
  return (ALLOWED_CANDIDATE_TRANSITIONS[currentStatus] ?? []).includes(target);
}

// --- Badge helpers local to H7 (kept here rather than in StatusBadge.tsx
// since these vocabularies -- ReadinessImpactLevel, ComplianceImpactState,
// OperationalImpactLevel, data_freshness -- are new to H7).

const READINESS_IMPACT_MAP: Record<string, BadgeKind> = {
  NO_IMPACT: "COMPLIANT",
  MONITOR: "PENDING",
  MAINTENANCE_DUE: "REVIEW_REQUIRED",
  INSPECTION_REQUIRED: "REVIEW_REQUIRED",
  REVIEW_REQUIRED: "REVIEW_REQUIRED",
  RESTRICTED_OPERATION: "NON_COMPLIANT",
  READINESS_AT_RISK: "NON_COMPLIANT",
  UNKNOWN: "UNKNOWN",
};

function readinessImpactBadge(level: string): { status: BadgeKind; label: string } {
  return { status: READINESS_IMPACT_MAP[level] ?? "UNKNOWN", label: level.replace(/_/g, " ") };
}

const AUTHORITATIVE_READINESS_MAP: Record<string, BadgeKind> = {
  READY: "COMPLIANT",
  BLOCKED: "NON_COMPLIANT",
  UNKNOWN: "UNKNOWN",
};

function authoritativeReadinessBadge(state: string): { status: BadgeKind; label: string } {
  return { status: AUTHORITATIVE_READINESS_MAP[state] ?? "UNKNOWN", label: state };
}

const OPERATIONAL_IMPACT_MAP: Record<string, BadgeKind> = {
  LOW: "COMPLIANT",
  MEDIUM: "REVIEW_REQUIRED",
  HIGH: "NON_COMPLIANT",
  UNKNOWN: "UNKNOWN",
};

function operationalImpactBadge(level: string): { status: BadgeKind; label: string } {
  return { status: OPERATIONAL_IMPACT_MAP[level] ?? "UNKNOWN", label: level };
}

const COMPLIANCE_IMPACT_MAP: Record<string, BadgeKind> = {
  COMPLIANT: "COMPLIANT",
  NON_COMPLIANT: "NON_COMPLIANT",
  DUE: "PENDING",
  OVERDUE: "NON_COMPLIANT",
  UNKNOWN: "UNKNOWN",
  NOT_APPLICABLE: "NOT_APPLICABLE",
  REQUIRES_REVIEW: "REVIEW_REQUIRED",
};

function complianceImpactBadge(state: string): { status: BadgeKind; label: string } {
  return { status: COMPLIANCE_IMPACT_MAP[state] ?? "UNKNOWN", label: state.replace(/_/g, " ") };
}

const PRIORITY_MAP: Record<string, BadgeKind> = {
  LOW: "COMPLIANT",
  MEDIUM: "PENDING",
  HIGH: "REVIEW_REQUIRED",
  CRITICAL: "NON_COMPLIANT",
};

function candidatePriorityBadge(priority: string): { status: BadgeKind; label: string } {
  return { status: PRIORITY_MAP[priority] ?? "UNKNOWN", label: priority };
}

const CANDIDATE_STATUS_MAP: Record<string, BadgeKind> = {
  OPEN: "PENDING",
  UNDER_REVIEW: "REVIEW_REQUIRED",
  ACCEPTED: "REVIEW_REQUIRED",
  DEFERRED: "UNKNOWN",
  REJECTED: "WRITTEN_OFF",
  RESOLVED: "COMPLIANT",
};

function candidateStatusBadge(status: string): { status: BadgeKind; label: string } {
  return { status: CANDIDATE_STATUS_MAP[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

// data_freshness is a free-form string | null on MaintenanceCandidateOut.
// Known values render a distinguishable badge; any other literal backend
// string is still shown as-is (never fabricated, never silently dropped).
const FRESHNESS_MAP: Record<string, BadgeKind> = {
  AVAILABLE: "COMPLIANT",
  FRESH: "COMPLIANT",
  LIMITED: "REVIEW_REQUIRED",
  STALE: "NON_COMPLIANT",
  MISSING: "INSUFFICIENT_DATA",
  UNKNOWN: "UNKNOWN",
};

function freshnessBadge(freshness: string | null): { status: BadgeKind; label: string } {
  if (!freshness) return { status: "INSUFFICIENT_DATA", label: "MISSING" };
  return { status: FRESHNESS_MAP[freshness] ?? "UNKNOWN", label: freshness.replace(/_/g, " ") };
}

function SourceLineageTrail({ refs }: { refs: { source_type: string; source_id: string | null; label: string }[] }) {
  if (!refs || refs.length === 0) {
    return <span style={{ fontSize: 11.5, color: "#6b7280", fontStyle: "italic" }}>No source lineage recorded.</span>;
  }
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
      {refs.map((r, i) => (
        <span
          key={i}
          title={r.source_id ?? undefined}
          style={{
            fontSize: 11,
            padding: "3px 8px",
            borderRadius: 5,
            background: "rgba(255,255,255,0.04)",
            border: "1px solid #27272a",
            color: "#9ca3af",
          }}
        >
          [{r.source_type}] {r.label}
        </span>
      ))}
    </div>
  );
}

function CandidateCard({
  candidate,
  accessToken,
  canWrite,
  onChanged,
}: {
  candidate: MaintenanceCandidateOut;
  accessToken?: string | null;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function runAction(action: "review" | "accept" | "reject" | "defer") {
    if (!accessToken) return;
    setBusy(action);
    setActionError(null);
    try {
      if (action === "review") await mroIntelligenceApi.reviewCandidate(accessToken, candidate.id);
      if (action === "accept") await mroIntelligenceApi.acceptCandidate(accessToken, candidate.id);
      if (action === "reject") await mroIntelligenceApi.rejectCandidate(accessToken, candidate.id);
      if (action === "defer") await mroIntelligenceApi.deferCandidate(accessToken, candidate.id);
      onChanged();
    } catch (err) {
      // A 409 (disallowed transition per ALLOWED_CANDIDATE_TRANSITIONS) or
      // any other failure must be visible -- never silently ignored.
      const normalized = normalizeApiError(err);
      setActionError(normalized.message);
    } finally {
      setBusy(null);
    }
  }

  const lineageRefs = (candidate.source_lineage ?? []) as { source_type: string; source_id: string | null; label: string }[];

  return (
    <div
      style={{
        padding: 12,
        borderLeft: `4px solid ${candidate.status === "OPEN" || candidate.status === "UNDER_REVIEW" ? "#fbbf24" : "#374151"}`,
        background: "rgba(255,255,255,0.02)",
        borderRadius: 6,
        marginBottom: 10,
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <div>
          <strong style={{ fontSize: 14 }}>{candidate.candidate_type.replace(/_/g, " ")}</strong>
          <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 2 }}>
            confidence {(candidate.confidence * 100).toFixed(0)}% · component {candidate.component_id ?? "asset-level"}
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <StatusBadge {...candidatePriorityBadge(candidate.priority)} />
          <StatusBadge {...candidateStatusBadge(candidate.status)} />
          <StatusBadge {...freshnessBadge(candidate.data_freshness)} />
        </div>
      </div>

      {(candidate.status === "OPEN" || candidate.status === "UNDER_REVIEW") && (
        <div style={{ fontSize: 11, color: "#fbbf24", marginTop: 6, fontStyle: "italic" }}>
          {candidate.status === "OPEN" ? "Candidate Detected — Review Recommended." : "Under human review."}
        </div>
      )}

      <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "#d1d5db" }}>{candidate.reason}</p>

      {candidate.operational_impact && (
        <div style={{ fontSize: 11.5, color: "#9ca3af", marginTop: 6 }}>
          Estimated operational impact: {candidate.operational_impact}
        </div>
      )}

      <div style={{ marginTop: 6 }}>
        <span style={{ fontSize: 11, color: "#6b7280", textTransform: "uppercase", letterSpacing: 0.5 }}>Source lineage</span>
        <SourceLineageTrail refs={lineageRefs} />
      </div>

      {candidate.review_notes && (
        <div style={{ fontSize: 11.5, color: "#9ca3af", marginTop: 6 }}>Review notes: {candidate.review_notes}</div>
      )}

      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 6 }}>
        dedup {candidate.dedup_key} · created {new Date(candidate.created_at).toLocaleString()} · updated{" "}
        {new Date(candidate.updated_at).toLocaleString()}
      </div>

      {actionError && (
        <div style={{ fontSize: 12, color: "#f87171", marginTop: 8, fontWeight: 600 }}>{actionError}</div>
      )}

      {canWrite && (
        <div style={{ marginTop: 10, display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button
            disabled={!canTransition(candidate.status, "UNDER_REVIEW") || busy !== null}
            onClick={() => runAction("review")}
            style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid #27272a", background: "none", color: "#93c5fd", cursor: canTransition(candidate.status, "UNDER_REVIEW") ? "pointer" : "not-allowed", opacity: canTransition(candidate.status, "UNDER_REVIEW") ? 1 : 0.4 }}
          >
            {busy === "review" ? "Marking…" : "Mark Under Review"}
          </button>
          <button
            disabled={!canTransition(candidate.status, "ACCEPTED") || busy !== null}
            onClick={() => runAction("accept")}
            style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid #27272a", background: "none", color: "#4ade80", cursor: canTransition(candidate.status, "ACCEPTED") ? "pointer" : "not-allowed", opacity: canTransition(candidate.status, "ACCEPTED") ? 1 : 0.4 }}
          >
            {busy === "accept" ? "Accepting…" : "Accept Candidate (Review Only)"}
          </button>
          <button
            disabled={!canTransition(candidate.status, "DEFERRED") || busy !== null}
            onClick={() => runAction("defer")}
            style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid #27272a", background: "none", color: "#fbbf24", cursor: canTransition(candidate.status, "DEFERRED") ? "pointer" : "not-allowed", opacity: canTransition(candidate.status, "DEFERRED") ? 1 : 0.4 }}
          >
            {busy === "defer" ? "Deferring…" : "Defer Candidate"}
          </button>
          <button
            disabled={!canTransition(candidate.status, "REJECTED") || busy !== null}
            onClick={() => runAction("reject")}
            style={{ fontSize: 12, padding: "4px 10px", borderRadius: 6, border: "1px solid #27272a", background: "none", color: "#f87171", cursor: canTransition(candidate.status, "REJECTED") ? "pointer" : "not-allowed", opacity: canTransition(candidate.status, "REJECTED") ? 1 : 0.4 }}
          >
            {busy === "reject" ? "Rejecting…" : "Reject Candidate (Review Only)"}
          </button>
        </div>
      )}
    </div>
  );
}

function ComplianceImpactSection({ compliance }: { compliance: ComplianceImpactResult | null }) {
  if (!compliance) {
    return <p style={{ fontSize: 13, color: "#f87171", fontStyle: "italic" }}>EVIDENCE MISSING — compliance impact could not be loaded.</p>;
  }
  if (compliance.availability === "DATA_UNAVAILABLE") {
    return (
      <div>
        <StatusBadge status="INSUFFICIENT_DATA" label="EVIDENCE MISSING" />
        <p style={{ fontSize: 12.5, color: "#9ca3af", marginTop: 8 }}>
          {compliance.explanation.length > 0 ? compliance.explanation.join(" ") : "Underlying compliance data is unavailable for this asset."}
        </p>
      </div>
    );
  }
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
        <span style={{ fontSize: 12, color: "#9ca3af", textTransform: "uppercase" }}>Overall Impact</span>
        <StatusBadge {...complianceImpactBadge(compliance.overall_impact)} />
      </div>
      {compliance.explanation.length > 0 && (
        <p style={{ fontSize: 12.5, color: "#d1d5db", marginBottom: 10 }}>{compliance.explanation.join(" ")}</p>
      )}
      {compliance.obligations.length === 0 ? (
        <p style={{ fontSize: 12.5, color: "#9ca3af", fontStyle: "italic" }}>No correlated compliance obligations for this asset.</p>
      ) : (
        compliance.obligations.map((o) => (
          <div key={o.obligation_id} style={{ padding: 10, background: "rgba(255,255,255,0.02)", borderRadius: 6, marginBottom: 8, border: "1px solid #27272a" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
              <span style={{ fontSize: 12.5 }}>Requirement {o.requirement_id}</span>
              <div style={{ display: "flex", gap: 6 }}>
                <StatusBadge label={o.state.replace(/_/g, " ")} status="UNKNOWN" />
                <StatusBadge {...complianceImpactBadge(o.impact)} />
              </div>
            </div>
            <div style={{ fontSize: 11.5, color: "#9ca3af", marginTop: 4 }}>
              Due: {o.due_date ?? "—"}
            </div>
            {o.explanation.length > 0 && (
              <ul style={{ margin: "6px 0 0", paddingLeft: 16, fontSize: 12, color: "#d1d5db" }}>
                {o.explanation.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            )}
            <div style={{ marginTop: 6 }}>
              <span style={{ fontSize: 10.5, color: "#6b7280", textTransform: "uppercase" }}>Evidence / correlated signals</span>
              <SourceLineageTrail refs={o.correlated_signals} />
            </div>
          </div>
        ))
      )}
    </div>
  );
}

export function MROIntelligencePanel({ assetId, accessToken, canWrite = false }: MROIntelligencePanelProps) {
  const [intel, setIntel] = useState<AssetMROIntelligence | null>(null);
  const [candidates, setCandidates] = useState<MaintenanceCandidateOut[] | null>(null);
  const [compliance, setCompliance] = useState<ComplianceImpactResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function load() {
    if (!accessToken || !assetId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      mroIntelligenceApi.getAssetMROIntelligence(accessToken, assetId),
      mroIntelligenceApi.listMaintenanceCandidates(accessToken, assetId),
      mroIntelligenceApi.getComplianceImpact(accessToken, assetId).catch(() => null),
    ])
      .then(([i, c, comp]) => {
        setIntel(i);
        setCandidates(c);
        setCompliance(comp);
      })
      .catch((err) => {
        // Never fall back to a healthy-looking UI on a fetch failure -- an
        // explicit error state is required.
        setError(normalizeApiError(err).message);
      })
      .finally(() => setLoading(false));
  }

  useEffect(load, [accessToken, assetId]);

  if (loading) return <p style={{ fontSize: 13, color: "#9ca3af" }}>Loading MRO intelligence…</p>;
  if (error) return <p style={{ fontSize: 13, color: "#f87171", fontWeight: 600 }}>{error}</p>;
  if (!intel) return <p style={{ fontSize: 13, color: "#f87171" }}>MRO intelligence unavailable.</p>;

  return (
    <div>
      <div
        style={{
          padding: "10px 14px",
          background: "rgba(56, 189, 248, 0.08)",
          border: "1px solid rgba(56, 189, 248, 0.3)",
          borderRadius: 8,
          fontSize: 12.5,
          color: "#93c5fd",
          marginBottom: 14,
        }}
      >
        H7 correlation layer — every value below is drawn from an existing authoritative source (HUMS, readiness, compliance,
        maintenance). This panel never re-derives health, diagnosis, RUL, compliance, or readiness itself.
      </div>

      {intel.availability === "DATA_UNAVAILABLE" && (
        <div style={{ marginBottom: 14 }}>
          <StatusBadge status="INSUFFICIENT_DATA" label="Insufficient data" />
        </div>
      )}

      {/* H7 Overview */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 10, marginBottom: 16 }}>
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase" }}>Health</div>
          <div style={{ fontSize: 13 }}>{intel.health_state ?? "UNKNOWN"} {intel.health_confidence ? `(${intel.health_confidence.toLowerCase()})` : ""}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase" }}>Open Diagnostics / Prognostic Alerts</div>
          <div style={{ fontSize: 13 }}>{intel.open_diagnostic_count} / {intel.open_prognostic_alert_count}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase" }}>Authoritative Readiness</div>
          <StatusBadge {...authoritativeReadinessBadge(intel.authoritative_readiness_state)} />
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase" }}>H7 Readiness Impact (Advisory)</div>
          <StatusBadge {...readinessImpactBadge(intel.readiness_impact)} />
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase" }}>Compliance Impact</div>
          <StatusBadge {...complianceImpactBadge(intel.compliance_impact)} />
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase" }}>Operational Impact</div>
          <StatusBadge {...operationalImpactBadge(intel.operational_impact)} />
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase" }}>Open Maintenance Candidates</div>
          <div style={{ fontSize: 13 }}>{intel.open_candidate_count}</div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#9ca3af", textTransform: "uppercase" }}>Integration Conflicts</div>
          <div style={{ fontSize: 13, color: intel.conflicts.length > 0 ? "#f87171" : undefined }}>{intel.conflicts.length}</div>
        </div>
      </div>

      {intel.explanation.length > 0 && (
        <p style={{ fontSize: 12.5, color: "#d1d5db", marginBottom: 16 }}>{intel.explanation.join(" ")}</p>
      )}

      {/* Maintenance Intelligence */}
      <div style={{ marginBottom: 18 }}>
        <h4 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700 }}>Maintenance Intelligence Candidates</h4>
        {!candidates || candidates.length === 0 ? (
          <p style={{ fontSize: 13, color: "#9ca3af", fontStyle: "italic" }}>
            No maintenance intelligence candidates currently identified.
          </p>
        ) : (
          candidates.map((c) => (
            <CandidateCard key={c.id} candidate={c} accessToken={accessToken} canWrite={canWrite} onChanged={load} />
          ))
        )}
        <p style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
          These are advisory candidates only — never confirmed maintenance actions, work orders, or grounding directives.
        </p>
      </div>

      {/* Compliance Impact */}
      <div style={{ marginBottom: 18 }}>
        <h4 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700 }}>Compliance Impact</h4>
        <ComplianceImpactSection compliance={compliance} />
      </div>

      {/* Operational Impact */}
      <div style={{ marginBottom: 18 }}>
        <h4 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700 }}>Operational Impact</h4>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
          <StatusBadge {...operationalImpactBadge(intel.operational_impact)} />
        </div>
      </div>

      {/* Conflicts */}
      <div>
        <h4 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700 }}>Integration Conflicts</h4>
        {intel.conflicts.length === 0 ? (
          <p style={{ fontSize: 13, color: "#9ca3af", fontStyle: "italic" }}>No integration conflicts detected.</p>
        ) : (
          intel.conflicts.map((conflict, i) => (
            <div
              key={i}
              style={{
                padding: 10,
                borderLeft: "4px solid #f87171",
                background: "rgba(248,113,113,0.06)",
                borderRadius: 6,
                marginBottom: 8,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 6 }}>
                <strong style={{ fontSize: 12.5, color: "#f87171" }}>CONFLICT: {conflict.check}</strong>
                <StatusBadge
                  status={conflict.severity === "HIGH" ? "NON_COMPLIANT" : conflict.severity === "MEDIUM" ? "REVIEW_REQUIRED" : "PENDING"}
                  label={conflict.severity}
                />
              </div>
              <p style={{ fontSize: 12, color: "#d1d5db", margin: "6px 0" }}>{conflict.description}</p>
              <SourceLineageTrail refs={[conflict.source_a, conflict.source_b]} />
            </div>
          ))
        )}
        {intel.conflicts.length > 0 && (
          <p style={{ fontSize: 11, color: "#6b7280", marginTop: 4 }}>
            Conflicts are flagged for human review only — this panel provides no action to auto-resolve or dismiss them.
          </p>
        )}
      </div>
    </div>
  );
}
