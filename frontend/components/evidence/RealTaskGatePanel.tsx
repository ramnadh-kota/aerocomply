"use client";

// REAL-mode per-task Evidence + Inspection panel. Wired only where a real
// task_id exists (work order detail page, REAL mode) since Evidence and
// InspectionRequirement both require a real task FK.
//
// IMPORTANT: this component never computes a combined
// CAN_COMPLETE/BLOCKED verdict. It shows each backend-owned signal
// (evidence status, inspection status) exactly as returned by the API.
// There is currently no unified completion-gate endpoint, so the two
// signals are displayed side by side with an explicit note rather than
// synthesized into one answer on the frontend.

import { useState } from "react";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { evidenceApi, type BackendEvidence } from "@/lib/api/evidence";
import { inspectionsApi, type BackendInspectionRequirement } from "@/lib/api/inspections";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

function ErrorNote({ error }: { error: NormalizedApiError | null }) {
  if (!error) return null;
  return (
    <p className="ac-text-sm" style={{ color: "var(--ac-status-critical, #b42318)", margin: "6px 0 0" }}>
      {error.message}
    </p>
  );
}

export function RealTaskGatePanel({ taskId }: { taskId: string }) {
  const { accessToken } = useSession();
  const [evidence, setEvidence] = useState<BackendEvidence | null>(null);
  const [inspection, setInspection] = useState<BackendInspectionRequirement | null>(null);
  const [evError, setEvError] = useState<NormalizedApiError | null>(null);
  const [inError, setInError] = useState<NormalizedApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function withToken<T>(fn: (token: string) => Promise<T>): Promise<T | null> {
    if (!accessToken) return null;
    setBusy(true);
    try {
      return await fn(accessToken);
    } finally {
      setBusy(false);
    }
  }

  const createEvidence = () =>
    withToken(async (token) => {
      setEvError(null);
      try {
        setEvidence(await evidenceApi.create(token, taskId));
      } catch (err) {
        setEvError(normalizeApiError(err));
      }
      return null;
    });

  const transitionEvidence = (target: string, rejectionReason?: string) =>
    withToken(async (token) => {
      if (!evidence) return null;
      setEvError(null);
      try {
        setEvidence(await evidenceApi.transition(token, evidence.id, target, rejectionReason));
      } catch (err) {
        setEvError(normalizeApiError(err));
      }
      return null;
    });

  const createInspection = (required: boolean) =>
    withToken(async (token) => {
      setInError(null);
      try {
        setInspection(await inspectionsApi.create(token, { task_id: taskId, required }));
      } catch (err) {
        setInError(normalizeApiError(err));
      }
      return null;
    });

  const transitionInspection = (target: string) =>
    withToken(async (token) => {
      if (!inspection) return null;
      setInError(null);
      try {
        setInspection(
          await inspectionsApi.transition(token, inspection.id, target, {
            inspectorUserId: undefined,
          })
        );
      } catch (err) {
        setInError(normalizeApiError(err));
      }
      return null;
    });

  return (
    <div className="ac-card" style={{ marginTop: 8, background: "var(--ac-bg-subtle, #fafafa)" }}>
      <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Completion signals (REAL data)</p>
      <p className="ac-text-sm ac-text-muted" style={{ marginTop: 0, marginBottom: 10 }}>
        Unified completion gate: not yet available in REAL mode — showing individual signals only.
      </p>

      <div className="ac-grid-2" style={{ gap: 12 }}>
        <div>
          <div className="ac-flex ac-justify-between ac-items-center">
            <span className="ac-text-sm" style={{ fontWeight: 600 }}>Evidence</span>
            {evidence && <StatusBadge {...genericStatusBadge(evidence.status)} />}
          </div>
          <ErrorNote error={evError} />
          <div className="ac-flex ac-gap-2" style={{ marginTop: 6, flexWrap: "wrap" }}>
            {!evidence && (
              <button className="ac-btn ac-btn-sm" disabled={busy} onClick={createEvidence}>
                Create evidence record
              </button>
            )}
            {evidence?.status === "UPLOADED" && (
              <button className="ac-btn ac-btn-sm" disabled={busy} onClick={() => transitionEvidence("SUBMITTED")}>
                Submit
              </button>
            )}
            {evidence?.status === "SUBMITTED" && (
              <button className="ac-btn ac-btn-sm" disabled={busy} onClick={() => transitionEvidence("AWAITING_REVIEW")}>
                Send for review
              </button>
            )}
            {evidence?.status === "AWAITING_REVIEW" && (
              <>
                <button className="ac-btn ac-btn-sm ac-btn-primary" disabled={busy} onClick={() => transitionEvidence("ACCEPTED")}>
                  Accept
                </button>
                <button className="ac-btn ac-btn-sm" disabled={busy} onClick={() => transitionEvidence("REJECTED", "Rejected during REAL-mode review")}>
                  Reject
                </button>
              </>
            )}
            {evidence?.status === "REJECTED" && (
              <button className="ac-btn ac-btn-sm" disabled={busy} onClick={() => transitionEvidence("UPLOADED")}>
                Resubmit (re-upload)
              </button>
            )}
          </div>
        </div>

        <div>
          <div className="ac-flex ac-justify-between ac-items-center">
            <span className="ac-text-sm" style={{ fontWeight: 600 }}>Inspection {inspection ? (inspection.required ? "(RII)" : "(checklist)") : ""}</span>
            {inspection && <StatusBadge {...genericStatusBadge(inspection.status)} />}
          </div>
          <ErrorNote error={inError} />
          <div className="ac-flex ac-gap-2" style={{ marginTop: 6, flexWrap: "wrap" }}>
            {!inspection && (
              <>
                <button className="ac-btn ac-btn-sm" disabled={busy} onClick={() => createInspection(false)}>
                  Add checklist review
                </button>
                <button className="ac-btn ac-btn-sm" disabled={busy} onClick={() => createInspection(true)}>
                  Add RII (independent)
                </button>
              </>
            )}
            {inspection?.status === "PENDING" && (
              <>
                <button className="ac-btn ac-btn-sm ac-btn-primary" disabled={busy} onClick={() => transitionInspection("COMPLETED")}>
                  Complete (as me)
                </button>
                <button className="ac-btn ac-btn-sm" disabled={busy} onClick={() => transitionInspection("REJECTED")}>
                  Reject
                </button>
              </>
            )}
            {inspection?.status === "REJECTED" && (
              <button className="ac-btn ac-btn-sm" disabled={busy} onClick={() => transitionInspection("PENDING")}>
                Reopen
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
