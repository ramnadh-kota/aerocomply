import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { integrationsByCategory, type Integration, type IntegrationStatus } from "@/lib/mock/integrations";
import { COMPANY_NAME } from "@/lib/brand";

// M0.5 — Integration Hub. A dedicated, prominent surface for the ingestion
// architecture KOTA'S AEROSPACE is designed around: pulling data from a
// customer's existing MRO, ERP, procurement, HR, regulatory, and aircraft
// data systems rather than replacing them. Zero real integrations are
// connected in this prototype — every entry is honestly NOT_CONFIGURED.
// See lib/mock/integrations.ts for the full honesty invariant. The compact
// summary on Settings > Integrations links here instead of duplicating this
// inventory.

const STATUS_BADGE: Record<IntegrationStatus, { status: Parameters<typeof StatusBadge>[0]["status"]; label: string }> = {
  CONNECTED: { status: "COMPLIANT", label: "Connected" },
  NOT_CONFIGURED: { status: "UNKNOWN", label: "Not Configured" },
  ERROR: { status: "NON_COMPLIANT", label: "Error" },
  SYNCING: { status: "REVIEW_REQUIRED", label: "Syncing" },
};

const SYNC_METHOD_NOTES: { method: string; note: string }[] = [
  { method: "REST", note: "Live API calls against the source system, either direction." },
  { method: "Webhook", note: "Source system pushes events to KOTA'S AEROSPACE as they happen." },
  { method: "CSV", note: "Batch file upload or drop-folder ingestion for systems without a modern API." },
  { method: "SFTP", note: "Scheduled batch file transfer over SFTP." },
  { method: "Scheduled", note: "Periodic pull on a fixed interval (e.g. regulatory feeds)." },
  { method: "Event-driven", note: "Streaming ingestion triggered by source-system events (e.g. onboard telemetry)." },
];

export default function IntegrationsPage() {
  const groups = integrationsByCategory();
  const total = groups.reduce((sum, g) => sum + g.items.length, 0);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Integration Hub" }]} />
      <h1 className="ac-h1">Integration Hub</h1>
      <p className="ac-subtitle" style={{ marginBottom: 20 }}>
        Where {COMPANY_NAME} connects to the systems you already run.
      </p>

      <div className="ac-card" style={{ marginBottom: 20, background: "var(--ac-surface-2)" }}>
        <p className="ac-text-sm" style={{ margin: 0, marginBottom: 8 }}>
          {COMPANY_NAME} is designed as an intelligence overlay: it ingests data from your existing MRO, ERP,
          procurement, HR, regulatory, and aircraft data systems rather than asking you to re-enter it into a second
          system of record.
        </p>
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          <strong>No integrations are connected in this demo environment.</strong> Every entry below is a designed
          ingestion point, not a live connection — this page shows the architecture, honestly labeled, not a
          marketplace of working integrations.
        </p>
      </div>

      <div className="ac-kpi-grid" style={{ marginBottom: 20 }}>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Designed Ingestion Points</p>
          <p className="ac-kpi-value">{total}</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Connected</p>
          <p className="ac-kpi-value">0</p>
        </div>
        <div className="ac-kpi-card">
          <p className="ac-kpi-label">Categories</p>
          <p className="ac-kpi-value">{groups.length}</p>
        </div>
      </div>

      {groups.map((g) => (
        <section key={g.category} className="ac-section" style={{ marginBottom: 16 }}>
          <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>{g.category}</h2>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead>
                <tr>
                  <th>Integration</th>
                  <th>Status</th>
                  <th>Sync Method</th>
                  <th>Last Sync</th>
                  <th>Records</th>
                </tr>
              </thead>
              <tbody>
                {g.items.map((item) => (
                  <IntegrationRow key={item.id} item={item} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <section className="ac-section">
        <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>Architecture Notes</h2>
        <div className="ac-card">
          <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 10 }}>
            Each integration is modeled against one of six sync methods, chosen per source system&apos;s own
            capabilities rather than forcing a single pattern:
          </p>
          <div>
            {SYNC_METHOD_NOTES.map((s, idx) => (
              <div
                key={s.method}
                className="ac-flex"
                style={{
                  gap: 12,
                  padding: "8px 0",
                  borderTop: idx > 0 ? "1px solid var(--ac-border)" : undefined,
                  alignItems: "baseline",
                }}
              >
                <span className="ac-mono ac-text-sm" style={{ minWidth: 100, fontWeight: 600 }}>{s.method}</span>
                <span className="ac-text-sm ac-text-muted">{s.note}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="ac-card" style={{ marginTop: 20 }}>
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          Looking for authentication and infrastructure status specifically? See{" "}
          <Link href="/settings">Settings → Integrations</Link> for the compact summary, including the one backend
          integration (JWT authentication) that has a real, tested implementation not currently running in this
          environment.
        </p>
      </div>
    </div>
  );
}

function IntegrationRow({ item }: { item: Integration }) {
  const badge = STATUS_BADGE[item.status];
  return (
    <tr>
      <td>
        <span>{item.name}</span>
        <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0 0", maxWidth: 480 }}>
          {item.implementationNote ?? item.description}
        </p>
      </td>
      <td>
        <StatusBadge status={badge.status} label={item.implementationNote ? "Backend Implemented — Not Running" : badge.label} />
      </td>
      <td className="ac-mono ac-text-sm">{item.syncMethod ?? "—"}</td>
      <td className="ac-text-sm">{item.lastSync ?? "Never"}</td>
      <td className="ac-text-sm">{item.recordCount ?? "—"}</td>
    </tr>
  );
}
