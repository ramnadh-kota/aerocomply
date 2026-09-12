"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { regulatoryRequirements } from "@/lib/mock/regulations";
import { assessmentsForRequirement } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import type { RequirementType } from "@/lib/mock/types";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { aircraftApi, type BackendAircraft } from "@/lib/api/aircraft";
import {
  regulatoryRequirementsApi,
  complianceAssessmentsApi,
  type BackendRegulatoryRequirement,
  type BackendComplianceAssessment,
} from "@/lib/api/compliance";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";

const TYPES: RequirementType[] = ["AD", "SB", "REGULATION", "RULE", "AMC", "GM", "SIB", "NOTICE", "OTHER"];

function badgeKindForStatus(status: string): Parameters<typeof StatusBadge>[0]["status"] {
  return status === "COMPLIANT" || status === "NON_COMPLIANT" || status === "REVIEW_REQUIRED" || status === "UNKNOWN"
    ? status
    : "UNKNOWN";
}

function RealRegulatoryRegister() {
  const { apiBaseUrl } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  const [requirements, setRequirements] = useState<BackendRegulatoryRequirement[]>([]);
  const [aircraftList, setAircraftList] = useState<BackendAircraft[]>([]);
  const [assessments, setAssessments] = useState<BackendComplianceAssessment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([regulatoryRequirementsApi.list(accessToken), aircraftApi.list(accessToken)])
      .then(async ([reqList, acList]) => {
        if (cancelled) return;
        setRequirements(reqList);
        setAircraftList(acList);
        const perAircraft = await Promise.all(
          acList.map((a) => complianceAssessmentsApi.listForAircraft(accessToken, a.id))
        );
        if (cancelled) return;
        setAssessments(perAircraft.flat());
      })
      .catch((err) => {
        if (!cancelled) setError(normalizeApiError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, isAuthenticated]);

  const registrationFor = (aircraftId: string) =>
    aircraftList.find((a) => a.id === aircraftId)?.registration ?? aircraftId;

  const rows = requirements.map((req) => {
    const reqAssessments = assessments.filter((a) => a.requirement_id === req.id);
    const latest = [...reqAssessments].sort((a, b) => b.evaluated_at.localeCompare(a.evaluated_at))[0];
    const gap = !latest || latest.status === "NON_COMPLIANT" || latest.status === "REVIEW_REQUIRED" || latest.status === "UNKNOWN";
    return { req, assessments: reqAssessments, latest, gap };
  });
  const openGapCount = rows.filter((r) => r.gap).length;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Compliance", href: "/compliance" }, { label: "Regulatory Register" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Regulatory Register</h1>
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
        <RealDataPanel
          loading={loading}
          error={error}
          isEmpty={requirements.length === 0}
          emptyMessage="No regulatory requirements are recorded for this organization yet."
        >
          <div className="ac-card" style={{ padding: "var(--ac-space-3)", marginBottom: 12, borderColor: "var(--ac-status-review)" }}>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              Applicability (which aircraft a requirement applies to) and status here are
              exactly what a human recorded via an assessment — no automated condition-tree
              applicability engine runs behind this list. {rows.length} requirement(s) shown ·{" "}
              {openGapCount} with an open gap or no assessment on file.
            </p>
          </div>

          <div className="ac-card" style={{ padding: 0 }}>
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Requirement</th>
                  <th>Authority</th>
                  <th>Compliance Time</th>
                  <th>Assessed Aircraft</th>
                  <th>Status</th>
                  <th>Gap</th>
                </tr>
              </thead>
              <tbody>
                {rows.map(({ req, assessments: reqAssessments, latest, gap }) => (
                  <tr key={req.id}>
                    <td className="ac-mono">{req.requirement_number}<div className="ac-text-sm ac-text-muted">{req.title}</div></td>
                    <td>{req.authority}</td>
                    <td className="ac-text-sm">{req.compliance_time ?? "—"}</td>
                    <td className="ac-text-sm">
                      {reqAssessments.length === 0 ? "Not yet assessed" : (
                        reqAssessments.map((a, idx) => (
                          <span key={a.id}>
                            {idx > 0 && ", "}
                            {registrationFor(a.aircraft_id)}
                          </span>
                        ))
                      )}
                    </td>
                    <td>{latest ? <StatusBadge status={badgeKindForStatus(latest.status)} /> : <StatusBadge status="UNKNOWN" label="Not assessed" />}</td>
                    <td>{gap ? <StatusBadge status="NON_COMPLIANT" label="Open" /> : <StatusBadge status="COMPLIANT" label="Closed" />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </RealDataPanel>
      )}
    </div>
  );
}

function DemoRegulatoryRegister() {
  const [typeFilter, setTypeFilter] = useState<string>("ALL");

  const rows = regulatoryRequirements
    .filter((r) => typeFilter === "ALL" || r.requirementType === typeFilter)
    .map((req) => {
      const assessments = assessmentsForRequirement(req.id);
      const latest = [...assessments].sort((a, b) => b.evaluatedAt.localeCompare(a.evaluatedAt))[0];
      const evidenceCount = latest ? evidenceForAssessment(latest.id).length : 0;
      const gap = !latest || latest.finalStatus === "NON_COMPLIANT" || latest.finalStatus === "REVIEW_REQUIRED" || latest.finalStatus === "INSUFFICIENT_DATA";
      return { req, assessments, latest, evidenceCount, gap };
    });

  const openGapCount = rows.filter((r) => r.gap).length;

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Compliance", href: "/compliance" }, { label: "Regulatory Register" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Regulatory Register — AD / SB &amp; Gap Packager</h1>
          <p className="ac-subtitle">{rows.length} requirement(s) shown · {openGapCount} with an open gap or UNKNOWN status. Applicability and status are never inferred from missing evidence.</p>
        </div>
      </div>

      <div className="ac-flex ac-gap-2 ac-section" style={{ flexWrap: "wrap" }}>
        <button className="ac-btn" style={typeFilter === "ALL" ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined} onClick={() => setTypeFilter("ALL")}>All</button>
        {TYPES.map((t) => (
          <button key={t} className="ac-btn" style={typeFilter === t ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined} onClick={() => setTypeFilter(t)}>{t}</button>
        ))}
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <table className="ac-table">
          <thead>
            <tr>
              <th>Requirement</th>
              <th>Type</th>
              <th>Compliance Time</th>
              <th>Applicable Aircraft</th>
              <th>Evidence</th>
              <th>Status</th>
              <th>Gap</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ req, assessments, latest, evidenceCount, gap }) => (
              <tr key={req.id}>
                <td><Link href={`/regulations/${req.id}`} className="ac-mono">{req.requirementNumber}</Link></td>
                <td>{req.requirementType}</td>
                <td className="ac-text-sm">{req.complianceTime}</td>
                <td className="ac-text-sm">
                  {assessments.length === 0 ? "Insufficient source data." : (
                    assessments.map((a, idx) => {
                      const ac = a.subjectType === "AIRCRAFT" ? getAircraftById(a.subjectId) : undefined;
                      return (
                        <span key={a.id}>
                          {idx > 0 && ", "}
                          {ac ? <Link href={`/aircraft/${ac.id}`} className="ac-mono">{currentRegistration(ac)}</Link> : a.subjectId}
                        </span>
                      );
                    })
                  )}
                </td>
                <td>{latest ? evidenceCount : "—"}</td>
                <td>{latest ? <Link href={`/assessments/${latest.id}`}><StatusBadge status={latest.finalStatus} /></Link> : <StatusBadge status="INSUFFICIENT_DATA" label="No assessment" />}</td>
                <td>{gap ? <StatusBadge status="NON_COMPLIANT" label="Open" /> : <StatusBadge status="COMPLIANT" label="Closed" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function RegulatoryRegisterPage() {
  const { isReal, hydrated } = useDataMode();
  if (!hydrated) return null;
  return isReal ? <RealRegulatoryRegister /> : <DemoRegulatoryRegister />;
}
