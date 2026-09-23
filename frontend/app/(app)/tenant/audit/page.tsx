"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { tenantApi } from "@/lib/api/tenant";
import type { AuditEventResponse } from "@/lib/api/audit";
import { DEMO_TENANT_AUDIT_EVENTS } from "@/lib/demo/demoTenant";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function TenantAuditPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [events, setEvents] = useState<AuditEventResponse[]>(
    isDemo ? DEMO_TENANT_AUDIT_EVENTS : []
  );
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [search, setSearch] = useState("");
  const [selectedEvent, setSelectedEvent] = useState<AuditEventResponse | null>(null);

  useEffect(() => {
    if (isDemo) {
      setEvents(DEMO_TENANT_AUDIT_EVENTS);
      setLoading(false);
      return;
    }

    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    tenantApi
      .listAuditEvents(accessToken, { limit: 100 })
      .then(setEvents)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [isDemo, isAuthenticated, accessToken]);

  const filteredEvents = events.filter((e) => {
    const q = search.toLowerCase();
    return (
      e.action.toLowerCase().includes(q) ||
      e.entity_type.toLowerCase().includes(q) ||
      (e.entity_id ?? "").toLowerCase().includes(q)
    );
  });

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Audit Trail" },
        ]}
        eyebrow="GOVERNANCE & COMPLIANCE"
        title="Organization Audit Log"
        subtitle="Immutable ledger of administrative actions, personnel role changes, and operational configuration events."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/compliance" className="ac-btn">
              AeroComply Register →
            </Link>
          </div>
        }
      />

      <div style={{ marginBottom: 16 }}>
        {isDemo ? (
          <div
            style={{
              padding: "10px 16px",
              background: "rgba(59, 130, 246, 0.08)",
              border: "1px solid rgba(59, 130, 246, 0.25)",
              borderRadius: 6,
              fontSize: 13,
            }}
          >
            <strong>DEMO MODE</strong> · Showing synthetic audit event trail for KOTA Aerospace Demo Operations.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={filteredEvents.length === 0}
            emptyMessage="No audit records on file for your organization."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      <div
        className="ac-card"
        style={{
          padding: 12,
          marginBottom: 16,
          display: "flex",
          gap: 12,
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <input
          type="text"
          className="ac-input"
          placeholder="Filter by action name, entity type, or target ID..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: "100%", maxWidth: 420 }}
        />
        <span className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>
          {filteredEvents.length} Recorded Events
        </span>
      </div>

      <div className="ac-card" style={{ padding: 0, marginBottom: 24 }}>
        <div style={{ overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Action Name</th>
                <th>Entity Class</th>
                <th>Entity Target</th>
                <th>Actor User</th>
                <th style={{ textAlign: "right" }}>Payload</th>
              </tr>
            </thead>
            <tbody>
              {filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "32px 16px", opacity: 0.7 }}>
                    No audit events found.
                  </td>
                </tr>
              ) : (
                filteredEvents.map((evt) => (
                  <tr key={evt.id}>
                    <td className="ac-mono" style={{ fontSize: 12 }}>
                      {new Date(evt.created_at).toLocaleString()}
                    </td>
                    <td>
                      <span
                        className="ac-mono"
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          padding: "2px 6px",
                          borderRadius: 4,
                          background: "var(--bg-subtle, rgba(255, 255, 255, 0.06))",
                          border: "1px solid var(--border-color, #27272a)",
                        }}
                      >
                        {evt.action}
                      </span>
                    </td>
                    <td style={{ fontWeight: 500, fontSize: 13 }}>
                      {evt.entity_type}
                    </td>
                    <td className="ac-mono" style={{ fontSize: 11, opacity: 0.7 }}>
                      {evt.entity_id ? evt.entity_id.slice(0, 13) + "..." : "—"}
                    </td>
                    <td className="ac-mono" style={{ fontSize: 11, opacity: 0.7 }}>
                      {evt.user_id ? evt.user_id.slice(0, 8) + "..." : "SYSTEM"}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      <button
                        type="button"
                        className="ac-btn"
                        style={{ fontSize: 11, padding: "2px 8px" }}
                        onClick={() => setSelectedEvent(evt)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Inspect Modal */}
      {selectedEvent && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.65)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
        >
          <div className="ac-card" style={{ maxWidth: 560, width: "90%", padding: 24 }}>
            <h3 className="ac-h3" style={{ marginBottom: 4 }}>
              Audit Event Payload
            </h3>
            <div className="ac-mono" style={{ fontSize: 12, opacity: 0.7, marginBottom: 16 }}>
              {selectedEvent.action} · {new Date(selectedEvent.created_at).toISOString()}
            </div>

            <pre
              style={{
                background: "var(--bg-card, #18181b)",
                border: "1px solid var(--border-color, #27272a)",
                borderRadius: 6,
                padding: 12,
                fontSize: 12,
                maxHeight: 240,
                overflowY: "auto",
              }}
            >
              {JSON.stringify(
                {
                  id: selectedEvent.id,
                  organization_id: selectedEvent.organization_id,
                  action: selectedEvent.action,
                  entity_type: selectedEvent.entity_type,
                  entity_id: selectedEvent.entity_id,
                  actor_user_id: selectedEvent.user_id,
                  event_metadata: selectedEvent.event_metadata,
                },
                null,
                2
              )}
            </pre>

            <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="ac-btn"
                onClick={() => setSelectedEvent(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
