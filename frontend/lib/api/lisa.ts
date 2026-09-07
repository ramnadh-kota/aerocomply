// Typed REAL-mode client for the backend Lisa agent endpoint
// (backend/app/api/v1/lisa.py). organization_id is never sent by the
// client — the backend derives it from the authenticated JWT, exactly like
// every other REAL-mode client in this directory.

import { apiRequest } from "@/lib/apiClient";

export interface LisaAskRequest {
  question: string;
  conversation_history?: string[];
  current_entity?: string;
}

export interface LisaAiButton {
  label: string;
  href: string;
}

// Field names mirror frontend/lib/mock/ai/engine.ts::AiResponse so
// AIResponseView can render both sources through the same component.
export interface LisaAskResponse {
  id: string;
  question: string;
  headline: string;
  narrative: string[];
  priority?: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | null;
  whatIFound: string[];
  whyItMatters?: string | null;
  recommendedNextStep?: string | null;
  dependencies: string[];
  whoShouldAct?: string | null;
  relatedRecords: LisaAiButton[];
  confidenceState: "CONFIRMED" | "PARTIAL_DATA" | "UNKNOWN" | "NOT_CONFIGURED";
  actionCategory:
    | "INFORMATION"
    | "RECOMMENDATION"
    | "NAVIGATION"
    | "DRAFT"
    | "USER_APPROVAL_REQUIRED"
    | "SAFETY_RESTRICTED";
  source: "AI_AGENT";
}

export const lisaApi = {
  ask: (accessToken: string, payload: LisaAskRequest) =>
    apiRequest<LisaAskResponse>("/lisa/ask", { method: "POST", body: payload, accessToken }),
};
