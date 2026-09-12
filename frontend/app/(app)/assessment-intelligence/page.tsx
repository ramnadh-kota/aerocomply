"use client";

// MRO Assessment & Impact Intelligence Command Center — REAL-mode only.
// This is a new backend-authoritative domain (backend/app/services/assessment)
// with no legacy mock/demo data of its own, so there is no DEMO branch here;
// in DEMO mode we say so plainly rather than fabricating assessment results.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import {
  assessmentsApi,
  type BackendAssessment,
  type BackendAssessmentFinding,
  type BackendAssessmentGap,
  type BackendAssessmentRecommendation,
  type BackendAssessmentRisk,
  type BackendAssessmentRoadmapItem,
  type BackendAssessmentSnapshot,
} from "@/lib/api/assessments";

function severityBadge(severity: string) {
  const s = severity.toUpperCase();
  if (s === "CRITICAL" || s === "HIGH") return { status: "NON_COMPLIANT" as const, label: severity };
  if (s === "MODERATE") return { status: "REVIEW_REQUIRED" as const, label: severity };
  return { status: "APPLICABLE" as const, label: severity };
}

function AssessmentDetail({ assessment, onBack }: { assessment: BackendAssessment; onBack: () => void }) {
  const { accessToken } = useSession();
  const [snapshot, setSnapshot] = useState<BackendAssessmentSnapshot | null>(null);
  const [findings, setFindings] = useState<BackendAssessmentFinding[]>([]);
  const [risks, setRisks] = useState<BackendAssessmentRisk[]>([]);
  const [gaps, setGaps] = useState<BackendAssessmentGap[]>([]);
  const [recommendations, setRecommendations] = useState<BackendAssessmentRecommendation[]>([]);
  const [roadmap, setRoadmap] = useState<BackendAssessmentRoadmapItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [hasSnapshot, setHasSnapshot] = useState(true);

  const loadAll = () => {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    Promise.all([
      assessmentsApi.getLatestSnapshot(accessToken, assessment.id).catch((err) => {
        if (normalizeApiError(err).kind === "not_found") {
          setHasSnapshot(false);
          return null;
        }
        throw err;
      }),
      assessmentsApi.getFindings(accessToken, assessment.id),
      assessmentsApi.getRisks(accessToken, assessment.id),
      assessmentsApi.getGaps(accessToken, assessment.id),
      assessmentsApi.getRecommendations(accessToken, assessment.id),
      assessmentsApi.getRoadmap(accessToken, assessment.id),
    ])
      .then(([snap, f, r, g, rec, rm]) => {
        setSnapshot(snap);
        setHasSnapshot(snap !== null);
        setFindings(f);
        setRisks(r);
        setGaps(g);
        setRecommendations(rec);
        setRoadmap(rm);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, assessment.id]);

  const runNow = () => {
    if (!accessToken) return;
    setRunning(true);
    setError(null);
    assessmentsApi
      .run(accessToken, assessment.id)
      .then(() => loadAll())
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setRunning(false));
  };

  const findingColumns: Column<BackendAssessmentFinding>[] = [
    { key: "rank", header: "#", render: (f) => f.priority_rank },
    { key: "title", header: "Finding", render: (f) => f.title },
    { key: "severity", header: "Severity", render: (f) => <StatusBadge {...severityBadge(f.severity)} /> },
    { key: "materiality", header: "Materiality", render: (f) => f.materiality_score.toFixed(0) },
    { key: "complexity", header: "Complexity", render: (f) => f.complexity_band },
    { key: "impact", header: "Impact", render: (f) => f.impact_dimensions.join(", ") },
    { key: "entity", header: "Affected Entity", render: (f) => <span className="ac-mono">{f.entity_type}:{f.entity_id}</span> },
  ];

  const roadmapColumns: Column<BackendAssessmentRoadmapItem>[] = [
    { key: "seq", header: "#", render: (r) => r.sequence },
    { key: "title", header: "Initiative", render: (r) => r.title },
    { key: "priority", header: "Priority", render: (r) => <StatusBadge {...severityBadge(r.priority)} /> },
    { key: "owner", header: "Owner", render: (r) => r.owner_role ?? "UNKNOWN" },
    {
      key: "deps",
      header: "Dependencies",
      render: (r) =>
        r.prerequisite_sequence_numbers.length > 0 ? (
          <span title="Blocked until these sequence numbers complete">
            ⛔ #{r.prerequisite_sequence_numbers.join(", #")}
          </span>
        ) : (
          "None"
        ),
    },
    { key: "effort", header: "Effort", render: (r) => `${r.estimated_effort_band} (confidence: ${r.effort_confidence})` },
    { key: "status", header: "Status", render: (r) => <StatusBadge {...genericStatusBadge(r.status)} /> },
  ];

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Assessment Intelligence", href: "/assessment-intelligence" },
          { label: assessment.name },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{assessment.name}</h1>
          <p className="ac-subtitle">
            Scope: {assessment.scope_type}
            {assessment.scope_id ? ` (${assessment.scope_id})` : ""} · Status: {assessment.status}
          </p>
        </div>
        <div className="ac-flex ac-gap-2">
          <button className="ac-btn" onClick={onBack}>← Back</button>
          <button className="ac-btn" onClick={runNow} disabled={running}>
            {running ? "Running…" : hasSnapshot ? "Re-run Assessment" : "Run Assessment"}
          </button>
        </div>
      </div>

      <RealDataPanel loading={loading} error={error} isEmpty={false} emptyMessage="">
        {!hasSnapshot ? (
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              This assessment has not been run yet. Click &quot;Run Assessment&quot; to generate real
              findings, risks, gaps, recommendations, and a roadmap from operational data.
            </p>
          </div>
        ) : (
          <>
            {snapshot && (
              <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
                <div className="ac-flex ac-gap-4" style={{ flexWrap: "wrap" }}>
                  <div>
                    <div className="ac-text-sm ac-text-muted">Snapshot Version</div>
                    <div className="ac-h2">v{snapshot.version}</div>
                  </div>
                  <div>
                    <div className="ac-text-sm ac-text-muted">Overall Score</div>
                    <div className="ac-h2">{snapshot.overall_score}</div>
                  </div>
                  <div>
                    <div className="ac-text-sm ac-text-muted">Maturity Band</div>
                    <div className="ac-h2">{snapshot.maturity_band}</div>
                  </div>
                  <div>
                    <div className="ac-text-sm ac-text-muted">Findings</div>
                    <div className="ac-h2">{snapshot.finding_count} ({snapshot.critical_finding_count} critical)</div>
                  </div>
                </div>
                {snapshot.summary && <p className="ac-text-sm" style={{ marginTop: 10 }}>{snapshot.summary}</p>}
              </div>
            )}

            <h2 className="ac-h2" style={{ marginTop: "var(--ac-space-5)" }}>Findings</h2>
            {findings.length === 0 ? (
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                  No assessable operational findings are currently available for this scope.
                </p>
              </div>
            ) : (
              <div className="ac-card" style={{ padding: 0 }}>
                <DataTable columns={findingColumns} rows={findings} />
              </div>
            )}

            <h2 className="ac-h2" style={{ marginTop: "var(--ac-space-5)" }}>Risks</h2>
            {risks.length === 0 ? (
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No risks identified.</p>
              </div>
            ) : (
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                {risks.map((r) => (
                  <div key={r.id} style={{ marginBottom: 10 }}>
                    <StatusBadge {...severityBadge(r.risk_level)} /> <strong>{r.reason}</strong>
                    <div className="ac-text-sm ac-text-muted">
                      Likelihood: {r.likelihood} · Owner: {r.owner_role ?? "UNKNOWN"}
                      {r.mitigation ? ` · Mitigation: ${r.mitigation}` : ""}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <h2 className="ac-h2" style={{ marginTop: "var(--ac-space-5)" }}>Gaps</h2>
            {gaps.length === 0 ? (
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No gaps identified.</p>
              </div>
            ) : (
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                {gaps.map((g) => (
                  <div key={g.id} style={{ marginBottom: 10 }}>
                    <strong>{g.category}</strong> ({g.severity})
                    <div className="ac-text-sm ac-text-muted">
                      Expected: {g.expected_condition} — Current: {g.current_condition}
                    </div>
                    <div className="ac-text-sm">Recommended: {g.recommended_action}</div>
                  </div>
                ))}
              </div>
            )}

            <h2 className="ac-h2" style={{ marginTop: "var(--ac-space-5)" }}>Recommendations</h2>
            {recommendations.length === 0 ? (
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No recommendations yet.</p>
              </div>
            ) : (
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                {recommendations.map((r) => (
                  <div key={r.id} style={{ marginBottom: 10 }}>
                    <StatusBadge {...severityBadge(r.priority)} /> <strong>{r.recommendation}</strong>
                    <div className="ac-text-sm ac-text-muted">
                      Why: {r.why} · Owner: {r.responsible_role ?? "UNKNOWN"} · Status: {r.status}
                    </div>
                  </div>
                ))}
              </div>
            )}

            <h2 className="ac-h2" style={{ marginTop: "var(--ac-space-5)" }}>Roadmap</h2>
            {roadmap.length === 0 ? (
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No roadmap items yet.</p>
              </div>
            ) : (
              <div className="ac-card" style={{ padding: 0 }}>
                <DataTable columns={roadmapColumns} rows={roadmap} />
              </div>
            )}
          </>
        )}
      </RealDataPanel>
    </div>
  );
}

function RealAssessmentIntelligence() {
  const { apiBaseUrl } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  const [assessments, setAssessments] = useState<BackendAssessment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [selected, setSelected] = useState<BackendAssessment | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);

  const loadList = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    assessmentsApi
      .list(accessToken)
      .then(setAssessments)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated]);

  const createAssessment = () => {
    if (!accessToken || !newName.trim()) return;
    setCreating(true);
    setError(null);
    assessmentsApi
      .create(accessToken, { name: newName.trim(), scope_type: "FLEET" })
      .then((created) => {
        setNewName("");
        loadList();
        setSelected(created);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setCreating(false));
  };

  if (selected) {
    return <AssessmentDetail assessment={selected} onBack={() => setSelected(null)} />;
  }

  const columns: Column<BackendAssessment>[] = [
    { key: "name", header: "Assessment", render: (a) => a.name },
    { key: "scope", header: "Scope", render: (a) => a.scope_type },
    { key: "status", header: "Status", render: (a) => <StatusBadge {...genericStatusBadge(a.status)} /> },
    { key: "created", header: "Created", render: (a) => new Date(a.created_at).toLocaleDateString(), sortValue: (a) => a.created_at },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Assessment Intelligence" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">MRO Assessment &amp; Impact Intelligence</h1>
          <p className="ac-subtitle">REAL data mode — connected to {apiBaseUrl}</p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            REAL data mode requires signing in. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <>
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
              <input
                className="ac-input"
                style={{ width: 280 }}
                placeholder="New fleet assessment name…"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                aria-label="New assessment name"
              />
              <button className="ac-btn" onClick={createAssessment} disabled={creating || !newName.trim()}>
                {creating ? "Creating…" : "Create Assessment"}
              </button>
            </div>
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={assessments.length === 0}
            emptyMessage="No assessments have been created yet. Create one above to analyze real operational findings, risks, gaps, and a prioritized roadmap."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <DataTable columns={columns} rows={assessments} onRowClick={(a) => setSelected(a)} />
            </div>
          </RealDataPanel>
        </>
      )}
    </div>
  );
}

export default function AssessmentIntelligencePage() {
  const { isReal, hydrated } = useDataMode();
  if (!hydrated) return null;
  if (!isReal) {
    return (
      <div>
        <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Assessment Intelligence" }]} />
        <div className="ac-section-header">
          <div>
            <h1 className="ac-h1">MRO Assessment &amp; Impact Intelligence</h1>
          </div>
        </div>
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Assessment intelligence is a REAL-data-mode capability — it reads directly from the
            connected backend and has no demo dataset. Switch to REAL data mode to use it.
          </p>
        </div>
      </div>
    );
  }
  return <RealAssessmentIntelligence />;
}
