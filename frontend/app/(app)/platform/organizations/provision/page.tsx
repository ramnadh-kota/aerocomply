"use client";

// Phase 18.3 & Milestone: Platform Admin — Provision Organization. Orchestrates the
// existing Organization/Plan/Subscription/Admin systems in one atomic flow
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

  const orgCodePreview = organizationName.trim()
    ? organizationName
        .trim()
        .toUpperCase()
        .replace(/[^A-Z0-9]/g, "_")
        .slice(0, 16)
    : "";

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
          plan_code: selectedPlan?.code ?? "DRONE_001",
          features_count: selectedPlan?.included_features_count ?? 12,
          limits_count: 6,
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
            Create a new customer organization, assign a commercial plan, establish baseline entitlements,
            and invite its initial tenant administrator.
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
        <div className="ac-card" style={{ padding: "var(--ac-space-6)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <StatusBadge status="COMPLIANT" label="Tenant Ready" />
            <h2 className="ac-h2" style={{ margin: 0 }}>
              Organization Provisioned Successfully
            </h2>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 16,
              marginBottom: 20,
              background: "var(--ac-surface-2)",
              padding: "var(--ac-space-4)",
              borderRadius: "var(--ac-radius-md)",
            }}
          >
            <div>
              <span className="ac-text-xs" style={{ textTransform: "uppercase", opacity: 0.6, letterSpacing: "0.05em" }}>
                1. Organization Created
              </span>
              <p className="ac-text-sm" style={{ margin: "4px 0 0 0", fontWeight: 600 }}>
                {result.organization_name}
              </p>
              <span className="ac-text-xs" style={{ opacity: 0.8 }}>
                Status: {result.organization_status}
              </span>
            </div>

            <div>
              <span className="ac-text-xs" style={{ textTransform: "uppercase", opacity: 0.6, letterSpacing: "0.05em" }}>
                2. Subscription Created
              </span>
              <p className="ac-text-sm" style={{ margin: "4px 0 0 0", fontWeight: 600 }}>
                {result.subscription_status}
              </p>
              <span className="ac-text-xs" style={{ opacity: 0.8 }}>
                ID: {result.subscription_id.slice(0, 8)}…
              </span>
            </div>

            <div>
              <span className="ac-text-xs" style={{ textTransform: "uppercase", opacity: 0.6, letterSpacing: "0.05em" }}>
                3. Plan Assigned
              </span>
              <p className="ac-text-sm" style={{ margin: "4px 0 0 0", fontWeight: 600 }}>
                {result.plan_code || selectedPlan?.code || "Assigned"}
              </p>
              <span className="ac-text-xs" style={{ opacity: 0.8 }}>
                {selectedPlan?.name ?? "Commercial Plan Baseline"}
              </span>
            </div>

            <div>
              <span className="ac-text-xs" style={{ textTransform: "uppercase", opacity: 0.6, letterSpacing: "0.05em" }}>
                4. Initial Admin Created
              </span>
              <p className="ac-text-sm" style={{ margin: "4px 0 0 0", fontWeight: 600 }}>
                {result.admin_email}
              </p>
              <span className="ac-text-xs" style={{ opacity: 0.8 }}>
                {result.admin_email_verified ? "Email Verified" : "Awaiting activation OTP"}
              </span>
            </div>

            <div>
              <span className="ac-text-xs" style={{ textTransform: "uppercase", opacity: 0.6, letterSpacing: "0.05em" }}>
                5. Entitlements Established
              </span>
              <p className="ac-text-sm" style={{ margin: "4px 0 0 0", fontWeight: 600 }}>
                Inherited from Plan
              </p>
              <span className="ac-text-xs" style={{ opacity: 0.8 }}>
                {result.features_count !== undefined && result.features_count !== null
                  ? `${result.features_count} feature entitlements active`
                  : "Effective features resolved"}
              </span>
            </div>

            <div>
              <span className="ac-text-xs" style={{ textTransform: "uppercase", opacity: 0.6, letterSpacing: "0.05em" }}>
                6. Usage Limits Established
              </span>
              <p className="ac-text-sm" style={{ margin: "4px 0 0 0", fontWeight: 600 }}>
                Inherited from Plan
              </p>
              <span className="ac-text-xs" style={{ opacity: 0.8 }}>
                {result.limits_count !== undefined && result.limits_count !== null
                  ? `${result.limits_count} limit thresholds established`
                  : "Baseline usage limits configured"}
              </span>
            </div>
          </div>

          <p className="ac-text-sm" style={{ margin: "0 0 16px 0", opacity: 0.85 }}>
            {result.onboarding_email_sent
              ? "An onboarding invitation has been dispatched to the administrator. They will verify their email and set their password through the secure activation flow."
              : "The initial onboarding email could not be sent immediately. You may resend the invitation below."}
          </p>

          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
            <Link className="ac-btn" href={`/platform/organizations/${result.organization_id}`}>
              View Organization
            </Link>
            <button className="ac-btn" onClick={resendInvitation} disabled={resendStatus === "sending"}>
              {resendStatus === "sending"
                ? "Sending…"
                : resendStatus === "sent"
                  ? "Invitation Resent"
                  : "Resend Invitation"}
            </button>
            <button className="ac-btn" style={{ background: "transparent" }} onClick={reset}>
              Provision Another
            </button>
            {resendStatus === "error" && (
              <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)", alignSelf: "center" }}>
                Could not resend invitation right now (may be within cooldown window).
              </span>
            )}
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4)" }}>
          {/* Organization Section */}
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Organization</strong>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginTop: 10 }}>
              <div>
                <label className="ac-text-xs" style={{ display: "block", marginBottom: 4, opacity: 0.8 }}>
                  Organization Name *
                </label>
                <input
                  className="ac-input"
                  style={{ width: "100%" }}
                  placeholder="e.g. Skyline Aerospace Ltd."
                  value={organizationName}
                  onChange={(e) => setOrganizationName(e.target.value)}
                  aria-label="Organization Name"
                />
              </div>
              <div>
                <label className="ac-text-xs" style={{ display: "block", marginBottom: 4, opacity: 0.8 }}>
                  Organization Code Preview
                </label>
                <input
                  className="ac-input"
                  style={{ width: "100%", opacity: 0.8, background: "var(--ac-surface-2)" }}
                  readOnly
                  placeholder="Auto-derived from name"
                  value={orgCodePreview}
                  aria-label="Organization Code"
                />
              </div>
            </div>
          </div>

          {/* Commercial Plan Section */}
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Commercial Plan</strong>
            {plansLoading ? (
              <p className="ac-text-sm" style={{ marginTop: 8 }}>
                Loading commercial plans…
              </p>
            ) : plansError ? (
              <p className="ac-text-sm" style={{ marginTop: 8, color: "var(--ac-status-non-compliant)" }}>
                {plansError.message}
              </p>
            ) : plans.length === 0 ? (
              <p className="ac-text-sm" style={{ marginTop: 8 }}>
                No active commercial plans exist. <Link href="/platform/plans">Create one in Plans →</Link>
              </p>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginTop: 10 }}>
                <div>
                  <label className="ac-text-xs" style={{ display: "block", marginBottom: 4, opacity: 0.8 }}>
                    Select Plan *
                  </label>
                  <select
                    className="ac-input"
                    style={{ width: "100%" }}
                    value={planId}
                    onChange={(e) => setPlanId(e.target.value)}
                    aria-label="Commercial Plan"
                  >
                    <option value="">Select Plan ▼</option>
                    {plans.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name} ({p.code})
                      </option>
                    ))}
                  </select>
                </div>
                {selectedPlan && (
                  <div style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
                    <span className="ac-text-xs" style={{ opacity: 0.7 }}>
                      Asset Scope: <strong>{selectedPlan.asset_scope ?? "All Aerospace"}</strong>
                    </span>
                    <span className="ac-text-xs" style={{ opacity: 0.7 }}>
                      Features: <strong>{selectedPlan.included_features_count ?? "Full Suite"} included</strong>
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Subscription Section */}
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Subscription</strong>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginTop: 10 }}>
              <div>
                <label className="ac-text-xs" style={{ display: "block", marginBottom: 4, opacity: 0.8 }}>
                  Start Date
                </label>
                <input
                  className="ac-input"
                  style={{ width: "100%", opacity: 0.85, background: "var(--ac-surface-2)" }}
                  readOnly
                  value={new Date().toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
                  aria-label="Start Date"
                />
              </div>
              <div>
                <label className="ac-text-xs" style={{ display: "block", marginBottom: 4, opacity: 0.8 }}>
                  Billing / Subscription Status *
                </label>
                <select
                  className="ac-input"
                  style={{ width: "100%" }}
                  value={subscriptionStatus}
                  onChange={(e) => setSubscriptionStatus(e.target.value as "TRIALING" | "ACTIVE")}
                  aria-label="Subscription Status"
                >
                  <option value="TRIALING">Trial (TRIALING)</option>
                  <option value="ACTIVE">Active (ACTIVE)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Initial Tenant Administrator Section */}
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Initial Tenant Administrator</strong>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginTop: 10 }}>
              <div>
                <label className="ac-text-xs" style={{ display: "block", marginBottom: 4, opacity: 0.8 }}>
                  Full Name *
                </label>
                <input
                  className="ac-input"
                  style={{ width: "100%" }}
                  placeholder="e.g. Captain Jane Doe"
                  value={adminFullName}
                  onChange={(e) => setAdminFullName(e.target.value)}
                  aria-label="Admin Full Name"
                />
              </div>
              <div>
                <label className="ac-text-xs" style={{ display: "block", marginBottom: 4, opacity: 0.8 }}>
                  Email Address *
                </label>
                <input
                  className="ac-input"
                  style={{ width: "100%" }}
                  placeholder="admin@customer.com"
                  type="email"
                  value={adminEmail}
                  onChange={(e) => setAdminEmail(e.target.value)}
                  aria-label="Admin Email"
                />
              </div>
            </div>
            <div style={{ marginTop: 10, padding: 8, background: "var(--ac-surface-2)", borderRadius: "var(--ac-radius-sm)" }}>
              <span className="ac-text-xs" style={{ opacity: 0.85 }}>
                <strong>Credential Flow:</strong> A secure one-time activation token will be generated and dispatched
                to the initial administrator. The administrator sets their own password during onboarding; passwords are never
                set, stored, or viewed by platform administrators.
              </span>
            </div>
          </div>

          {/* Provisioning Summary Card */}
          {canSubmit && (
            <div className="ac-card" style={{ padding: "var(--ac-space-4)", background: "var(--ac-surface-2)" }}>
              <strong className="ac-text-sm" style={{ display: "block", marginBottom: 8 }}>
                Provisioning Summary
              </strong>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
                <div>
                  <span className="ac-text-xs" style={{ opacity: 0.6, display: "block" }}>
                    Plan:
                  </span>
                  <span className="ac-text-sm" style={{ fontWeight: 600 }}>
                    {selectedPlan?.code ?? "—"}
                  </span>
                  <span className="ac-text-xs" style={{ display: "block", opacity: 0.8 }}>
                    {selectedPlan?.name ?? "Commercial Plan"}
                  </span>
                </div>
                <div>
                  <span className="ac-text-xs" style={{ opacity: 0.6, display: "block" }}>
                    Features:
                  </span>
                  <span className="ac-text-sm" style={{ fontWeight: 600 }}>
                    Inherited from selected plan
                  </span>
                  <span className="ac-text-xs" style={{ display: "block", opacity: 0.8 }}>
                    Baseline features active upon provisioning
                  </span>
                </div>
                <div>
                  <span className="ac-text-xs" style={{ opacity: 0.6, display: "block" }}>
                    Limits:
                  </span>
                  <span className="ac-text-sm" style={{ fontWeight: 600 }}>
                    Inherited from selected plan
                  </span>
                  <span className="ac-text-xs" style={{ display: "block", opacity: 0.8 }}>
                    Assets, users, work orders, LISA tokens & storage
                  </span>
                </div>
              </div>
            </div>
          )}

          {submitError && (
            <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
              {submitError.message}
            </p>
          )}

          <div className="ac-flex ac-gap-2">
            <button className="ac-btn" onClick={submit} disabled={!canSubmit || submitting}>
              {submitting ? "Provisioning…" : "Provision Organization"}
            </button>
            <Link className="ac-btn" style={{ background: "transparent" }} href="/platform/organizations">
              Cancel
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ProvisionOrganizationPage() {
  return <RealProvisionOrganization />;
}

