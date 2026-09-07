import Link from "next/link";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { evidenceRepository, workOrderRepository, partRepository, userRepository } from "@/lib/domain/repositories";
import { getAssessmentById } from "@/lib/mock/assessments";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getEngineById } from "@/lib/mock/engines";
import { evidenceLifecycleStateFor } from "@/lib/mock/types";

// M8.4 — Evidence detail. Built against the M8.1 repository layer rather
// than importing lib/mock/evidence directly, as the first workflow to use
// that abstraction. Shows every link the record actually has and an
// explicit missing-link indicator for every one it doesn't — never infers
// a link that isn't recorded.

const TYPE_LABEL: Record<string, string> = {
  MAINTENANCE_RECORD: "Maintenance Record",
  OEM_DOCUMENT: "OEM Document",
  INSPECTION_RECORD: "Inspection Record",
  UPLOADED_DOCUMENT: "Uploaded File",
  STRUCTURED_RECORD_REFERENCE: "Structured Record Reference",
  REGULATORY_DOCUMENT: "Regulatory Document",
};

export default function EvidenceDetailPage({ params }: { params: { id: string } }) {
  const item = evidenceRepository.getById(params.id);
  if (!item) notFound();

  const assessment = getAssessmentById(item.applicabilityAssessmentId);
  const subjectAircraft = assessment?.subjectType === "AIRCRAFT" ? getAircraftById(assessment.subjectId) : undefined;
  const subjectEngine = assessment?.subjectType === "ENGINE" ? getEngineById(assessment.subjectId) : undefined;
  const uploadedByUser = item.uploadedBy ? userRepository.getById(item.uploadedBy) : undefined;
  const linkedWorkOrder = item.linkedWorkOrderId ? workOrderRepository.getById(item.linkedWorkOrderId) : undefined;
  const linkedPart = item.linkedPartId ? partRepository.getById(item.linkedPartId) : undefined;
  const lifecycleState = evidenceLifecycleStateFor(item);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Evidence", href: "/evidence" }, { label: item.id }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{item.id} — {TYPE_LABEL[item.evidenceType] ?? item.evidenceType}</h1>
          <p className="ac-subtitle">{item.description}</p>
        </div>
        <div className="ac-flex ac-gap-2">
          <StatusBadge status={item.verificationStatus} />
          <StatusBadge status={lifecycleState === "VERIFIED" ? "VERIFIED" : "UNVERIFIED"} label={lifecycleState.replace(/_/g, " ")} />
        </div>
      </div>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Source</h2>
        <div className="ac-card">
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>Source label: <span className="ac-mono">{item.sourceLabel}</span></p>
          <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>Uploaded/Referenced: {new Date(item.uploadedOrReferencedAt).toLocaleString()}</p>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Uploaded by: {uploadedByUser ? uploadedByUser.name : "Insufficient source data."}</p>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Linked Records</h2>
        <div className="ac-card">
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>
            Assessment: {assessment ? <Link href={`/assessments/${assessment.id}`} className="ac-mono">{assessment.id}</Link> : "Insufficient source data."}
          </p>
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>
            Aircraft/Engine: {subjectAircraft ? <Link href={`/aircraft/${subjectAircraft.id}`} className="ac-mono">{currentRegistration(subjectAircraft)}</Link> : subjectEngine ? <Link href={`/engines/${subjectEngine.id}`} className="ac-mono">{subjectEngine.serialNumber}</Link> : "Insufficient source data."}
          </p>
          <p className="ac-text-sm" style={{ margin: "0 0 4px" }}>
            Work Order: {linkedWorkOrder ? <Link href={`/maintenance/work-orders/${linkedWorkOrder.id}`} className="ac-mono">{linkedWorkOrder.workOrderNumber}</Link> : "Insufficient source data. — this evidence record is not yet linked to a work order."}
          </p>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Part: {linkedPart ? <Link href={`/maintenance/parts/${linkedPart.id}`} className="ac-mono">{linkedPart.partNumber}</Link> : "Insufficient source data. — this evidence record is not yet linked to a part."}
          </p>
        </div>
      </section>

      <section className="ac-section">
        <h2 className="ac-h2" style={{ marginBottom: 10 }}>Document Processing</h2>
        <div className="ac-card">
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Document processing unavailable — source data not extracted. This record is tracked by its source label and verification status only; no OCR or automated content extraction has run against it.
          </p>
        </div>
      </section>
    </div>
  );
}
