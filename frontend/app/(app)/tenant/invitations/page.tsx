"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { tenantApi, type TenantInvitation } from "@/lib/api/tenant";
import { DEMO_TENANT_INVITATIONS } from "@/lib/demo/demoTenant";
import { demoStore } from "@/lib/demo/demoStore";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

const ROLES = [
  { value: "MAINTENANCE_ENGINEER", label: "Maintenance Engineer" },
  { value: "CAMO_MANAGER", label: "CAMO Manager" },
  { value: "COMPLIANCE_MANAGER", label: "Compliance Manager" },
  { value: "QUALITY_MANAGER", label: "Quality Manager" },
  { value: "ORG_ADMIN", label: "Organization Administrator" },
  { value: "VIEWER", label: "Stakeholder / Viewer" },
];

export default function TenantInvitationsPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [invitations, setInvitations] = useState<TenantInvitation[]>(
    isDemo ? DEMO_TENANT_INVITATIONS : []
  );
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  // Invite Modal
  const [showModal, setShowModal] = useState(false);
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState(ROLES[0].value);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadInvitations = () => {
    if (isDemo) {
      setInvitations(demoStore.getInvitations());
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
      .listInvitations(accessToken)
      .then(setInvitations)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadInvitations();
    if (isDemo) {
      return demoStore.subscribe(() => {
        setInvitations(demoStore.getInvitations());
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemo, isAuthenticated, accessToken]);

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!email.trim() || !fullName.trim()) {
      setFormError("Email and full name are required.");
      return;
    }

    setSubmitting(true);
    if (isDemo) {
      const created = demoStore.addInvitation({
        email,
        full_name: fullName,
        role,
      });
      setInvitations(demoStore.getInvitations());
      setSubmitting(false);
      setShowModal(false);
      setEmail("");
      setFullName("");
      setNotice(`DEMO SIMULATION: Demonstration invitation created for ${created.email} (${created.role}). No external email dispatched.`);
      return;
    }

    if (!accessToken) return;
    try {
      const created = await tenantApi.inviteUser(accessToken, {
        email,
        full_name: fullName,
        role,
      });
      setInvitations((prev) => [created, ...prev]);
      setShowModal(false);
      setEmail("");
      setFullName("");
      setNotice(`Onboarding invitation initiated for ${email}.`);
    } catch (err) {
      setFormError(normalizeApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async (inv: TenantInvitation) => {
    if (isDemo) {
      demoStore.resendInvitation(inv.id);
      setNotice(`DEMO SIMULATION: Invitation extended for ${inv.email}.`);
      return;
    }
    if (!accessToken) return;
    try {
      await tenantApi.resendInvitation(accessToken, inv.user_id);
      alert(`Invitation code resent to ${inv.email}.`);
      loadInvitations();
    } catch (err) {
      alert(normalizeApiError(err).message);
    }
  };

  const handleCancel = async (inv: TenantInvitation) => {
    if (!confirm(`Cancel invitation for ${inv.email}? This code will be permanently invalidated.`)) {
      return;
    }
    if (isDemo) {
      demoStore.cancelInvitation(inv.id);
      setNotice(`DEMO SIMULATION: Invitation cancelled for ${inv.email}.`);
      return;
    }
    if (!accessToken) return;
    try {
      await tenantApi.cancelInvitation(accessToken, inv.user_id);
      loadInvitations();
    } catch (err) {
      alert(normalizeApiError(err).message);
    }
  };

  const statusBadge = (status: TenantInvitation["status"]) => {
    switch (status) {
      case "ACCEPTED":
        return { status: "ACTIVE" as const, label: "ACCEPTED" };
      case "PENDING":
        return { status: "PENDING" as const, label: "PENDING" };
      case "EXPIRED":
        return { status: "STORED" as const, label: "EXPIRED" };
      case "CANCELLED":
        return { status: "STORED" as const, label: "REVOKED" };
    }
  };

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Invitations" },
        ]}
        eyebrow="ONBOARDING"
        title="Team Invitations"
        subtitle="Invite personnel to join your organization with assigned operational roles."
        actions={
          <button
            type="button"
            className="ac-btn ac-btn-primary"
            onClick={() => {
              setShowModal(true);
              setFormError(null);
            }}
          >
            + Send Invitation
          </button>
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
            <strong>DEMO MODE</strong> · Viewing synthetic onboarding invitation lifecycle states.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={invitations.length === 0}
            emptyMessage="No pending or historical invitations."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      {notice && (
        <div
          style={{
            padding: "8px 12px",
            background: "rgba(16, 185, 129, 0.15)",
            color: "var(--success, #10b981)",
            borderRadius: 4,
            marginBottom: 16,
            fontSize: 13,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>✓ {notice}</span>
          <button
            type="button"
            className="ac-btn"
            style={{ padding: "2px 6px", fontSize: 11 }}
            onClick={() => setNotice(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Invitations Table */}
      <div className="ac-card" style={{ padding: 0, marginBottom: 24 }}>
        <div style={{ overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Recipient</th>
                <th>Target Role</th>
                <th>Status</th>
                <th>Issued</th>
                <th>Expires</th>
                <th style={{ textAlign: "right" }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {invitations.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "32px 16px", opacity: 0.7 }}>
                    No invitation records found.
                  </td>
                </tr>
              ) : (
                invitations.map((inv) => {
                  const badge = statusBadge(inv.status);
                  return (
                    <tr key={inv.id}>
                      <td>
                        <div style={{ fontWeight: 600 }}>{inv.full_name}</div>
                        <div className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>
                          {inv.email}
                        </div>
                      </td>
                      <td>
                        <span
                          className="ac-mono"
                          style={{
                            fontSize: 11,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: "var(--bg-subtle, rgba(255, 255, 255, 0.06))",
                            border: "1px solid var(--border-color, #27272a)",
                          }}
                        >
                          {inv.role}
                        </span>
                      </td>
                      <td>
                        <StatusBadge status={badge.status} label={badge.label} />
                      </td>
                      <td className="ac-mono" style={{ fontSize: 12 }}>
                        {new Date(inv.created_at).toLocaleDateString()}
                      </td>
                      <td className="ac-mono" style={{ fontSize: 12 }}>
                        {new Date(inv.expires_at).toLocaleDateString()}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        <div className="ac-flex ac-gap-2 ac-items-center" style={{ justifyContent: "flex-end" }}>
                          {inv.can_resend && (
                            <button
                              type="button"
                              className="ac-btn"
                              style={{ fontSize: 12, padding: "4px 8px" }}
                              onClick={() => handleResend(inv)}
                            >
                              Resend
                            </button>
                          )}
                          {inv.can_cancel && (
                            <button
                              type="button"
                              className="ac-btn"
                              style={{ fontSize: 12, padding: "4px 8px", color: "var(--danger, #ef4444)" }}
                              onClick={() => handleCancel(inv)}
                            >
                              Cancel
                            </button>
                          )}
                          {!inv.can_resend && !inv.can_cancel && (
                            <span style={{ fontSize: 12, opacity: 0.5 }}>—</span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div
        className="ac-card"
        style={{
          background: "var(--bg-subtle, rgba(255, 255, 255, 0.02))",
          border: "1px dashed var(--border-color, #27272a)",
        }}
      >
        <h3 className="ac-h3" style={{ fontSize: 14, marginBottom: 4 }}>
          Invitation &amp; Security Lifecycle
        </h3>
        <p className="ac-text-sm" style={{ opacity: 0.8, margin: 0 }}>
          Invitations issue single-use secure onboarding codes. Once accepted, the recipient sets their account password directly. In local/development environments without live SMTP, codes are securely recorded in the authorization ledger.
        </p>
      </div>

      {/* Invite Modal */}
      {showModal && (
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
          <div className="ac-card" style={{ maxWidth: 440, width: "90%", padding: 24 }}>
            <h3 className="ac-h3" style={{ marginBottom: 4 }}>
              Invite Team Member
            </h3>
            <p className="ac-text-sm" style={{ opacity: 0.7, marginBottom: 16 }}>
              Send an onboarding invitation to an aerospace team member.
            </p>

            <form onSubmit={handleInvite}>
              <div style={{ marginBottom: 14 }}>
                <label className="ac-label" style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>
                  Email Address *
                </label>
                <input
                  type="email"
                  className="ac-input"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="colleague@yourcompany.com"
                  style={{ width: "100%" }}
                  required
                />
              </div>

              <div style={{ marginBottom: 14 }}>
                <label className="ac-label" style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>
                  Full Name *
                </label>
                <input
                  type="text"
                  className="ac-input"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Capt. Jane Doe"
                  style={{ width: "100%" }}
                  required
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label className="ac-label" style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>
                  Assigned Operational Role *
                </label>
                <select
                  className="ac-input"
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  style={{ width: "100%" }}
                >
                  {ROLES.map((r) => (
                    <option key={r.value} value={r.value}>
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              {formError && (
                <div
                  style={{
                    padding: "8px 12px",
                    background: "rgba(239, 68, 68, 0.15)",
                    color: "var(--danger, #ef4444)",
                    borderRadius: 4,
                    marginBottom: 16,
                    fontSize: 13,
                  }}
                >
                  ⚠ {formError}
                </div>
              )}

              <div className="ac-flex ac-gap-2" style={{ justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="ac-btn"
                  onClick={() => setShowModal(false)}
                  disabled={submitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="ac-btn ac-btn-primary"
                  disabled={submitting}
                >
                  {submitting ? "Sending..." : "Send Invitation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
