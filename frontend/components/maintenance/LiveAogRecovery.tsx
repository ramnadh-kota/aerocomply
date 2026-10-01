"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { aogRecoveryApi, type BackendAogRecoveryStatus, type BackendCriticalPathStage } from "@/lib/api/aogRecovery";

const GLYPH: Record<BackendCriticalPathStage["status"], string> = { COMPLETE: "✓", ACTIVE: "●", BLOCKED: "⚠", WAITING: "○", UNKNOWN: "?" };
const COLOR: Record<BackendCriticalPathStage["status"], string> = {
  COMPLETE: "var(--ac-status-compliant)",
  ACTIVE: "var(--ac-accent)",
  BLOCKED: "var(--ac-status-non-compliant)",
  WAITING: "var(--ac-text-muted)",
  UNKNOWN: "var(--ac-status-review)",
};

type State = { kind: "loading" } | { kind: "error"; message: string } | { kind: "loaded"; status: BackendAogRecoveryStatus };

/**
 * AOG recovery for a live organization: everything on this page comes from GET /aog-events/recovery-status/{aircraft_id}
 * for the real aircraft id in the URL. No bundled sample aircraft, work orders or blockers are ever involved.
 */
export function LiveAogRecovery({ aircraftId }: { aircraftId: string }) {
  const { accessToken } = useSession();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    aogRecoveryApi
      .getRecoveryStatus(accessToken, aircraftId)
      .then((status) => !cancelled && setState({ kind: "loaded", status }))
      .catch((e: unknown) => !cancelled && setState({ kind: "error", message: e instanceof Error ? e.message : "request failed" }));
    return () => {
      cancelled = true;
    };
  }, [accessToken, aircraftId]);

  const crumbs = [{ label: "Dashboard", href: "/dashboard" }, { label: "Control Center", href: "/maintenance/control-center" }, { label: "AOG Recovery" }];

  if (state.kind === "loading") {
    return (
      <div>
        <Breadcrumbs items={crumbs} />
        <div className="ac-card" role="status" style={{ padding: 24 }}>Loading AOG recovery status…</div>
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div>
        <Breadcrumbs items={crumbs} />
        <div className="ac-card" role="alert" style={{ padding: 24 }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>AOG recovery status is not available for this aircraft ({state.message}).</p>
        </div>
      </div>
    );
  }

  const s = state.status;
  return (
    <div>
      <Breadcrumbs items={crumbs} />
      <div className="ac-flex ac-items-center" style={{ gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <h1 className="ac-h1" style={{ margin: 0 }}>AOG Recovery — {s.registration}</h1>
        <StatusBadge status={s.is_aog ? "NON_COMPLIANT" : "COMPLIANT"} label={s.is_aog ? "AOG" : "NOT AOG"} />
      </div>
      <div className="ac-card">
        <p className="ac-eyebrow" style={{ marginBottom: 8 }}>Live recovery status</p>
        {!s.is_aog && <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No active AOG event is recorded for this aircraft.</p>}
        {s.is_aog && (
          <div>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>
              Event {s.aog_event_id?.slice(0, 8)}… · {s.aog_status} · {s.severity}
              {s.work_order_id && <> · Work Order <span className="ac-mono">{s.work_order_id.slice(0, 8)}…</span></>}
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 4px" }}>
              Release Readiness: {s.release_readiness_status ?? "N/A"} · TAT: {s.tat_status ?? "N/A"}
              {s.tat_reason && ` (${s.tat_reason})`}
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 8px" }}>
              Technician Authorization: {s.technician_authorization} · ETA: {s.eta} · Compliance: {s.compliance_status}
            </p>
            {s.critical_path.length > 0 && (
              <div style={{ marginBottom: 12, overflowX: "auto" }}>
                <p className="ac-eyebrow" style={{ margin: "0 0 6px" }}>Critical Path</p>
                <table className="ac-table">
                  <thead><tr><th>Stage</th><th>Status</th><th>Reason</th><th>Record</th><th>Next Action</th></tr></thead>
                  <tbody>
                    {s.critical_path.map((stage) => (
                      <tr key={stage.stage}>
                        <td className="ac-mono ac-text-sm">{stage.stage.replace(/_/g, " ")}</td>
                        <td>
                          <span style={{ color: COLOR[stage.status], fontWeight: 700, marginRight: 6 }} aria-hidden>{GLYPH[stage.status]}</span>
                          <span className="ac-text-sm">{stage.status}</span>
                        </td>
                        <td className="ac-text-sm">{stage.reason}</td>
                        <td className="ac-mono ac-text-sm">{stage.record_type && stage.record_id ? `${stage.record_type} ${stage.record_id.slice(0, 8)}…` : "—"}</td>
                        <td className="ac-text-sm">{stage.next_action ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {s.blockers.length > 0 ? (
              <div style={{ overflowX: "auto" }}>
                <table className="ac-table">
                  <thead><tr><th>Category</th><th>Description</th><th>Who Should Act</th><th>Dependency</th></tr></thead>
                  <tbody>
                    {s.blockers.map((b, i) => (
                      <tr key={i} style={s.next_best_action === b ? { outline: "2px solid var(--ac-accent)" } : undefined}>
                        <td className="ac-mono ac-text-sm">{b.category}</td>
                        <td className="ac-text-sm">{b.description}</td>
                        <td className="ac-text-sm">{b.who_should_act}</td>
                        <td className="ac-text-sm">{b.dependency}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No blockers are recorded for this aircraft&apos;s active AOG event.</p>
            )}
            {s.next_best_action && (
              <p className="ac-text-sm" style={{ marginTop: 8 }}>
                <strong>Next best action:</strong> {s.next_best_action.dependency} ({s.next_best_action.who_should_act})
              </p>
            )}
          </div>
        )}
        <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8, marginBottom: 0 }}>{s.data_completeness}</p>
      </div>
    </div>
  );
}
