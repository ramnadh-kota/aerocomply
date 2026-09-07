"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { EvidenceCard } from "@/components/evidence/EvidenceCard";
import { getComponentInstance, componentForInstance, installationsForComponentInstance } from "@/lib/mock/components";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getEngineById } from "@/lib/mock/engines";
import { assessments } from "@/lib/mock/assessments";
import { evidenceForAssessment } from "@/lib/mock/evidence";
import { regulatoryRequirements } from "@/lib/mock/regulations";
import { maintenanceEventsForComponentInstance } from "@/lib/mock/maintenance";
import type { ComponentInstallation } from "@/lib/mock/types";

export default function ComponentDetailPage({ params }: { params: { id: string } }) {
  const instance = getComponentInstance(params.id);
  if (!instance) notFound();

  const component = componentForInstance(instance.id)!;
  const history = installationsForComponentInstance(instance.id);

  // Assessments that cite THIS component's part number as a condition (mock: match by partNumber in condition label).
  const relatedAssessments = assessments.filter((a) => a.conditionEvaluations.some((c) => c.label.includes(component.partNumber)));
  const relatedEvidence = relatedAssessments.flatMap((a) => evidenceForAssessment(a.id));
  const maintenanceEvents = maintenanceEventsForComponentInstance(instance.id);
  const currentInstallation = history.find((h) => h.removedAt === null);

  const installColumns: Column<ComponentInstallation>[] = [
    {
      key: "parent",
      header: "Parent Asset",
      render: (i) => {
        if (i.parentAssetType === "AIRCRAFT" && i.aircraftParentId) {
          const a = getAircraftById(i.aircraftParentId);
          return a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : i.aircraftParentId;
        }
        if (i.parentAssetType === "ENGINE" && i.engineParentId) {
          const e = getEngineById(i.engineParentId);
          return e ? <Link href={`/engines/${e.id}`} className="ac-mono">{e.serialNumber}</Link> : i.engineParentId;
        }
        return "—";
      },
    },
    { key: "type", header: "Parent Type", render: (i) => i.parentAssetType },
    { key: "position", header: "Position", render: (i) => i.position },
    { key: "installed", header: "Installed", render: (i) => i.installedAt },
    { key: "removed", header: "Removed", render: (i) => i.removedAt ?? "— (current)" },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Components", href: "/components" }, { label: instance.serialNumber }]} />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{component.partNumber} — {instance.serialNumber}</h1>
          <p className="ac-subtitle">{component.description} · {component.manufacturer}</p>
        </div>
        <StatusBadge status={component.requiresSerialization ? "VERIFIED" : "PENDING"} label={component.requiresSerialization ? "Serialized" : "Batch-Tracked"} />
      </div>

      <div className="ac-grid-2 ac-section">
        <div className="ac-card">
          <p className="ac-kpi-label">Current Status</p>
          <div style={{ marginTop: 6 }}>
            <StatusBadge status={currentInstallation ? "ACTIVE" : "STORED"} label={currentInstallation ? "Installed" : "Removed / Not Installed"} />
          </div>
        </div>
        <div className="ac-card">
          <p className="ac-kpi-label">Compliance Impact</p>
          <div style={{ marginTop: 6 }}>
            {relatedAssessments[0] ? <StatusBadge status={relatedAssessments[0].systemResult} /> : <span className="ac-text-sm ac-text-muted">Not cited in any assessment</span>}
          </div>
        </div>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Installation History</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <DataTable columns={installColumns} rows={history} emptyMessage="No installation history recorded for this component instance." />
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Applicable Requirements &amp; Assessment History</h2>
        {relatedAssessments.length === 0 && (
          <p className="ac-text-sm ac-text-muted">No assessment currently cites this component&rsquo;s part number as a condition.</p>
        )}
        <div className="ac-flex ac-flex-col ac-gap-2">
          {relatedAssessments.map((a) => (
            <Link key={a.id} href={`/assessments/${a.id}`} className="ac-card ac-flex ac-justify-between ac-items-center">
              <span className="ac-mono">{regulatoryRequirements.find((r) => r.id === a.regulatoryRequirementId)?.requirementNumber}</span>
              <StatusBadge status={a.systemResult} />
            </Link>
          ))}
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Maintenance History</h2>
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr><th>Date</th><th>Type</th><th>Description</th><th>Status</th></tr>
            </thead>
            <tbody>
              {maintenanceEvents.length === 0 && (
                <tr><td colSpan={4} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 16 }}>No maintenance events recorded.</td></tr>
              )}
              {maintenanceEvents.map((m) => (
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
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Evidence</h2>
        {relatedEvidence.length === 0 && <p className="ac-text-sm ac-text-muted">No evidence linked yet.</p>}
        <div className="ac-grid-2">
          {relatedEvidence.map((e) => (
            <EvidenceCard key={e.id} evidence={e} />
          ))}
        </div>
      </section>
    </div>
  );
}
