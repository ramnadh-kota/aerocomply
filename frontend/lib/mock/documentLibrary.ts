// Document Library — pure read/aggregation layer over document-like records
// that already exist across the mock model. This is NOT the M8.6 ingestion
// placeholder (lib/domain/documents.ts, which simulates an OCR/parser
// pipeline status) and it is NOT object storage — no file content exists in
// this prototype. Every row here is a real record from an existing mock
// store, unified into one browsable shape so a document-style view can exist
// without fabricating anything. A category with zero real backing records is
// left empty rather than seeded with invented entries — the UI is expected
// to say so honestly.

import { regulatoryDocuments, getAuthorityById } from "./regulations";
import { evidence } from "./evidence";
import { evidenceRecords } from "./evidenceRecords";
import { partCertificates } from "./partTraceability";
import { getPartById } from "./parts";
import { getWorkOrderById } from "./workOrders";
import { vendors } from "./procurement";
import { getAircraftById, currentRegistration } from "./aircraft";
import { getAssessmentById } from "./assessments";

export type LibraryDocumentType =
  | "Maintenance Manual"
  | "Work Instruction"
  | "Regulatory Document"
  | "Certificate"
  | "Evidence"
  | "Inspection Record"
  | "Vendor Document"
  | "Compliance Record";

export type LibraryDocumentStatus =
  | "Published"
  | "Superseded"
  | "Withdrawn"
  | "Draft"
  | "Verified"
  | "Unverified"
  | "Missing"
  | "Reference Unknown"
  | "Accepted"
  | "Rejected"
  | "Submitted"
  | "On File";

export interface LibraryDocument {
  id: string;
  title: string;
  type: LibraryDocumentType;
  authority?: string;
  revision?: string;
  effectiveDate?: string;
  status: LibraryDocumentStatus;
  relatedAircraftId?: string;
  relatedWorkOrderId?: string;
  href: string;
}

const SOURCE_STATUS_LABEL: Record<string, LibraryDocumentStatus> = {
  PUBLISHED: "Published",
  SUPERSEDED: "Superseded",
  WITHDRAWN: "Withdrawn",
  DRAFT: "Draft",
};

const CERT_STATUS_LABEL: Record<string, LibraryDocumentStatus> = {
  PRESENT: "Verified",
  MISSING: "Missing",
  REFERENCE_UNKNOWN: "Reference Unknown",
  NOT_VERIFIED: "Unverified",
};

const EVIDENCE_RECORD_STATUS_LABEL: Record<string, LibraryDocumentStatus> = {
  ACCEPTED: "Accepted",
  REJECTED: "Rejected",
  SUBMITTED: "Submitted",
};

const ASSESSMENT_EVIDENCE_STATUS_LABEL: Record<string, LibraryDocumentStatus> = {
  VERIFIED: "Verified",
  UNVERIFIED: "Unverified",
};

/** Regulatory documents (AD/SB/AMC/Notice) — real records from regulations.ts. */
function regulatoryDocs(): LibraryDocument[] {
  return regulatoryDocuments.map((d) => {
    const authority = getAuthorityById(d.regulatoryAuthorityId);
    return {
      id: d.id,
      title: `${d.docNumber} — ${d.title}`,
      type: "Regulatory Document",
      authority: authority?.code,
      revision: d.revision,
      effectiveDate: d.effectiveDate,
      status: SOURCE_STATUS_LABEL[d.sourceStatus] ?? "Draft",
      href: `/regulations/${d.id}`,
    };
  });
}

/** Assessment-scoped evidence (evidence.ts) — structured record references and
 * uploaded documents attached to an ApplicabilityAssessment. */
function assessmentEvidenceDocs(): LibraryDocument[] {
  return evidence.map((e) => {
    const assessment = getAssessmentById(e.applicabilityAssessmentId);
    const relatedAircraftId = assessment?.subjectType === "AIRCRAFT" ? assessment.subjectId : undefined;
    return {
      id: e.id,
      title: e.sourceLabel,
      type: "Compliance Record" as LibraryDocumentType,
      effectiveDate: e.uploadedOrReferencedAt.slice(0, 10),
      status: ASSESSMENT_EVIDENCE_STATUS_LABEL[e.verificationStatus] ?? "Unverified",
      relatedAircraftId,
      href: `/evidence/${e.id}`,
    };
  });
}

