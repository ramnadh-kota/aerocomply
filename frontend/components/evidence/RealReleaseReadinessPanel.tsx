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
import { useSession } from "@/lib/auth/SessionContext";
import { releaseReadinessApi, type BackendReleaseReadiness } from "@/lib/api/release-readiness";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { ReadinessIndicator, type ReadinessBlocker } from "@/components/readiness/ReadinessIndicator";

const CATEGORY_LABEL: Record<string, string> = {
  EVIDENCE: "Evidence",
  INSPECTION: "Inspection",
  TASK_EXECUTION: "Task Execution",
  MATERIAL: "Material",
  COMPLIANCE: "Compliance",
  FINDING: "Finding",
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
        <ReadinessIndicator
          status={readiness.status}
          footer={readiness.data_completeness}
          blockers={readiness.blockers.map((b, i): ReadinessBlocker => ({
            key: `${b.category}-${i}`,
            label: (
              <>
                <strong>{CATEGORY_LABEL[b.category] ?? b.category}</strong>: {b.description}{" "}
                {b.category !== "FINDING" && (
                  <span className="ac-text-muted ac-mono" style={{ fontSize: 12 }}>({b.related_record_id})</span>
                )}
              </>
            ),
            href: b.category === "FINDING" ? `/findings/${b.related_record_id}` : undefined,
          }))}
        />
      )}
    </div>
  );
}
