import Link from "next/link";
import { getFleetTatStatus } from "@/lib/mock/ai/analytics";
import type { TatStatus } from "@/lib/mock/ai/analytics";

// Fleet-wide TAT (turnaround time) tile — reads getFleetTatStatus(), the
// SAME canonical TAT engine already consumed by fleet/health, workspace and
// executive pages, and just tallies the counts. No new TAT classification
// logic lives here.

const TILES: { status: TatStatus; label: string; color: string }[] = [
  { status: "ON_TRACK", label: "On Track", color: "var(--ac-status-compliant)" },
  { status: "AT_RISK", label: "At Risk", color: "var(--ac-status-review)" },
  { status: "DELAYED", label: "Delayed", color: "var(--ac-status-non-compliant)" },
  { status: "UNKNOWN", label: "Unknown", color: "var(--ac-status-insufficient)" },
];

export function FleetTatSummary() {
  const rows = getFleetTatStatus();
  const counts: Record<TatStatus, number> = { ON_TRACK: 0, AT_RISK: 0, DELAYED: 0, UNKNOWN: 0 };
  for (const r of rows) counts[r.assessment.status]++;

  return (
    <div className="ac-card">
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
        <p className="ac-eyebrow" style={{ margin: 0 }}>Fleet TAT Status</p>
        <Link href="/maintenance/release-readiness" className="ac-text-sm">Release Readiness →</Link>
      </div>
      <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 10px" }}>
        {rows.length} open work order(s) evaluated for turnaround time · source: getFleetTatStatus()
      </p>
      <div className="ac-grid-4">
        {TILES.map((t) => (
          <Link key={t.status} href="/maintenance/work-orders" className="ac-kpi-card" style={{ display: "block", borderColor: t.color }}>
            <p className="ac-kpi-label">{t.label}</p>
            <p className="ac-kpi-value">{counts[t.status]}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
