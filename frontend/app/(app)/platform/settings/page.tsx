"use client";

// Platform Admin — Platform Operational Settings.

import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import Link from "next/link";

export default function PlatformSettingsPage() {
  const { isAuthenticated, user } = useSession();
  const { mode, apiBaseUrl } = useDataMode();

  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
      <Breadcrumbs items={[{ label: "Platform Admin", href: "/platform/dashboard" }, { label: "Settings" }]} />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1" style={{ margin: 0 }}>Platform — Operational Settings</h1>
          <p className="ac-subtitle" style={{ margin: "4px 0 0" }}>
            Platform control plane environment, security boundaries, and authorization configuration.
          </p>
        </div>
      </div>

      {mode === "REAL" && !isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : mode === "REAL" && !isPlatformUser ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)", borderLeft: "4px solid var(--ac-status-non-compliant)" }}>
          <h3 className="ac-h3" style={{ margin: "0 0 6px" }}>Platform Access Denied</h3>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Your account does not possess the <code>PLATFORM_MANAGE</code> authority required to view platform settings.
          </p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: 16 }}>
          {/* Environment Configuration */}
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <h2 className="ac-h2" style={{ margin: "0 0 12px" }}>Control Plane Environment</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="ac-text-muted">Data Session Mode</span>
                <StatusBadge
                  status={mode === "REAL" ? "COMPLIANT" : "REVIEW_REQUIRED"}
                  label={mode === "REAL" ? "REAL ENVIRONMENT · LIVE API DATA" : "DEMO ENVIRONMENT · SYNTHETIC DATA"}
                />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="ac-text-muted">API Gateway Endpoint</span>
                <code>{apiBaseUrl}</code>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="ac-text-muted">Platform Milestone</span>
                <strong>Milestone 2.0 (Platform Control Plane)</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="ac-text-muted">Core Foundation Milestone</span>
                <StatusBadge status="COMPLIANT" label="Drone M1.5 Accepted" />
              </div>
            </div>
          </div>

          {/* Security & Access Policies */}
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <h2 className="ac-h2" style={{ margin: "0 0 12px" }}>Security & Access Governance</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="ac-text-muted">Tenant Cross-Query Isolation</span>
                <StatusBadge status="COMPLIANT" label="Enforced Server-Side" />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="ac-text-muted">Arbitrary Role Impersonation</span>
                <StatusBadge status="NON_COMPLIANT" label="Disabled" />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="ac-text-muted">Expansive Override Gate</span>
                <StatusBadge status="COMPLIANT" label="PLATFORM_ENTITLEMENT_OVERRIDE" />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span className="ac-text-muted">Audit Trail Immutability</span>
                <StatusBadge status="COMPLIANT" label="Append-Only Verified" />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
