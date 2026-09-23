"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { tenantApi, type TenantSettings } from "@/lib/api/tenant";
import { DEMO_TENANT_SETTINGS } from "@/lib/demo/demoTenant";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

export default function TenantSettingsPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [settings, setSettings] = useState<TenantSettings | null>(
    isDemo ? DEMO_TENANT_SETTINGS : null
  );
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [timezone, setTimezone] = useState(isDemo ? DEMO_TENANT_SETTINGS.timezone : "UTC");
  const [operationalMode, setOperationalMode] = useState(
    isDemo ? DEMO_TENANT_SETTINGS.operational_mode : "STANDARD"
  );
  const [defaultAssetType, setDefaultAssetType] = useState(
    isDemo ? DEMO_TENANT_SETTINGS.default_asset_type : "AIRCRAFT"
  );
  const [notificationEmail, setNotificationEmail] = useState(
    isDemo ? DEMO_TENANT_SETTINGS.notification_email ?? "" : ""
  );

  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (isDemo) {
      setSettings(DEMO_TENANT_SETTINGS);
      setTimezone(DEMO_TENANT_SETTINGS.timezone);
      setOperationalMode(DEMO_TENANT_SETTINGS.operational_mode);
      setDefaultAssetType(DEMO_TENANT_SETTINGS.default_asset_type);
      setNotificationEmail(DEMO_TENANT_SETTINGS.notification_email ?? "");
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
      .getSettings(accessToken)
      .then((s) => {
        setSettings(s);
        setTimezone(s.timezone);
        setOperationalMode(s.operational_mode);
        setDefaultAssetType(s.default_asset_type);
        setNotificationEmail(s.notification_email ?? "");
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [isDemo, isAuthenticated, accessToken]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaveError(null);
    setSaveSuccess(false);

    if (isDemo) {
      setSaving(true);
      setTimeout(() => {
        setSettings((prev) =>
          prev
            ? {
                ...prev,
                timezone,
                operational_mode: operationalMode,
                default_asset_type: defaultAssetType,
                notification_email: notificationEmail || null,
              }
            : null
        );
        setSaving(false);
        setSaveSuccess(true);
      }, 400);
      return;
    }

    if (!accessToken) return;
    setSaving(true);
    try {
      const updated = await tenantApi.updateSettings(accessToken, {
        timezone,
        operational_mode: operationalMode,
        default_asset_type: defaultAssetType,
        notification_email: notificationEmail || undefined,
      });
      setSettings(updated);
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
          { label: "Operational Settings" },
        ]}
        eyebrow="CONFIGURATION"
        title="Tenant Operational Settings"
        subtitle="Configure organization-level defaults for timezones, operational dispatch, and asset conventions."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/tenant/profile" className="ac-btn">
              ← Organization Profile
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
            <strong>DEMO MODE</strong> · Settings mutations are simulated in memory.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!settings}
            emptyMessage="No settings configured."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      {settings && (
        <div className="ac-card" style={{ maxWidth: 640 }}>
          <form onSubmit={handleSave}>
            <div style={{ marginBottom: 16 }}>
              <label className="ac-label" style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>
                Operational Timezone
              </label>
              <select
                className="ac-input"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                style={{ width: "100%" }}
              >
                <option value="UTC">UTC (Coordinated Universal Time)</option>
                <option value="UTC+05:30">UTC+05:30 (India Standard Time - IST)</option>
                <option value="UTC+00:00">UTC+00:00 (London / GMT)</option>
                <option value="UTC-05:00">UTC-05:00 (US Eastern Time - EST)</option>
                <option value="UTC-08:00">UTC-08:00 (US Pacific Time - PST)</option>
                <option value="UTC+08:00">UTC+08:00 (Singapore / Perth - SGT)</option>
              </select>
              <p className="ac-text-sm" style={{ opacity: 0.7, marginTop: 4 }}>
                Determines how flight logs, maintenance due dates, and work order deadlines are calculated.
              </p>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label className="ac-label" style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>
                Operational Workflow Mode
              </label>
              <select
                className="ac-input"
                value={operationalMode}
                onChange={(e) => setOperationalMode(e.target.value)}
                style={{ width: "100%" }}
              >
                <option value="STANDARD">Standard Aerospace (Flight Ops &amp; Scheduled Maintenance)</option>
                <option value="HIGH_VOLUME_MRO">High-Volume MRO Facility (Heavy Inspection Focus)</option>
                <option value="TACTICAL_DISPATCH">Tactical UAV/Drone Operations (Continuous Mission Dispatch)</option>
              </select>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label className="ac-label" style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>
                Default Asset Class
              </label>
              <select
                className="ac-input"
                value={defaultAssetType}
                onChange={(e) => setDefaultAssetType(e.target.value)}
                style={{ width: "100%" }}
              >
                <option value="AIRCRAFT">Fixed-Wing Aircraft</option>
                <option value="DRONE">Drone UAV / UAS</option>
                <option value="HELICOPTER">Rotorcraft / Helicopter</option>
                <option value="EVTOL">eVTOL / Advanced Air Mobility</option>
              </select>
            </div>

            <div style={{ marginBottom: 20 }}>
              <label className="ac-label" style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>
                Operations Notification Email
              </label>
              <input
                type="email"
                className="ac-input"
                value={notificationEmail}
                onChange={(e) => setNotificationEmail(e.target.value)}
                placeholder="ops@yourcompany.com"
                style={{ width: "100%" }}
              />
              <p className="ac-text-sm" style={{ opacity: 0.7, marginTop: 4 }}>
                Receives automated alerts for expiring airworthiness directives and work order releases.
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
                ✓ Settings updated and recorded to organization audit trail.
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
              {saving ? "Saving..." : "Save Settings"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
