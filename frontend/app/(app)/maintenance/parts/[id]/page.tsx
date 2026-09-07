"use client";

import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge, partStatusBadge, traceabilityStatusBadge, workOrderStatusBadge } from "@/components/status/StatusBadge";
import { getPartById } from "@/lib/mock/parts";
import {
  receivingRecordForPart,
  certificatesForPart,
  installationsForPart,
  removalsForPart,
  currentInstallationForPart,
  traceabilityStatusForPart,
} from "@/lib/mock/partTraceability";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { getComponentInstance } from "@/lib/mock/components";
import { getUserById } from "@/lib/mock/roles";

// M7.2/M7.3 — Parts traceability detail: renders the real chain (Identity ->
// Receiving -> Certificate -> Installation -> Removal -> Current
// Disposition) using only records that actually exist in
// lib/mock/partTraceability.ts. Any missing link is shown as "Insufficient
// source data." rather than inferred or defaulted to a passing state.

function actorName(userId: string): string {
  const u = getUserById(userId);
  return u ? u.name : userId;
}

export default function PartTraceabilityDetailPage({ params }: { params: { id: string } }) {
  const part = getPartById(params.id);
  if (!part) notFound();

  const receiving = receivingRecordForPart(part.id);
  const certificates = certificatesForPart(part.id);
  const installations = installationsForPart(part.id);
  const removals = removalsForPart(part.id);
  const currentInstallation = currentInstallationForPart(part.id);
  const traceability = traceabilityStatusForPart(part.id);

  const workOrder = part.workOrderId ? getWorkOrderById(part.workOrderId) : undefined;
  const aircraft = part.installedAircraftId ? getAircraftById(part.installedAircraftId) : undefined;
  const componentInstance = part.installedComponentInstanceId ? getComponentInstance(part.installedComponentInstanceId) : undefined;

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Parts & Traceability", href: "/maintenance/parts" },
          { label: part.partNumber },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{part.partNumber} — {part.description}</h1>
          <p className="ac-subtitle">
            {part.classification === "SERIALIZED" ? `Serial ${part.serialNumber ?? "Insufficient source data."}` : `Batch/Lot ${part.batchOrLot ?? "Insufficient source data."}`}
            {" · "}Manufacturer: {part.manufacturer ?? "Insufficient source data."}
          </p>
        </div>
        <div className="ac-flex ac-gap-2">
          <StatusBadge {...partStatusBadge(part.status)} />
          <StatusBadge {...traceabilityStatusBadge(traceability)} label={`Traceability: ${traceability.replace(/_/g, " ")}`} />
        </div>
      </div>

      {/* Part Identity */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Part Identity</h2>
        <div className="ac-kpi-grid">
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Classification</p>
            <p className="ac-kpi-value" style={{ fontSize: 16 }}>{part.classification}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Quantity</p>
            <p className="ac-kpi-value">{part.quantity}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Location</p>
            <p className="ac-kpi-value" style={{ fontSize: 16 }}>{part.location}</p>
          </div>
          <div className="ac-kpi-card">
            <p className="ac-kpi-label">Life Limit</p>
            <p className="ac-kpi-value" style={{ fontSize: 14 }}>{part.lifeLimitInfo ?? "Insufficient source data."}</p>
          </div>
        </div>
      </section>

      {/* Receiving */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Receiving Record</h2>
        <div className="ac-card">
          {receiving ? (
            <div className="ac-text-sm">
              <p style={{ margin: "0 0 4px" }}>Received {receiving.receivedDate} by {actorName(receiving.receivedBy)}</p>
              <p style={{ margin: "0 0 4px" }}>Source: {receiving.source}</p>
              <p style={{ margin: 0 }}>Quantity received: {receiving.quantityReceived}</p>
            </div>
          ) : (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data. No receiving record on file — this part has not been logged as received.</p>
          )}
        </div>
      </section>

      {/* Certificate */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Certificate Evidence</h2>
        {certificates.length === 0 ? (
          <div className="ac-card">
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data. No certificate record exists for this part yet.</p>
          </div>
        ) : (
          <div className="ac-flex ac-flex-col ac-gap-3">
            {certificates.map((c) => (
              <div key={c.id} className="ac-card">
                <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
                  <span className="ac-mono" style={{ fontWeight: 600 }}>{c.certificateType.replace(/_/g, " ")}</span>
                  <StatusBadge
                    status={c.verificationStatus === "PRESENT" ? "COMPLIANT" : c.verificationStatus === "MISSING" ? "REVIEW_REQUIRED" : c.verificationStatus === "NOT_VERIFIED" ? "UNVERIFIED" : "INSUFFICIENT_DATA"}
                    label={c.verificationStatus.replace(/_/g, " ")}
                  />
                </div>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>Reference: {c.certificateReference ?? "Insufficient source data."}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>Issuer: {c.certificateIssuer ?? "Insufficient source data."}</p>
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Date: {c.certificateDate ?? "Insufficient source data."}</p>
              </div>
            ))}
          </div>
        )}
        <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
          A missing or unverified certificate reflects an evidence gap only — it does not by itself mean this part is non-compliant. See the applicable maintenance record and work order for a compliance determination.
        </p>
      </section>

      {/* Installation */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Installation History</h2>
        {installations.length === 0 ? (
          <div className="ac-card">
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Insufficient source data. No installation record on file for this part.</p>
          </div>
        ) : (
          <div className="ac-flex ac-flex-col ac-gap-3">
            {installations.map((i) => {
              const a = getAircraftById(i.aircraftId);
              const wo = i.workOrderId ? getWorkOrderById(i.workOrderId) : undefined;
              return (
                <div key={i.id} className="ac-card">
                  <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>
                    Installed {i.installationDate} on {a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : "Insufficient source data."} by {actorName(i.installedBy)}
                  </p>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                    Work Order: {wo ? <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-mono">{wo.workOrderNumber}</Link> : "Insufficient source data."}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Removal */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Removal History</h2>
        <div className="ac-card">
          {removals.length === 0 ? (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No removal recorded for this part.</p>
          ) : (
            removals.map((r) => (
              <p key={r.id} className="ac-text-sm" style={{ margin: "0 0 4px" }}>
                Removed {r.removalDate} by {actorName(r.removedBy)} — {r.reason}
              </p>
            ))
          )}
        </div>
      </section>

      {/* Current Disposition */}
      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Current Disposition</h2>
        <div className="ac-card">
          <div className="ac-text-sm">
            <p style={{ margin: "0 0 4px" }}>Status: <StatusBadge {...partStatusBadge(part.status)} /></p>
            <p style={{ margin: "0 0 4px" }}>
              Currently installed on: {aircraft ? <Link href={`/aircraft/${aircraft.id}`} className="ac-mono">{currentRegistration(aircraft)}</Link> : "Not currently installed."}
            </p>
            <p style={{ margin: "0 0 4px" }}>
              Component instance: {componentInstance ? <Link href="/components" className="ac-mono">{componentInstance.id}</Link> : "Insufficient source data."}
            </p>
            <p style={{ margin: "0 0 4px" }}>
              Reserved for work order: {workOrder ? (
                <span className="ac-flex ac-items-center ac-gap-2" style={{ display: "inline-flex" }}>
                  <Link href={`/maintenance/work-orders/${workOrder.id}`} className="ac-mono">{workOrder.workOrderNumber}</Link>
                  <StatusBadge {...workOrderStatusBadge(workOrder.status)} />
                </span>
              ) : "Insufficient source data."}
            </p>
            {currentInstallation && (
              <p style={{ margin: 0 }} className="ac-text-sm ac-text-muted">
                Last known installation event: {currentInstallation.installationDate}.
              </p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
