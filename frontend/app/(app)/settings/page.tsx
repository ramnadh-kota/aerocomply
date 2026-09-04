"use client";

import { useState, type ReactNode } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { organizations } from "@/lib/mock/organizations";
import { roles, users } from "@/lib/mock/roles";
import { regulatoryAuthorities, regulatoryDocuments } from "@/lib/mock/regulations";
import { getCurrentUser } from "@/lib/domain/currentUser";
import { TAT_AT_RISK_WINDOW_DAYS, DUE_SOON_DAYS } from "@/lib/mock/ai/analytics";
import { COMPANY_NAME, AI_NAME, AI_DESCRIPTION, AI_DEMO_DATA_FOOTER } from "@/lib/brand";

// M0.5 — Settings. There is no persistence layer in this prototype (no
// backend settings table, no auth-scoped tenant config), so this screen
// does two things honestly rather than fabricating a "Save" flow:
//   1. Surfaces REAL configuration that already exists elsewhere in the
//      mock domain (organizations, roles/users, regulatory authorities,
//      the canonical TAT/maintenance-due thresholds in analytics.ts) as
//      read-only "current configuration".
//   2. Presents inert preference controls (AI toggle, notification
//      toggles) clearly labeled as non-persisted preview UI, and
//      integrations as NOT CONFIGURED — never implying a live backend
//      connection that does not exist (see lib/apiClient.ts, a stub with
//      no wired settings/integration endpoints).

const TABS = [
  "General",
  "MRO Configuration",
  "Compliance",
  `${AI_NAME}`,
  "Notifications",
  "Security",
  "Integrations",
] as const;
type Tab = (typeof TABS)[number];

const NOTIFICATION_TOGGLES = [
  { key: "aog", label: "AOG Alerts", description: "Aircraft grounded with an open HIGH/CRITICAL defect." },
  { key: "tat", label: "TAT Alerts", description: "Work orders classified AT RISK or DELAYED by turnaround-time tracking." },
  { key: "overdue", label: "Overdue Maintenance", description: "Maintenance tasks past their due date." },
  { key: "evidence", label: "Evidence Rejection", description: "Submitted evidence records rejected by review." },
  { key: "inspection", label: "Inspection Requirements", description: "Work packages ready for or awaiting inspection." },
  { key: "regulatory", label: "Regulatory Updates", description: "Newly published AD/SB/AMC/Notice documents." },
  { key: "procurement", label: "Procurement Alerts", description: "Parts shortages blocking work order material readiness." },
] as const;

const INTEGRATION_GROUPS: { group: string; items: string[] }[] = [
  { group: "Regulatory Data Providers", items: ["FAA Dynamic Regulatory System", "EASA ADs & SIBs Feed", "UK CAA Mandate Feed", "DGCA CAR Notices Feed", "CASA AD Feed"] },
  { group: "Storage", items: ["Document / Evidence Storage (S3-compatible)"] },
  { group: "Authentication", items: ["SSO / SAML Identity Provider"] },
  { group: "Email", items: ["Outbound Email (SMTP / API)"] },
  { group: "Messaging", items: ["Slack / Teams Alerts"] },
];

