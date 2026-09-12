"use client";

// REAL-mode release-readiness panel for a work order. Reads
// GET /work-orders/{id}/release-readiness (backend/app/api/v1/release_readiness.py)
// and renders exactly what the backend returns — READY/BLOCKED status plus,
// for each blocker, its category, description, and related_record_id. This
// panel never computes readiness itself; it is presentation-only over the
// backend's own aggregation (see release_readiness_service.py for the three
// blocker categories currently implemented: EVIDENCE, INSPECTION,
// TASK_EXECUTION).

import { useCallback, useEffect, useState } from "react";
import { StatusBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { releaseReadinessApi, type BackendReleaseReadiness } from "@/lib/api/release-readiness";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

const CATEGORY_LABEL: Record<string, string> = {
  EVIDENCE: "Evidence",
  INSPECTION: "Inspection",
  TASK_EXECUTION: "Task Execution",
};

export function RealReleaseReadinessPanel({ workOrderId }: { workOrderId: string }) {
  const { accessToken, isAuthenticated } = useSession();
  const [readiness, setReadiness] = useState<BackendReleaseReadiness | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const load = useCallback(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    releaseReadinessApi
      .getForWorkOrder(accessToken, workOrderId)
      .then(setReadiness)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [accessToken, isAuthenticated, workOrderId]);

  useEffect(() => {
    load();
  }, [load]);

  if (!isAuthenticated) return null;

  return (
    <div className="ac-card" style={{ marginTop: 8 }}>
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 8 }}>
        <p className="ac-eyebrow" style={{ margin: 0 }}>Release Readiness (REAL data)</p>
        <button className="ac-btn ac-btn-sm" disabled={loading} onClick={load}>
          Refresh
        </button>
      </div>

      {loading && <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Loading readiness…</p>}
      {error && (
        <p className="ac-text-sm" style={{ color: "var(--ac-status-critical, #b42318)", margin: 0 }}>
          {error.message}
        </p>
      )}

      {!loading && !error && readiness && (
        <>
          <div className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 10 }}>
            <StatusBadge
              status={readiness.status === "READY" ? "COMPLIANT" : readiness.status === "BLOCKED" ? "NON_COMPLIANT" : "INSUFFICIENT_DATA"}
              label={readiness.status}
            />
            <span className="ac-text-sm ac-text-muted">
              {readiness.blockers.length} blocker{readiness.blockers.length === 1 ? "" : "s"}
            </span>
          </div>

          {readiness.blockers.length > 0 && (
            <ul style={{ margin: "0 0 10px", paddingLeft: 18 }}>
              {readiness.blockers.map((b, i) => (
                <li key={i} className="ac-text-sm" style={{ marginBottom: 6 }}>
                  <strong>{CATEGORY_LABEL[b.category] ?? b.category}</strong>: {b.description}{" "}
                  <span className="ac-text-muted ac-mono" style={{ fontSize: 12 }}>({b.related_record_id})</span>
                </li>
              ))}
            </ul>
          )}

          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>{readiness.data_completeness}</p>
        </>
      )}
    </div>
  );
}