/** Technician execution evidence (evidenceRecords.ts) — before/after/inspection
 * photos tied to a work order and maintenance task. Links to the work order's
 * planning detail page, since there is no standalone evidence-record view. */
function executionEvidenceDocs(): LibraryDocument[] {
  return evidenceRecords.map((e) => ({
    id: e.id,
    title: `${e.evidenceType.replace(/_/g, " ")} — ${e.fileName}`,
    type: "Evidence" as LibraryDocumentType,
    effectiveDate: e.capturedAt.slice(0, 10),
    status: EVIDENCE_RECORD_STATUS_LABEL[e.status] ?? "Submitted",
    relatedAircraftId: e.aircraftId,
    relatedWorkOrderId: e.workOrderId,
    href: `/maintenance/planning/${e.workOrderId}`,
  }));
}

/** Part certificates (partTraceability.ts) — FAA 8130-3 / EASA Form 1 / other
 * certificate records tracked per part. Only records that actually exist are
 * included; certificates known to be MISSING are still real facts (the
 * absence itself is data), so they are included with a Missing status. */
function partCertificateDocs(): LibraryDocument[] {
  return partCertificates.map((c) => {
    const part = getPartById(c.partId);
    return {
      id: c.id,
      title: c.certificateReference
        ? `${c.certificateType.replace(/_/g, " ")} — ${c.certificateReference}`
        : `${c.certificateType.replace(/_/g, " ")} — ${part?.description ?? c.partId}`,
      type: "Certificate" as LibraryDocumentType,
      authority: c.certificateIssuer ?? undefined,
      effectiveDate: c.certificateDate ?? undefined,
      status: CERT_STATUS_LABEL[c.verificationStatus] ?? "Unverified",
      relatedWorkOrderId: part?.workOrderId ?? undefined,
      href: `/maintenance/parts/${c.partId}`,
    };
  });
}

/** Vendor quality certifications (procurement.ts) — a vendor-level list of
 * certification labels (e.g. "AS9120"). Minimal metadata (no date/id per
 * certification in the source model), but real, named, sourced data — not
 * invented. Vendors with no certifications recorded contribute nothing. */
function vendorCertificationDocs(): LibraryDocument[] {
  const docs: LibraryDocument[] = [];
  for (const v of vendors) {
    if (!v.certifications || v.certifications.length === 0) continue;
    for (const cert of v.certifications) {
      docs.push({
        id: `vendor-cert-${v.id}-${cert.replace(/\s+/g, "-").toLowerCase()}`,
        title: `${cert} — ${v.name}`,
        type: "Vendor Document",
        authority: v.name,
        status: "On File",
        href: `/procurement/vendors/${v.id}`,
      });
    }
  }
  return docs;
}

export function getAllDocuments(): LibraryDocument[] {
  return [
    ...regulatoryDocs(),
    ...assessmentEvidenceDocs(),
    ...executionEvidenceDocs(),
    ...partCertificateDocs(),
    ...vendorCertificationDocs(),
  ];
}

/** Categories this prototype's mock model has zero backing records for.
 * Rendered honestly by the UI instead of being silently hidden or faked. */
export const EMPTY_DOCUMENT_CATEGORIES: { type: LibraryDocumentType; reason: string }[] = [
  { type: "Maintenance Manual", reason: "No maintenance manual records exist in the current mock dataset." },
  { type: "Work Instruction", reason: "No work instruction documents exist in the current mock dataset." },
  { type: "Inspection Record", reason: "No standalone inspection record documents exist in the current mock dataset — inspection outcomes are tracked on Inspector Reviews and Work Orders instead." },
];

export function documentTypeOptions(): LibraryDocumentType[] {
  return [
    "Regulatory Document",
    "Compliance Record",
    "Evidence",
    "Certificate",
    "Vendor Document",
    "Maintenance Manual",
    "Work Instruction",
    "Inspection Record",
  ];
}

// re-export helpers the page needs for related-record display
export { getAircraftById, currentRegistration, getWorkOrderById };
