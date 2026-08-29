"use client";

import { useState } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { DataTable, type Column } from "@/components/tables/DataTable";
import {
  getAircraftById,
  getAircraftVariant,
  getAircraftType,
  currentRegistration,
} from "@/lib/mock/aircraft";
import { installationsForAircraft as engineHistoryForAircraft, getEngineById, getEngineType, currentEnginesForAircraft } from "@/lib/mock/engines";
import { componentInstallationsForAircraft, componentForInstance } from "@/lib/mock/components";
import { assessmentsForAircraft } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { getOrganizationById } from "@/lib/mock/organizations";
import { getRequirementById } from "@/lib/mock/regulations";
import { auditEventsForObjectLabelContains } from "@/lib/mock/audit";
import { maintenanceEventsForAircraft } from "@/lib/mock/maintenance";
import { Timeline } from "@/components/timeline/Timeline";
import type { ApplicabilityAssessment, ComponentInstallation, EngineInstallation } from "@/lib/mock/types";

const TABS = ["Overview", "Configuration", "Engines", "Components", "Regulatory", "Assessments", "Evidence", "Audit"] as const;
type Tab = (typeof TABS)[number];

export default function AircraftDetailPage({ params }: { params: { id: string } }) {
  const aircraft = getAircraftById(params.id);
  const [tab, setTab] = useState<Tab>("Overview");

  if (!aircraft) notFound();

  const variant = getAircraftVariant(aircraft.aircraftVariantId)!;
  const type = getAircraftType(variant.aircraftTypeId)!;
  const operator = getOrganizationById(aircraft.operatorOrgId);
  const registration = currentRegistration(aircraft);
  const currentEngines = currentEnginesForAircraft(aircraft.id);
  const engineHistory = engineHistoryForAircraft(aircraft.id);
  const componentHistory = componentInstallationsForAircraft(aircraft.id);
  const assessments = assessmentsForAircraft(aircraft.id);
  const allEvidence = assessments.flatMap((a) => evidenceForAssessment(a.id));
  const auditEvents = auditEventsForObjectLabelContains(registration).concat(auditEventsForObjectLabelContains(aircraft.id));
  const maintenanceEvents = maintenanceEventsForAircraft(aircraft.id);
  const nextAction = maintenanceEvents.find((m) => m.status === "OVERDUE") ?? maintenanceEvents.find((m) => m.status === "SCHEDULED");
  const lastComplianceEvent = assessments[0];

  const engineColumns: Column<EngineInstallation>[] = [
    { key: "position", header: "Position", render: (i) => i.position },
    { key: "engine", header: "Engine Serial Number", render: (i) => <Link href={`/engines/${i.engineId}`} className="ac-mono">{getEngineById(i.engineId)!.serialNumber}</Link> },
    { key: "type", header: "Engine Type", render: (i) => getEngineType(getEngineById(i.engineId)!.engineTypeId)!.modelDesignation },
    { key: "installed", header: "Installed", render: (i) => i.installedAt },
    { key: "removed", header: "Removed", render: (i) => i.removedAt ?? "— (current)" },
  ];

  const componentColumns: Column<ComponentInstallation>[] = [
    { key: "pn", header: "Part Number", render: (i) => <Link href={`/components/${i.componentInstanceId}`} className="ac-mono">{componentForInstance(i.componentInstanceId)?.partNumber}</Link> },
    { key: "desc", header: "Description", render: (i) => componentForInstance(i.componentInstanceId)?.description },
    { key: "position", header: "Position", render: (i) => i.position },
    { key: "installed", header: "Installed", render: (i) => i.installedAt },
    { key: "removed", header: "Removed", render: (i) => i.removedAt ?? "— (current)" },
  ];

  const assessmentColumns: Column<ApplicabilityAssessment>[] = [
    { key: "req", header: "Requirement", render: (a) => <span className="ac-mono">{getRequirementById(a.regulatoryRequirementId)?.requirementNumber}</span> },
    { key: "date", header: "Date", render: (a) => new Date(a.evaluatedAt).toLocaleDateString() },
    { key: "system", header: "System Result", render: (a) => <StatusBadge status={a.systemResult} /> },
    { key: "human", header: "Human Decision", render: (a) => a.humanDecision.replace(/_/g, " ") },
    { key: "final", header: "Status", render: (a) => <StatusBadge status={a.finalStatus} /> },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Aircraft", href: "/aircraft" }, { label: registration }]} />

      <div className="ac-section-header">
        <div>
          <div className="ac-flex ac-items-center ac-gap-3">
            <h1 className="ac-h1">{registration}</h1>
            <StatusBadge status={aircraft.status} />
          </div>
          <p className="ac-subtitle">
            {type.manufacturer} {variant.modelDesignation} · MSN {aircraft.msn}
          </p>
        </div>
      </div>

      <div className="ac-grid-3 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Aircraft Variant</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{variant.modelDesignation}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Operator</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{operator?.name ?? "—"}</p>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Entry Into Service</p>
          <p style={{ fontWeight: 600, marginTop: 4 }}>{aircraft.entryIntoServiceDate}</p>
        </div>
      </div>

      <div className="ac-tabs" role="tablist">
        {TABS.map((t) =>
          t === "Configuration" ? (
            <Link key={t} href={`/aircraft/${aircraft.id}/configuration`} className="ac-tab">
              {t}
            </Link>
          ) : (
            <button key={t} role="tab" aria-selected={tab === t} className={`ac-tab${tab === t ? " active" : ""}`} onClick={() => setTab(t)}>
              {t}
            </button>
          )
        )}
      </div>

      {tab === "Overview" && (
        <div>
          <div className="ac-grid-2 ac-section">
            <div className="ac-card">
              <p className="ac-kpi-label">Next Required Action</p>
              {nextAction ? (
                <>
                  <p style={{ fontWeight: 600, marginTop: 4, fontSize: 13 }}>{nextAction.description}</p>
                  <StatusBadge
                    status={nextAction.status === "OVERDUE" ? "NON_COMPLIANT" : "PENDING"}
                    label={nextAction.status === "OVERDUE" ? `Overdue since ${nextAction.date}` : `Scheduled ${nextAction.date}`}
                  />
                </>
              ) : (
                <p className="ac-text-sm ac-text-muted" style={{ marginTop: 4 }}>No outstanding action.</p>
              )}
            </div>
            <div className="ac-card">
              <p className="ac-kpi-label">Last Compliance Event</p>
              {lastComplianceEvent ? (
                <>
                  <p style={{ fontWeight: 600, marginTop: 4, fontSize: 13 }}>
                    <Link href={`/regulations/${lastComplianceEvent.regulatoryRequirementId}`} className="ac-mono">
                      {getRequirementById(lastComplianceEvent.regulatoryRequirementId)?.requirementNumber}
                    </Link>{" "}
                    — {new Date(lastComplianceEvent.evaluatedAt).toLocaleDateString()}
                  </p>
                  <StatusBadge status={lastComplianceEvent.finalStatus} />
                </>
              ) : (
                <p className="ac-text-sm ac-text-muted" style={{ marginTop: 4 }}>No assessments recorded.</p>
              )}
            </div>
          </div>

          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Current Engine Configuration</h2>
            <div className="ac-card" style={{ padding: 0 }}>
              <DataTable columns={engineColumns} rows={currentEngines} />
            </div>
          </section>
          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Component Summary</h2>
            <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
              {componentHistory.filter((c) => c.removedAt === null).length} components currently installed and tracked · {componentHistory.length} installation records total
            </p>
          </section>
          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Maintenance Events</h2>
            <div className="ac-card" style={{ padding: 0 }}>
              <table className="ac-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Description</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {maintenanceEvents.length === 0 && (
                    <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No maintenance events recorded.</td></tr>
                  )}
                  {maintenanceEvents.slice(0, 6).map((m) => (
                    <tr key={m.id}>
                      <td className="ac-mono ac-text-sm">{m.date}</td>
                      <td className="ac-text-sm">{m.eventType.replace(/_/g, " ")}</td>
                      <td className="ac-text-sm">{m.description}</td>
                      <td>
                        <StatusBadge
                          status={m.status === "OVERDUE" ? "NON_COMPLIANT" : m.status === "COMPLETED" ? "COMPLIANT" : m.status === "IN_PROGRESS" ? "REVIEW_REQUIRED" : "PENDING"}
                          label={m.status.replace(/_/g, " ")}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Regulatory Assessment Summary</h2>
            <div className="ac-card" style={{ padding: 0 }}>
              <DataTable columns={assessmentColumns} rows={assessments.slice(0, 5)} getRowHref={(a) => `/assessments/${a.id}`} />
            </div>
          </section>
          <section className="ac-section">
            <h2 className="ac-h2" style={{ marginBottom: 10 }}>Recent Events</h2>
            <div className="ac-card">
              <Timeline
                entries={auditEvents.slice(0, 5).map((e) => ({
                  id: e.id,
                  date: new Date(e.timestamp).toLocaleString(),
                  title: e.action.replace(/_/g, " ").replace(/\./g, " — "),
                  detail: `${e.actor} (${e.actorRole})`,
                }))}
              />
            </div>
          </section>
        </div>
      )}

      {tab === "Engines" && (
        <div className="ac-card" style={{ padding: 0 }}>
          <DataTable columns={engineColumns} rows={engineHistory} emptyMessage="No engine installation history recorded." />
        </div>
      )}

      {tab === "Components" && (
        <div className="ac-card" style={{ padding: 0 }}>
          <DataTable columns={componentColumns} rows={componentHistory} emptyMessage="No component installation history recorded." />
        </div>
      )}

      {tab === "Regulatory" && (
        <div className="ac-card" style={{ padding: 0 }}>
          <DataTable columns={assessmentColumns} rows={assessments} getRowHref={(a) => `/assessments/${a.id}`} emptyMessage="No regulatory assessments yet." />
        </div>
      )}

      {tab === "Assessments" && (
        <div className="ac-card" style={{ padding: 0 }}>
          <DataTable columns={assessmentColumns} rows={assessments} getRowHref={(a) => `/assessments/${a.id}`} emptyMessage="No assessments yet." />
        </div>
      )}

      {tab === "Evidence" && (
        <div className="ac-grid-2">
          {allEvidence.length === 0 && <p className="ac-text-muted">No evidence linked yet.</p>}
          {allEvidence.map((e) => (
            <Link key={e.id} href={`/evidence#${e.id}`} className="ac-card" style={{ display: "block" }}>
              <p className="ac-eyebrow">{e.evidenceType.replace(/_/g, " ")}</p>
              <p style={{ fontWeight: 600, fontSize: 13, margin: "4px 0" }} className="ac-mono">{e.sourceLabel}</p>
              <p className="ac-text-sm ac-text-secondary">{e.description}</p>
            </Link>
          ))}
        </div>
      )}

      {tab === "Audit" && (
        <div className="ac-card">
          <Timeline
            entries={auditEvents.map((e) => ({
              id: e.id,
              date: new Date(e.timestamp).toLocaleString(),
              title: e.action.replace(/_/g, " ").replace(/\./g, " — "),
              detail: `${e.actor} (${e.actorRole}) — ${e.objectLabel}`,
            }))}
          />
          {auditEvents.length === 0 && <p className="ac-text-muted">No audit events recorded for this aircraft yet.</p>}
        </div>
      )}
    </div>
  );
}
