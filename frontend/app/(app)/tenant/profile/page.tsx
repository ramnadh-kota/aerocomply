"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { tenantApi, type TenantProfile } from "@/lib/api/tenant";
import { DEMO_TENANT_PROFILE } from "@/lib/demo/demoTenant";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

const INDUSTRIES = [
  { value: "AIRCRAFT", label: "Fixed-Wing Aircraft Operations / Commercial Airline" },
  { value: "DRONE_UAV", label: "Drone / Unmanned Aircraft System (UAV/UAS)" },
  { value: "HELICOPTER", label: "Rotorcraft / Helicopter Operations" },
  { value: "EVTOL_AAM", label: "eVTOL / Advanced Air Mobility (AAM)" },
];

export default function TenantProfilePage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [profile, setProfile] = useState<TenantProfile | null>(
    isDemo ? DEMO_TENANT_PROFILE : null
  );
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [name, setName] = useState(isDemo ? DEMO_TENANT_PROFILE.name : "");
  const [industry, setIndustry] = useState(isDemo ? DEMO_TENANT_PROFILE.industry ?? "AIRCRAFT" : "AIRCRAFT");
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (isDemo) {
      setProfile(DEMO_TENANT_PROFILE);
      setName(DEMO_TENANT_PROFILE.name);
      setIndustry(DEMO_TENANT_PROFILE.industry ?? "AIRCRAFT");
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
      .getProfile(accessToken)
      .then((p) => {
        setProfile(p);
        setName(p.name);
        setIndustry(p.industry ?? "AIRCRAFT");
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [isDemo, isAuthenticated, accessToken]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    setSaveSuccess(false);

    if (!name.trim()) {
      setSaveError("Organization name cannot be empty.");
      return;
    }

    if (isDemo) {
      setSaving(true);
      setTimeout(() => {
        setProfile((prev) => (prev ? { ...prev, name, industry } : null));
        setSaving(false);
        setSaveSuccess(true);
      }, 400);
      return;
    }

    if (!accessToken) return;
    setSaving(true);
    try {
      const updated = await tenantApi.updateProfile(accessToken, { name, industry });
      setProfile(updated);
      setSaveSuccess(true);
    } catch (err) {
      setSaveError(normalizeApiError(err).message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Organization Profile" },
        ]}
        eyebrow="TENANT PROFILE"
        title="Organization Profile"
        subtitle="Manage your aerospace organization's legal name, industry sector, and contact identity."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/tenant/settings" className="ac-btn">
              Operational Defaults →
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
            <strong>DEMO MODE</strong> · Edits in demo mode simulate mutations in memory only.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!profile}
            emptyMessage="No profile found."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      {profile && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 24 }}>
          {/* Edit Form */}
          <div className="ac-card">
            <h2 className="ac-h2" style={{ marginBottom: 16 }}>
              Organization Details
            </h2>
            <form onSubmit={handleSave}>
              <div style={{ marginBottom: 16 }}>
                <label className="ac-label" style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>
                  Organization Legal Name *
                </label>
                <input
                  type="text"
                  className="ac-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={{ width: "100%" }}
                  required
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label className="ac-label" style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>
                  Aerospace Industry Sector
                </label>
                <select
                  className="ac-input"
                  value={industry}
                  onChange={(e) => setIndustry(e.target.value)}
                  style={{ width: "100%" }}
                >
                  {INDUSTRIES.map((ind) => (
                    <option key={ind.value} value={ind.value}>
                      {ind.label}
                    </option>
                  ))}
                </select>
                <p className="ac-text-sm" style={{ opacity: 0.7, marginTop: 4 }}>
                  Configures regulatory workflows and asset taxonomy across your workspace.
                </p>
              </div>

              {saveSuccess && (
                <div
                  style={{
                    padding: "8px 12px",
                    background: "rgba(16, 185, 129, 0.15)",
                    color: "var(--success, #10b981)",
                    borderRadius: 4,
                    marginBottom: 16,
                    fontSize: 13,
                  }}
                >
                  ✓ Organization profile updated successfully.
                </div>
              )}

              {saveError && (
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
                  ⚠ {saveError}
                </div>
              )}

              <button type="submit" className="ac-btn ac-btn-primary" disabled={saving}>
                {saving ? "Saving..." : "Save Changes"}
              </button>
            </form>
          </div>

          {/* Read-Only Governance & Platform Boundaries */}
          <div className="ac-card">
            <h2 className="ac-h2" style={{ marginBottom: 16 }}>
              Governance &amp; Identity
            </h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <div className="ac-eyebrow">ORGANIZATION ID</div>
                <div className="ac-mono" style={{ fontSize: 13, wordBreak: "break-all" }}>
                  {profile.id}
                </div>
              </div>

              <div>
                <div className="ac-eyebrow">TENANT STATUS</div>
                <div className="ac-flex ac-gap-2 ac-items-center" style={{ marginTop: 4 }}>
                  <StatusBadge
                    status={profile.status === "ACTIVE" ? "ACTIVE" : "STORED"}
                    label={profile.status}
                  />
                  <span style={{ fontSize: 12, opacity: 0.7 }}>(Managed by Platform Admin)</span>
                </div>
              </div>

              <div>
                <div className="ac-eyebrow">PRIMARY CONTACT</div>
                <div style={{ fontSize: 14, fontWeight: 500 }}>
                  {profile.primary_contact_name ?? "Not configured"}
                </div>
                <div className="ac-mono" style={{ fontSize: 12, opacity: 0.7 }}>
                  {profile.primary_contact_email ?? "No email"}
                </div>
              </div>

              <div>
                <div className="ac-eyebrow">ONBOARDING DATE</div>
                <div style={{ fontSize: 13 }}>
                  {new Date(profile.created_at).toLocaleDateString(undefined, {
                    year: "numeric",
                    month: "long",
                    day: "numeric",
                  })}
                </div>
              </div>

              <div
                style={{
                  marginTop: 12,
                  padding: "10px 12px",
                  background: "var(--bg-subtle, rgba(255, 255, 255, 0.03))",
                  border: "1px solid var(--border-color, #27272a)",
                  borderRadius: 6,
                  fontSize: 12,
                }}
              >
                <div style={{ fontWeight: 600, marginBottom: 2 }}>Platform Admin Boundary</div>
                <p style={{ margin: 0, opacity: 0.8 }}>
                  Tenant administrators cannot alter tenant lifecycle state (ACTIVE / SUSPENDED) or modify global commercial plans. For account adjustments, contact your KOTA Aerospace platform manager.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
