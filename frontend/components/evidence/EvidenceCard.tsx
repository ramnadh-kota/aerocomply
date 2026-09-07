import type { Evidence } from "@/lib/mock/types";
import { StatusBadge } from "@/components/status/StatusBadge";

const TYPE_LABEL: Record<Evidence["evidenceType"], string> = {
  MAINTENANCE_RECORD: "Maintenance Record",
  OEM_DOCUMENT: "OEM Document",
  INSPECTION_RECORD: "Inspection Record",
  UPLOADED_DOCUMENT: "Uploaded File",
  STRUCTURED_RECORD_REFERENCE: "Structured Record Reference",
  REGULATORY_DOCUMENT: "Regulatory Document",
};

export function EvidenceCard({ evidence }: { evidence: Evidence }) {
  const shape = evidence.evidenceType === "UPLOADED_DOCUMENT" ? "File Upload" : "Structured Record Reference";

  return (
    <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6 }}>
        <span className="ac-eyebrow">{TYPE_LABEL[evidence.evidenceType]}</span>
        <StatusBadge status={evidence.verificationStatus} />
      </div>
      <p style={{ margin: "0 0 4px", fontWeight: 600, fontSize: 13 }} className="ac-mono">
        {evidence.sourceLabel}
      </p>
      <p className="ac-text-sm ac-text-secondary" style={{ margin: "0 0 8px" }}>
        {evidence.description}
      </p>
      <div className="ac-flex ac-justify-between ac-text-sm ac-text-muted">
        <span>{shape}</span>
        <span>{new Date(evidence.uploadedOrReferencedAt).toLocaleString()}</span>
      </div>
      {evidence.relatedConditionIds.length > 0 && (
        <p className="ac-text-sm ac-text-muted" style={{ marginTop: 6 }}>
          Related to {evidence.relatedConditionIds.length} condition{evidence.relatedConditionIds.length > 1 ? "s" : ""}
        </p>
      )}
    </div>
  );
}