export default function SettingsPage() {
  const [tab, setTab] = useState<Tab>("General");
  const current = getCurrentUser();
  const org = current?.organization ?? organizations[0];

  const [notifPrefs, setNotifPrefs] = useState<Record<string, boolean>>(
    Object.fromEntries(NOTIFICATION_TOGGLES.map((n) => [n.key, true]))
  );
  const [aiEnabled, setAiEnabled] = useState(true);
  const [reasoningMode, setReasoningMode] = useState<"balanced" | "concise" | "thorough">("balanced");

  const authoritiesInMockData = regulatoryAuthorities.map((a) => ({
    ...a,
    docCount: regulatoryDocuments.filter((d) => d.regulatoryAuthorityId === a.id).length,
  }));

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Settings" }]} />
      <h1 className="ac-h1">Settings</h1>
      <p className="ac-subtitle" style={{ marginBottom: 20 }}>
        Account, MRO configuration, compliance coverage, {AI_NAME}, notifications, security, and integrations.
      </p>

      <div className="ac-card" style={{ marginBottom: 20, background: "var(--ac-surface-2)" }}>
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          This is a read-only prototype. There is no settings persistence layer yet — values below are either drawn live
          from existing {COMPANY_NAME} mock data, or are inert preview controls clearly labeled as such. Nothing on this
          page is saved to a backend.
        </p>
      </div>

      <div className="ac-tabs">
        {TABS.map((t) => (
          <button key={t} className={`ac-tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)} type="button">
            {t}
          </button>
        ))}
      </div>

      {tab === "General" && (
        <section className="ac-section">
          <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>General</h2>
          <div className="ac-card">
            <div>
              <Row label="Organization" value={org?.name ?? "Unknown"} />
              <Row label="Organization Type" value={org?.orgType ?? "Unknown"} />
              <Row label="Workspace" value={COMPANY_NAME} note="DEMO DATA — single-workspace prototype, no multi-workspace model exists yet." />
              <Row label="Timezone" value="Asia/Kolkata (UTC+05:30)" note="DEMO DATA — not read from a user/org preference record." />
              <Row label="Date Format" value="YYYY-MM-DD" note="DEMO DATA — matches the format used throughout mock data." />
              <Row label="Currency" value="INR (₹)" note="DEMO DATA — matches lib/mock/finance.ts figures." />
            </div>
          </div>
        </section>
      )}

      {tab === "MRO Configuration" && (
        <section className="ac-section">
          <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>MRO Configuration</h2>
          <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 12 }}>
            Current configuration used by the canonical planning/TAT engines in{" "}
            <span className="ac-mono">lib/mock/ai/analytics.ts</span>. READ-ONLY PROTOTYPE — no admin UI exists yet to
            change these values; changing them would require editing that file.
          </p>
          <div className="ac-card">
            <div>
              <Row label="TAT At-Risk Window" value={`${TAT_AT_RISK_WINDOW_DAYS} day(s)`} note="A work order with an open release blocker due within this window is classified AT RISK." />
              <Row label="TAT Delayed" value="Due date passed" note="Any open work order past its due date is classified DELAYED, regardless of blockers." />
              <Row label="Maintenance Due Soon Window" value={`${DUE_SOON_DAYS} day(s)`} note="Scheduled maintenance due within this window is classified DUE SOON." />
              <Row label="AOG Determination" value="Open HIGH/CRITICAL defect" note="Aircraft operational status becomes AOG when a serious open defect exists — not a numeric threshold." />
              <Row label="Evidence Policy" value="Reviewer approval required" note="See lib/mock/evidenceRecords.ts — evidence status is VERIFIED/UNVERIFIED/REJECTED by reviewer action, no auto-approval." />
              <Row label="Inspection Policy" value="Work package must reach READY_FOR_INSPECTION" note="See lib/mock/ai/analytics.ts work package status mapping." />
            </div>
          </div>
        </section>
      )}

      {tab === "Compliance" && (
        <section className="ac-section">
          <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>Compliance</h2>
          <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 12 }}>
            Regulatory authorities represented in this prototype&apos;s mock data (<span className="ac-mono">lib/mock/regulations.ts</span>).
            All documents below are fictional demo records, not real, current, or legally binding requirements.
          </p>
          <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
            <table className="ac-table">
              <thead>
                <tr><th>Authority</th><th>Code</th><th>Mock Documents</th><th>Coverage</th></tr>
              </thead>
              <tbody>
                {authoritiesInMockData.map((a) => (
                  <tr key={a.id}>
                    <td>{a.name}</td>
                    <td className="ac-mono">{a.code}</td>
                    <td>{a.docCount}</td>
                    <td>
                      {a.docCount > 0 ? (
                        <StatusBadge status="ACTIVE" label="Demo Records Present" />
                      ) : (
                        <StatusBadge status="UNKNOWN" label="No Records" />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {tab === AI_NAME && (
        <section className="ac-section">
          <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>{AI_NAME}</h2>
          <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 12 }}>
            {AI_DESCRIPTION}. Preview — not yet persisted. These controls do not change {AI_NAME}&apos;s behavior; they
            illustrate the settings surface a real configuration API would back.
          </p>
          <div className="ac-card">
            <div>
              <Row
                label={`${AI_NAME} Enabled`}
                value={
                  <label className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                    <input type="checkbox" checked={aiEnabled} onChange={(e) => setAiEnabled(e.target.checked)} />
                    <span className="ac-text-sm">{aiEnabled ? "Enabled" : "Disabled"}</span>
                  </label>
                }
                note="Preview toggle — the Ask Lisa console remains available regardless of this setting."
              />
              <Row
                label="Reasoning Mode"
                value={
                  <select
                    className="ac-input"
                    value={reasoningMode}
                    onChange={(e) => setReasoningMode(e.target.value as typeof reasoningMode)}
                    style={{ maxWidth: 220 }}
                  >
                    <option value="concise">Concise</option>
                    <option value="balanced">Balanced</option>
                    <option value="thorough">Thorough</option>
                  </select>
                }
                note="Preview only — the underlying answer engine (lib/mock/ai/engine.ts) does not vary by this setting yet."
              />
            </div>
          </div>
          <div className="ac-card" style={{ marginTop: 12 }}>
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>{AI_DEMO_DATA_FOOTER}</p>
          </div>
        </section>
      )}

      {tab === "Notifications" && (
        <section className="ac-section">
          <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>Notifications</h2>
          <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 12 }}>
            Preview — not yet persisted. No notification delivery system exists in this prototype (no email/push
            backend is wired up); these toggles illustrate the intended preference surface only.
          </p>
          <div className="ac-card">
            {NOTIFICATION_TOGGLES.map((n, idx) => (
              <div
                key={n.key}
                className="ac-flex"
                style={{
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "10px 0",
                  borderTop: idx > 0 ? "1px solid var(--ac-border)" : undefined,
                }}
              >
                <div>
                  <p style={{ margin: 0, fontWeight: 500 }}>{n.label}</p>
                  <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>{n.description}</p>
                </div>
                <label className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
                  <input
                    type="checkbox"
                    checked={notifPrefs[n.key]}
                    onChange={(e) => setNotifPrefs((prev) => ({ ...prev, [n.key]: e.target.checked }))}
                  />
                  <span className="ac-text-sm">{notifPrefs[n.key] ? "On" : "Off"}</span>
                </label>
              </div>
            ))}
          </div>
        </section>
      )}

      {tab === "Security" && (
        <section className="ac-section">
          <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>Security</h2>
          <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 12 }}>
            This prototype has no real authentication or server-side permission enforcement (see{" "}
            <span className="ac-mono">lib/mock/roles.ts</span>) — the summary below reflects the mock RBAC model only.
          </p>
          <div className="ac-kpi-grid" style={{ marginBottom: 16 }}>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Roles Defined</p>
              <p className="ac-kpi-value">{roles.length}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">User Accounts</p>
              <p className="ac-kpi-value">{users.length}</p>
            </div>
            <div className="ac-kpi-card">
              <p className="ac-kpi-label">Active Sessions</p>
              <p className="ac-kpi-value">1</p>
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Single fixed demo identity — no real session tracking.</p>
            </div>
          </div>
          <div className="ac-card">
            <p className="ac-text-sm" style={{ marginBottom: 4 }}>
              Signed in as (demo identity): <strong>{current?.user.name ?? "Unknown"}</strong> —{" "}
              {current?.role?.name ?? "No role"}
            </p>
            <div className="ac-flex ac-gap-2" style={{ marginTop: 10 }}>
              <Link href="/organization/roles" className="ac-btn">Manage Roles</Link>
              <Link href="/organization/users" className="ac-btn">Manage Users</Link>
            </div>
          </div>
        </section>
      )}

      {tab === "Integrations" && (
        <section className="ac-section">
          <h2 className="ac-eyebrow" style={{ marginBottom: 10 }}>Integrations</h2>
          <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 12 }}>
            No external integration is wired to a live backend in this prototype (<span className="ac-mono">lib/apiClient.ts</span>{" "}
            has no connected settings/integration endpoints). Every item below is NOT CONFIGURED.
          </p>
          {INTEGRATION_GROUPS.map((g) => (
            <div key={g.group} className="ac-card" style={{ marginBottom: 12 }}>
              <p className="ac-text-sm" style={{ fontWeight: 600, marginBottom: 8 }}>{g.group}</p>
              {g.items.map((item, idx) => (
                <div
                  key={item}
                  className="ac-flex"
                  style={{ justifyContent: "space-between", alignItems: "center", padding: "6px 0", borderTop: idx > 0 ? "1px solid var(--ac-border)" : undefined }}
                >
                  <span className="ac-text-sm">{item}</span>
                  <StatusBadge status="UNKNOWN" label="Not Configured" />
                </div>
              ))}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

function Row({ label, value, note }: { label: string; value: ReactNode; note?: string }) {
  return (
    <div className="ac-flex" style={{ justifyContent: "space-between", alignItems: "flex-start", padding: "10px 0", borderTop: "1px solid var(--ac-border)", gap: 16 }}>
      <div style={{ minWidth: 180 }}>
        <p style={{ margin: 0, fontWeight: 500 }}>{label}</p>
        {note && <p className="ac-text-sm ac-text-muted" style={{ margin: 0, maxWidth: 420 }}>{note}</p>}
      </div>
      <div className="ac-text-sm" style={{ textAlign: "right" }}>{value}</div>
    </div>
  );
}
