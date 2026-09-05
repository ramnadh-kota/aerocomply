// M8.6 — Document ingestion foundation.
//
// No OCR/document parser exists in this prototype. This file defines the
// domain vocabulary a future ingestion pipeline would need so evidence
// upload UI and the Evidence model already speak the right language — it
// does NOT simulate extraction results. Every call site must render the
// standard unavailable message below rather than inventing parsed content.

export type SupportedDocumentType =
  | "WORK_ORDER_DOCUMENT"
  | "TASK_CARD"
  | "INSPECTION_REPORT"
  | "CERTIFICATE_8130_3"
  | "CERTIFICATE_EASA_FORM_1"
  | "AD_COMPLIANCE_RECORD"
  | "SB_COMPLIANCE_RECORD"
  | "CALIBRATION_CERTIFICATE"
  | "TRAINING_AUTHORIZATION_RECORD";

export const DOCUMENT_PROCESSING_UNAVAILABLE_MESSAGE =
  "Document processing unavailable — source data not extracted.";

export interface DocumentIngestionResult {
  documentType: SupportedDocumentType;
  status: "UNAVAILABLE";
  message: string;
}

/** Placeholder ingestion entry point. Always returns UNAVAILABLE — there is
 * no OCR/parser wired up. Exists so future ingestion code has one function
 * to replace rather than a UI that fabricates results. */
export function ingestDocument(documentType: SupportedDocumentType): DocumentIngestionResult {
  return { documentType, status: "UNAVAILABLE", message: DOCUMENT_PROCESSING_UNAVAILABLE_MESSAGE };
}
