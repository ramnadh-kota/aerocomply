"use client";

// Phase 18.3: Platform Admin — Provision Organization. Orchestrates the
// existing Organization/Plan/Subscription/Admin systems in one guided flow
// (backend/app/api/v1/platform.py POST /platform/organizations/provision +
// app/services/provisioning_service.py) rather than duplicating any of
// them. REAL-mode only, same pattern as the rest of /platform/*. Backend
// enforces PLATFORM_MANAGE on every call — this page hiding itself from
// non-platform-admin users is a UX convenience, never the security
// boundary.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type ProvisionOrganizationResponse } from "@/lib/api/platform";
import { planApi, type PlanResponse } from "@/lib/api/plan";
import { DEMO_PLATFORM_PLANS } from "@/lib/demo/demoPlatform";

export function RealProvisionOrganization() {
  const { accessToken, isAuthenticated } = useSession();
  const { mode } = useDataMode();

  const [plans, setPlans] = useState<PlanResponse[]>([]);
  const [plansLoading, setPlansLoading] = useState(true);
  const [plansError, setPlansError] = useState<NormalizedApiError | null>(null);

  const [organizationName, setOrganizationName] = useState("");
  const [planId, setPlanId] = useState("");
  const [subscriptionStatus, setSubscriptionStatus] = useState<"TRIALING" | "ACTIVE">("TRIALING");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminFullName, setAdminFullName] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<NormalizedApiError | null>(null);
  const [result, setResult] = useState<ProvisionOrganizationResponse | null>(null);
  const [resendStatus, setResendStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");

  useEffect(() => {
    if (mode === "DEMO") {
      setPlans(DEMO_PLATFORM_PLANS.filter((p) => p.is_active));
      setPlansLoading(false);
      return;
    }
    if (!isAuthenticated || !accessToken) {
      setPlansLoading(false);
      return;
    }
    planApi
      .listPlans(accessToken)
      .then((all) => setPlans(all.filter((p) => p.is_active)))
      .catch((err) => setPlansError(normalizeApiError(err)))
      .finally(() => setPlansLoading(false));
  }, [mode, accessToken, isAuthenticated]);

  const selectedPlan = plans.find((p) => p.id === planId) ?? null;
  const canSubmit =
    organizationName.trim().length > 0 &&
    planId.length > 0 &&
    adminEmail.trim().length > 0 &&
    adminFullName.trim().length > 0;

  const submit = () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);

    if (mode === "DEMO") {
      setTimeout(() => {
        setResult({
          organization_id: `00000000-0000-0000-0000-${String(Date.now()).slice(-12)}`,
          organization_name: organizationName.trim(),
          organization_status: "ACTIVE",
          plan_id: planId,
          subscription_id: `20000000-0000-0000-0000-${String(Date.now()).slice(-12)}`,
          subscription_status: subscriptionStatus,
          admin_user_id: `30000000-0000-0000-0000-${String(Date.now()).slice(-12)}`,
          admin_email: adminEmail.trim(),
          admin_email_verified: false,
          onboarding_email_sent: true,
        });
        setSubmitting(false);
      }, 500);
      return;
    }

    if (!accessToken) return;
    platformApi
      .provisionOrganization(accessToken, {
        organization_name: organizationName.trim(),
        plan_id: planId,
        subscription_status: subscriptionStatus,
        admin_email: adminEmail.trim(),
        admin_full_name: adminFullName.trim(),
      })
      .then(setResult)
      .catch((err) => setSubmitError(normalizeApiError(err)))
      .finally(() => setSubmitting(false));
  };

  const resendInvitation = () => {
    if (mode === "DEMO") {
      setResendStatus("sent");
      return;
    }
    if (!accessToken || !result) return;
    setResendStatus("sending");
    platformApi
      .resendAdminInvitation(accessToken, result.admin_user_id)
      .then(() => setResendStatus("sent"))
      .catch(() => setResendStatus("error"));
  };

  const reset = () => {
    setOrganizationName("");
    setPlanId("");
    setSubscriptionStatus("TRIALING");
    setAdminEmail("");
    setAdminFullName("");
    setResult(null);
    setSubmitError(null);
    setResendStatus("idle");
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Organizations", href: "/platform/organizations" },
          { label: "Provision" },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Provision Organization</h1>
          <p className="ac-subtitle">
            Create a new customer organization, assign a plan, and invite its first admin. Not visible to
            customer users.
          </p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : result ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="COMPLIANT" label="Organization Provisioned" />
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              <strong>Organization:</strong> {result.organization_name} ({result.organization_status})
            </p>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              <strong>Plan:</strong> {selectedPlan?.name ?? result.plan_id} — Subscription{" "}
              {result.subscription_status}
            </p>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              <strong>Admin:</strong> {result.admin_email} —{" "}
              {result.admin_email_verified ? "Email verified" : "Awaiting email verification"}
            </p>
            <p className="ac-text-sm" style={{ margin: 0, opacity: 0.8 }}>
              {result.onboarding_email_sent
                ? "An invitation email has been sent. The administrator will verify their email and set their own password — the platform never sees or sets it."
                : "The invitation email could not be sent. Use Resend Invitation below."}
            </p>
          </div>
          <div className="ac-flex ac-gap-2" style={{ marginTop: 16, flexWrap: "wrap" }}>
            <button className="ac-btn" onClick={resendInvitation} disabled={resendStatus === "sending"}>
              {resendStatus === "sending"
                ? "Sending…"
                : resendStatus === "sent"
                  ? "Invitation Resent"
                  : "Resend Invitation"}
            </button>
            {resendStatus === "error" && (
              <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>
                Could not resend right now — it may still be within the resend cooldown window.
              </span>
            )}
            <Link className="ac-btn" href={`/platform/organizations/${result.organization_id}`}>
              View Organization
            </Link>
            <button className="ac-btn" onClick={reset}>
              Provision Another
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4)" }}>
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Organization</strong>
            <div style={{ marginTop: 8 }}>
              <input
                className="ac-input"
                style={{ width: "100%", maxWidth: 420 }}
                placeholder="Organization name"
                value={organizationName}
                onChange={(e) => setOrganizationName(e.target.value)}
                aria-label="Organization name"
              />
            </div>
          </div>

          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Commercial</strong>
            {plansLoading ? (
              <p className="ac-text-sm" style={{ marginTop: 8 }}>
                Loading plans…
              </p>
            ) : plansError ? (
              <p className="ac-text-sm" style={{ marginTop: 8, color: "var(--ac-status-non-compliant)" }}>
                {plansError.message}
              </p>
            ) : plans.length === 0 ? (
              <p className="ac-text-sm" style={{ marginTop: 8 }}>
                No active plans exist yet. <Link href="/platform/plans">Create one in Plans →</Link>
              </p>
            ) : (
              <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
                <select
                  className="ac-input"
                  style={{ width: 260 }}
                  value={planId}
                  onChange={(e) => setPlanId(e.target.value)}
                  aria-label="Plan"
                >
                  <option value="">Select a plan…</option>
                  {plans.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.code})
                    </option>
                  ))}
                </select>
                <select
                  className="ac-input"
                  style={{ width: 180 }}
                  value={subscriptionStatus}
                  onChange={(e) => setSubscriptionStatus(e.target.value as "TRIALING" | "ACTIVE")}
                  aria-label="Subscription status"
                >
                  <option value="TRIALING">Trial</option>
                  <option value="ACTIVE">Active</option>
                </select>
              </div>
            )}
          </div>

          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Administrator</strong>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
              <input
                className="ac-input"
                style={{ width: 240 }}
                placeholder="Full name"
                value={adminFullName}
                onChange={(e) => setAdminFullName(e.target.value)}
                aria-label="Admin full name"
              />
              <input
                className="ac-input"
                style={{ width: 260 }}
                placeholder="admin@customer.com"
                type="email"
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                aria-label="Admin email"
              />
            </div>
            <p className="ac-text-sm" style={{ marginTop: 8, opacity: 0.8 }}>
              The administrator will receive an email to verify their address and create their own password.
              No password is set here.
            </p>
          </div>

          {canSubmit && (
            <div className="ac-card" style={{ padding: "var(--ac-space-4)", background: "var(--ac-surface-2)" }}>
              <strong className="ac-text-sm">Review</strong>
              <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="ac-text-sm">
                  Organization: <strong>{organizationName.trim()}</strong>
                </span>
                <span className="ac-text-sm">
                  Plan: <strong>{selectedPlan?.name ?? "—"}</strong> ({subscriptionStatus === "TRIALING" ? "Trial" : "Active"})
                </span>
                <span className="ac-text-sm">
                  Admin: <strong>{adminFullName.trim()}</strong> — {adminEmail.trim()}
                </span>
              </div>
            </div>
          )}

          {submitError && (
            <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
              {submitError.message}
            </p>
          )}

          <div>
            <button className="ac-btn" onClick={submit} disabled={!canSubmit || submitting}>
              {submitting ? "Provisioning…" : "Provision Organization"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProvisionOrganizationPage() {
  return <RealProvisionOrganization />;
}
