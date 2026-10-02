"use client";

// Platform Admin — Provision Organization Wizard (Suite -> Suite Plan -> Subscription).
// Implements the canonical commercial hierarchy:
// Step 1: Select Suite (AIRCRAFT, DRONE_UAV, HELICOPTER, EVTOL_AAM)
// Step 2: Select Plan belonging ONLY to that Suite
// Step 3: Review Subscription & Configure Organization Admin
// Step 4: Create Organization + Subscription & Receive Activation Token

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type ProvisionOrganizationResponse } from "@/lib/api/platform";
import { planApi, type PlanResponse } from "@/lib/api/plan";
import {
  productCatalogApi,
  type ProductSuiteResponse,
} from "@/lib/api/productCatalog";
import {
  DEMO_PLATFORM_PLANS,
  DEMO_PLATFORM_SUITES,
} from "@/lib/demo/demoPlatform";

export function RealProvisionOrganization() {
  const { accessToken, isAuthenticated } = useSession();
  const { mode } = useDataMode();

  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Suites & Plans data
  const [suites, setSuites] = useState<ProductSuiteResponse[]>([]);
  const [suitesLoading, setSuitesLoading] = useState(true);
  const [suitesError, setSuitesError] = useState<NormalizedApiError | null>(null);

  const [plans, setPlans] = useState<PlanResponse[]>([]);
  const [plansLoading, setPlansLoading] = useState(true);
  const [plansError, setPlansError] = useState<NormalizedApiError | null>(null);

  // Form selections
  const [selectedSuiteId, setSelectedSuiteId] = useState<string>("");
  const [planId, setPlanId] = useState<string>("");
  const [organizationName, setOrganizationName] = useState("");
  const [subscriptionStatus, setSubscriptionStatus] = useState<"TRIALING" | "ACTIVE">("ACTIVE");
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
      setSuites(DEMO_PLATFORM_SUITES);
      setSuitesLoading(false);
      setPlans(DEMO_PLATFORM_PLANS.filter((p) => p.is_active));
      setPlansLoading(false);
      return;
    }
    if (!isAuthenticated || !accessToken) {
      setSuitesLoading(false);
      setPlansLoading(false);
      return;
    }

    setSuitesLoading(true);
    setPlansLoading(true);

    Promise.allSettled([
      productCatalogApi.listSuites(accessToken),
      planApi.listPlans(accessToken),
    ]).then(([suitesRes, plansRes]) => {
      if (suitesRes.status === "fulfilled") {
        setSuites(suitesRes.value);
      } else {
        setSuitesError(normalizeApiError(suitesRes.reason));
      }

      if (plansRes.status === "fulfilled") {
        setPlans(plansRes.value.filter((p) => p.is_active));
      } else {
        setPlansError(normalizeApiError(plansRes.reason));
      }

      setSuitesLoading(false);
      setPlansLoading(false);
    });
  }, [mode, accessToken, isAuthenticated]);

  const selectedSuite = suites.find((s) => s.id === selectedSuiteId) ?? null;

  // Filter plans strictly to selected Suite
  const availablePlansForSuite = plans.filter(
    (p) => p.suite_id === selectedSuiteId || (!p.suite_id && selectedSuite?.code === "AIRCRAFT")
  );

  const selectedPlan = plans.find((p) => p.id === planId) ?? null;

  const canProceedToPlan = !!selectedSuiteId;
  const canProceedToReview = !!selectedSuiteId && !!planId;
  const canSubmit =
    organizationName.trim().length > 0 &&
    planId.length > 0 &&
    adminEmail.trim().length > 0 &&
    adminFullName.trim().length > 0;

  const handleSelectSuite = (suiteId: string) => {
    setSelectedSuiteId(suiteId);
    setPlanId(""); // Reset plan if suite changes
  };

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
          plan_code: selectedPlan?.code ?? "PROFESSIONAL",
          features_count: selectedPlan?.included_features_count ?? 8,
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
    setStep(1);
    setSelectedSuiteId("");
    setPlanId("");
    setOrganizationName("");
    setSubscriptionStatus("ACTIVE");
    setAdminEmail("");
    setAdminFullName("");
    setResult(null);
    setSubmitError(null);
    setResendStatus("idle");
  };

  const renderSuiteIcon = (code: string) => {
    switch (code) {
      case "DRONE_UAV":
        return "🛸";
      case "AIRCRAFT":
        return "✈️";
      case "HELICOPTER":
        return "🚁";
      case "EVTOL_AAM":
        return "⚡";
      default:
        return "🌐";
    }
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Organizations", href: "/platform/organizations" },
          { label: "Provision Organization" },
        ]}
      />
      <div className="ac-section-header" style={{ marginBottom: "var(--ac-space-4)" }}>
        <div>
          <h1 className="ac-h1">Provision Customer Organization</h1>
          <p className="ac-subtitle">
            Configure product suite, commercial plan baseline, tenant details, and dispatch administrator credentials.
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
        /* Provisioning Success Confirmation */
        <div className="ac-card" style={{ padding: "var(--ac-space-6)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
            <StatusBadge status="COMPLIANT" label="Tenant Active" />
            <h2 className="ac-h2" style={{ margin: 0 }}>
              Organization Successfully Provisioned
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
                1. Product Suite Bound
              </span>
              <p className="ac-text-sm" style={{ margin: "4px 0 0 0", fontWeight: 600 }}>
                {selectedSuite?.name ?? "Commercial Product Suite"} ({selectedSuite?.code ?? "SUITE"})
              </p>
              <span className="ac-text-xs" style={{ opacity: 0.8 }}>
                Strict domain isolation active
              </span>
            </div>

            <div>
              <span className="ac-text-xs" style={{ textTransform: "uppercase", opacity: 0.6, letterSpacing: "0.05em" }}>
                2. Organization Created
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
                3. Subscription Created
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
                4. Plan Assigned
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
                5. Administrator Invited
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
                6. Entitlements Established
              </span>
              <p className="ac-text-sm" style={{ margin: "4px 0 0 0", fontWeight: 600 }}>
                {result.features_count !== undefined && result.features_count !== null
                  ? `${result.features_count} feature entitlements`
                  : "Effective features resolved"}
              </p>
              <span className="ac-text-xs" style={{ opacity: 0.8 }}>
                Usage limits & domain RBAC configured
              </span>
            </div>
          </div>

          <p className="ac-text-sm" style={{ margin: "0 0 16px 0", opacity: 0.85 }}>
            {result.onboarding_email_sent
              ? "An onboarding invitation has been dispatched to the administrator. They will verify their email and set their password through the secure activation flow."
              : "The initial onboarding email could not be sent immediately. You may resend the invitation below."}
          </p>

          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
            <Link className="ac-btn ac-btn-primary" href={`/platform/organizations/${result.organization_id}`}>
              View Organization →
            </Link>
            <button className="ac-btn" onClick={resendInvitation} disabled={resendStatus === "sending"}>
              {resendStatus === "sending"
                ? "Sending…"
                : resendStatus === "sent"
                  ? "Invitation Resent"
                  : "Resend Invitation"}
            </button>
            <button className="ac-btn" style={{ background: "transparent" }} onClick={reset}>
              Provision Another Organization
            </button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4)" }}>
          {/* Step Progress Bar */}
          <div
            className="ac-card"
            style={{
              padding: "var(--ac-space-3) var(--ac-space-4)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: 8,
              overflowX: "auto",
            }}
          >
            {[
              { num: 1, label: "1. Select Suite" },
              { num: 2, label: "2. Select Plan" },
              { num: 3, label: "3. Review & Provision" },
            ].map((s) => {
              const isActive = step === s.num;
              const isPast = step > s.num;
              return (
                <button
                  key={s.num}
                  type="button"
                  disabled={!isPast}
                  aria-current={isActive ? "step" : undefined}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    cursor: isPast ? "pointer" : "default",
                    background: "none",
                    border: 0,
                    padding: 0,
                    font: "inherit",
                    color: "inherit",
                    opacity: isActive ? 1 : isPast ? 0.9 : 0.45,
                  }}
                  onClick={() => {
                    if (isPast) setStep(s.num as any);
                  }}
                >
                  <span
                    style={{
                      width: 26,
                      height: 26,
                      borderRadius: "50%",
                      backgroundColor: isActive ? "var(--ac-primary, #3b82f6)" : isPast ? "var(--ac-status-compliant, #22c55e)" : "var(--ac-surface-2)",
                      color: "#fff",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 12,
                      fontWeight: 700,
                    }}
                  >
                    {isPast ? "✓" : s.num}
                  </span>
                  <span style={{ fontSize: 13, fontWeight: isActive ? 600 : 400 }}>{s.label}</span>
                </button>
              );
            })}
          </div>

          {/* STEP 1: SELECT SUITE */}
          {step === 1 && (
            <div className="ac-card" style={{ padding: "var(--ac-space-5)" }}>
              <div style={{ marginBottom: 16 }}>
                <strong className="ac-text-sm" style={{ display: "block", fontSize: 16 }}>
                  Step 1 — Select Product Suite
                </strong>
                <p className="ac-text-muted" style={{ fontSize: 13, margin: "4px 0 0" }}>
                  Every organization operates inside exactly one domain Suite (e.g. Commercial Aircraft, Drone UAV, Helicopter, or eVTOL).
                </p>
              </div>

              {suitesLoading ? (
                <p className="ac-text-sm">Loading available product suites…</p>
              ) : suitesError ? (
                <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>
                  {suitesError.message}
                </p>
              ) : (
                <div
                  role="radiogroup"
                  aria-label="Product suite"
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                    gap: 16,
                  }}
                >
                  {suites.map((s) => {
                    const isSelected = selectedSuiteId === s.id;
                    const plansCount = plans.filter(
                      (p) => p.suite_id === s.id || (!p.suite_id && s.code === "AIRCRAFT")
                    ).length;

                    return (
                      <button
                        key={s.id}
                        type="button"
                        role="radio"
                        aria-checked={isSelected}
                        onClick={() => handleSelectSuite(s.id)}
                        style={{
                          padding: 16,
                          borderRadius: 8,
                          border: isSelected
                            ? "2px solid var(--ac-primary, #3b82f6)"
                            : "1px solid var(--ac-border, #333)",
                          backgroundColor: isSelected ? "rgba(59, 130, 246, 0.08)" : "var(--ac-surface-1)",
                          cursor: "pointer",
                          width: "100%",
                          textAlign: "left",
                          font: "inherit",
                          color: "inherit",
                          transition: "all 0.15s ease",
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "space-between",
                        }}
                      >
                        <div>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                            <span style={{ fontSize: 28 }}>{renderSuiteIcon(s.code)}</span>
                            <span
                              className="ac-mono"
                              style={{
                                fontSize: 10,
                                padding: "2px 6px",
                                borderRadius: 4,
                                background: "var(--ac-surface-2)",
                                opacity: 0.8,
                              }}
                            >
                              {s.code}
                            </span>
                          </div>
                          <strong style={{ fontSize: 15, display: "block", marginBottom: 4 }}>{s.name}</strong>
                          <p className="ac-text-muted" style={{ fontSize: 12, margin: 0, minHeight: 36 }}>
                            {s.description}
                          </p>
                        </div>
                        <div
                          style={{
                            marginTop: 14,
                            paddingTop: 10,
                            borderTop: "1px solid var(--ac-border, #333)",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            fontSize: 12,
                          }}
                        >
                          <span style={{ opacity: 0.8 }}>
                            <strong>{plansCount}</strong> available tiers
                          </span>
                          {isSelected && (
                            <span style={{ color: "var(--ac-primary, #3b82f6)", fontWeight: 700 }}>
                              Selected ✓
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}

              <div style={{ marginTop: 24, display: "flex", justifyContent: "flex-end" }}>
                <button
                  className="ac-btn ac-btn-primary"
                  onClick={() => setStep(2)}
                  disabled={!canProceedToPlan}
                >
                  Next: Select Suite Plan →
                </button>
              </div>
            </div>
          )}

          {/* STEP 2: SELECT SUITE-SPECIFIC PLAN */}
          {step === 2 && (
            <div className="ac-card" style={{ padding: "var(--ac-space-5)" }}>
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <strong className="ac-text-sm" style={{ fontSize: 16 }}>
                    Step 2 — Select Commercial Plan
                  </strong>
                  <span
                    className="ac-badge"
                    style={{
                      backgroundColor: "rgba(59, 130, 246, 0.15)",
                      color: "var(--ac-accent)",
                      fontSize: 11,
                    }}
                  >
                    Suite: {selectedSuite?.name}
                  </span>
                </div>
                <p className="ac-text-muted" style={{ fontSize: 13, margin: 0 }}>
                  Showing only plans engineered exclusively for <strong>{selectedSuite?.name}</strong>. Cross-suite plan assignment is strictly blocked.
                </p>
              </div>

              {availablePlansForSuite.length === 0 ? (
                <div style={{ padding: 24, textAlign: "center", background: "var(--ac-surface-2)", borderRadius: 8 }}>
                  <p className="ac-text-sm" style={{ margin: "0 0 12px 0" }}>
                    No commercial plans currently configured for {selectedSuite?.name}.
                  </p>
                  <Link href="/platform/plans" className="ac-btn">
                    Configure Plans in Plan Catalog →
                  </Link>
                </div>
              ) : (
                <div
                  role="radiogroup"
                  aria-label="Commercial plan"
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                    gap: 16,
                  }}
                >
                  {availablePlansForSuite.map((p) => {
                    const isSelected = planId === p.id;
                    return (
                      <button
                        key={p.id}
                        type="button"
                        role="radio"
                        aria-checked={isSelected}
                        onClick={() => setPlanId(p.id)}
                        style={{
                          padding: 16,
                          borderRadius: 8,
                          border: isSelected
                            ? "2px solid var(--ac-primary, #3b82f6)"
                            : "1px solid var(--ac-border, #333)",
                          backgroundColor: isSelected ? "rgba(59, 130, 246, 0.08)" : "var(--ac-surface-1)",
                          cursor: "pointer",
                          width: "100%",
                          textAlign: "left",
                          font: "inherit",
                          color: "inherit",
                          transition: "all 0.15s ease",
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "space-between",
                        }}
                      >
                        <div>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                            <strong style={{ fontSize: 16 }}>{p.name}</strong>
                            <span className="ac-mono" style={{ fontSize: 11, opacity: 0.7 }}>
                              {p.code}
                            </span>
                          </div>
                          {p.description && (
                            <p className="ac-text-muted" style={{ fontSize: 12, margin: "0 0 12px 0" }}>
                              {p.description}
                            </p>
                          )}
                          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                            <span
                              style={{
                                fontSize: 11,
                                padding: "2px 6px",
                                borderRadius: 4,
                                backgroundColor: "var(--ac-surface-2)",
                              }}
                            >
                              Features: <strong>{p.included_features_count ?? "Full"}</strong>
                            </span>
                            <span
                              style={{
                                fontSize: 11,
                                padding: "2px 6px",
                                borderRadius: 4,
                                backgroundColor: "var(--ac-surface-2)",
                              }}
                            >
                              Domain: <strong>{p.asset_scope ?? selectedSuite?.code}</strong>
                            </span>
                          </div>
                        </div>

                        <div
                          style={{
                            marginTop: 12,
                            paddingTop: 10,
                            borderTop: "1px solid var(--ac-border, #333)",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                        >
                          <span style={{ fontSize: 12, opacity: 0.8 }}>Commercial Tier</span>
                          {isSelected && (
                            <span style={{ color: "var(--ac-primary, #3b82f6)", fontWeight: 700, fontSize: 12 }}>
                              Selected ✓
                            </span>
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}

              <div style={{ marginTop: 24, display: "flex", justifyContent: "space-between" }}>
                <button className="ac-btn" onClick={() => setStep(1)}>
                  ← Back to Suites
                </button>
                <button
                  className="ac-btn ac-btn-primary"
                  onClick={() => setStep(3)}
                  disabled={!canProceedToReview}
                >
                  Next: Organization Details & Review →
                </button>
              </div>
            </div>
          )}

          {/* STEP 3: ORGANIZATION DETAILS & REVIEW */}
          {step === 3 && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4)" }}>
              {/* Selected Suite & Plan Summary */}
              <div className="ac-card" style={{ padding: "var(--ac-space-4)", background: "var(--ac-surface-2)" }}>
                <strong className="ac-text-sm" style={{ display: "block", marginBottom: 8 }}>
                  Commercial Entitlement Boundary
                </strong>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
                  <div>
                    <span className="ac-text-xs" style={{ opacity: 0.6, display: "block" }}>
                      Product Suite:
                    </span>
                    <span className="ac-text-sm" style={{ fontWeight: 600 }}>
                      {renderSuiteIcon(selectedSuite?.code ?? "")} {selectedSuite?.name}
                    </span>
                    <span className="ac-text-xs" style={{ display: "block", opacity: 0.8 }}>
                      Code: {selectedSuite?.code}
                    </span>
                  </div>
                  <div>
                    <span className="ac-text-xs" style={{ opacity: 0.6, display: "block" }}>
                      Commercial Plan:
                    </span>
                    <span className="ac-text-sm" style={{ fontWeight: 600 }}>
                      {selectedPlan?.name} ({selectedPlan?.code})
                    </span>
                    <span className="ac-text-xs" style={{ display: "block", opacity: 0.8 }}>
                      Includes {selectedPlan?.included_features_count ?? "all"} baseline features
                    </span>
                  </div>
                  <div>
                    <span className="ac-text-xs" style={{ opacity: 0.6, display: "block" }}>
                      Domain Boundary:
                    </span>
                    <span className="ac-text-sm" style={{ fontWeight: 600 }}>
                      Strict Tenant Domain Isolation
                    </span>
                    <span className="ac-text-xs" style={{ display: "block", opacity: 0.8 }}>
                      Cross-suite APIs and assets restricted
                    </span>
                  </div>
                </div>
              </div>

              {/* Organization Section */}
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <strong className="ac-text-sm">Organization Details</strong>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 12, marginTop: 10 }}>
                  <div>
                    <label className="ac-text-xs" style={{ display: "block", marginBottom: 4, opacity: 0.8 }}>
                      Organization Name *
                    </label>
                    <input
                      className="ac-input"
                      style={{ width: "100%" }}
                      placeholder="e.g. Skyline Drone Technologies Ltd."
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

              {/* Subscription Status Section */}
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <strong className="ac-text-sm">Subscription Status</strong>
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
                      Subscription Status *
                    </label>
                    <select
                      className="ac-input"
                      style={{ width: "100%" }}
                      value={subscriptionStatus}
                      onChange={(e) => setSubscriptionStatus(e.target.value as "TRIALING" | "ACTIVE")}
                      aria-label="Subscription Status"
                    >
                      <option value="ACTIVE">Active (Commercial Customer)</option>
                      <option value="TRIALING">Trialing (Evaluation Period)</option>
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
                      Administrator Full Name *
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
                      Administrator Email Address *
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
                    <strong>Credential Security:</strong> A one-time activation token will be dispatched to the administrator. The administrator sets their own password during onboarding; platform administrators never see passwords.
                  </span>
                </div>
              </div>

              {submitError && (
                <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                  {submitError.message}
                </p>
              )}

              <div className="ac-flex ac-gap-2" style={{ justifyContent: "space-between" }}>
                <button className="ac-btn" onClick={() => setStep(2)}>
                  ← Back to Plan Selection
                </button>
                <div className="ac-flex ac-gap-2">
                  <Link className="ac-btn" style={{ background: "transparent" }} href="/platform/organizations">
                    Cancel
                  </Link>
                  <button className="ac-btn ac-btn-primary" onClick={submit} disabled={!canSubmit || submitting}>
                    {submitting ? "Provisioning Organization…" : "Create Organization & Subscription"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ProvisionOrganizationPage() {
  return <RealProvisionOrganization />;
}
