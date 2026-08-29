import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Timeline } from "@/components/timeline/Timeline";
import { auditEvents } from "@/lib/mock/audit";

export default function AuditTrailPage() {
  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Audit Trail" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Audit Trail</h1>
          <p className="ac-subtitle">{auditEvents.length} events · append-only, matching the DB-level immutability trigger shipped in M0</p>
        </div>
      </div>

      <div className="ac-card">
        <Timeline
          entries={auditEvents.map((e) => ({
            id: e.id,
            date: new Date(e.timestamp).toLocaleString(),
            title: (
              <span>
                {e.action.replace(/_/g, " ").replace(/\./g, " — ")}
                <span className="ac-text-sm ac-text-muted"> · {e.objectType}</span>
              </span>
            ),
            detail: (
              <span>
                <strong>{e.actor}</strong> ({e.actorRole}) — {e.objectLabel}
                {e.previousState && e.newState && (
                  <span className="ac-mono ac-text-sm">
                    {" "}
                    · {e.previousState} → {e.newState}
                  </span>
                )}
                {e.reason && <div className="ac-text-sm ac-text-secondary" style={{ marginTop: 2 }}>Reason: {e.reason}</div>}
                {e.relatedAssessmentId && (
                  <div className="ac-text-sm" style={{ marginTop: 2 }}>
                    <Link href={`/assessments/${e.relatedAssessmentId}`} className="ac-mono">View assessment →</Link>
                  </div>
                )}
              </span>
            ),
          }))}
        />
      </div>
    </div>
  );
}
