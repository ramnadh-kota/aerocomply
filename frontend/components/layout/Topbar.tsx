"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GlobalSearch } from "@/components/search/GlobalSearch";
import { ThemeToggle } from "@/components/layout/ThemeToggle";
import { organizations } from "@/lib/mock/organizations";
import { useRoleSim, simulatableRoles } from "@/lib/role-sim/RoleSimContext";
import { getRoleById } from "@/lib/mock/roles";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import { useSidebarDrawer } from "@/components/layout/SidebarDrawerContext";
import { PLATFORM_AI_NAME } from "@/lib/brand";
import { HelpPanel } from "@/components/onboarding/HelpPanel";
import { getProactiveAlerts, type AlertSeverity } from "@/lib/mock/ai/proactive";
import { useAlertState } from "@/lib/mock/ai/alertState";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";

// Same five-color status vocabulary as StatusBadge (components/status/
// StatusBadge.tsx) — never a second color mapping. Severity maps to the
// closest existing badge kind rather than inventing a new tone.
const SEVERITY_BADGE: Record<AlertSeverity, { status: "NON_COMPLIANT" | "REVIEW_REQUIRED" | "INSUFFICIENT_DATA" | "COMPLIANT"; label: string }> = {
  CRITICAL: { status: "NON_COMPLIANT", label: "Critical" },
  HIGH: { status: "REVIEW_REQUIRED", label: "High" },
  MEDIUM: { status: "INSUFFICIENT_DATA", label: "Medium" },
  LOW: { status: "COMPLIANT", label: "Low" },
};

export function Topbar() {
  const [orgId, setOrgId] = useState(organizations[0].id);
  const [notifOpen, setNotifOpen] = useState(false);
  const { roleId, setRoleId } = useRoleSim();
  const { addAuditEvent } = useMroState();
  const { toggle: toggleSidebar } = useSidebarDrawer();
  const { user, logout, isAuthenticated, sessionType, isReal, organizationName } = useSession();
  const { mode } = useDataMode();
  const activeRole = getRoleById(roleId);
  const router = useRouter();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const notifRef = useRef<HTMLDivElement | null>(null);
  const userMenuRef = useRef<HTMLDivElement | null>(null);
  // Computed fresh per render from live mock data — no separate
  // notifications store, so this can never drift from what Lisa reports
  // elsewhere (dashboard Daily Brief, AI console "Lisa noticed…" strip).
  // roleId passed through for relevance-only reordering (see
  // getProactiveAlerts() comment in lib/mock/ai/proactive.ts) — never hides
  // an alert, just nudges categories this simulated role acts on most
  // toward the top within the same severity band.
  const alerts = useMemo(() => getProactiveAlerts(roleId), [roleId]);
  const topAlerts = alerts.slice(0, 8);
  // Acknowledge/resolve is local, demo-only state (see lib/mock/ai/alertState.ts)
  // — the badge count only reflects alerts not yet marked resolved.
  const { statusFor, acknowledge, resolve } = useAlertState();
  const unresolvedCount = alerts.filter((a) => statusFor(a.id) !== "RESOLVED").length;

  useEffect(() => {
    if (!notifOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setNotifOpen(false);
    }
    function onPointerDown(e: MouseEvent) {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("mousedown", onPointerDown);
    };
  }, [notifOpen]);

  useEffect(() => {
    if (!userMenuOpen) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setUserMenuOpen(false);
    }
    function onPointerDown(e: MouseEvent) {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("mousedown", onPointerDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("mousedown", onPointerDown);
    };
  }, [userMenuOpen]);

  function changeRole(nextRoleId: string) {
    const nextRole = getRoleById(nextRoleId);
    setRoleId(nextRoleId);
    addAuditEvent({
      actor: "Prototype User",
      actorRole: "Role Simulation",
      action: "role_simulation.changed",
      objectType: "RoleSimulation",
      objectLabel: nextRole?.name ?? nextRoleId,
      previousState: activeRole?.name ?? null,
      newState: nextRole?.name ?? nextRoleId,
    });
  }

  function goToAlert(href: string) {
    setNotifOpen(false);
    router.push(href);
  }

  function handleSignOut() {
    setUserMenuOpen(false);
    logout();
    router.push("/login");
  }

  const displayName = user?.full_name || (sessionType === "DEMO" ? "KOTA Aerospace Demo User" : "Authenticated User");
  const initials = displayName
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("") || "AU";

  return (
    <header className="ac-topbar">
      <button className="ac-btn ac-menu-toggle" aria-label="Toggle navigation menu" onClick={toggleSidebar} style={{ padding: "8px 10px" }}>
        <span aria-hidden="true">☰</span>
      </button>
      <GlobalSearch />

      <div className="ac-flex ac-items-center ac-gap-4" style={{ marginLeft: "auto" }}>
        <Link href="/ai" className="ac-btn" style={{ padding: "6px 12px", fontSize: 13 }}>
          <span aria-hidden="true" style={{ marginRight: 6 }}>✦</span>
          Ask {PLATFORM_AI_NAME}
        </Link>
        <label className="ac-flex ac-items-center ac-gap-2 ac-text-sm" title="Prototype role simulation — permissions are not enforced">
          <span className="ac-text-muted">Viewing as</span>
          <select
            className="ac-input"
            style={{ width: 190, padding: "6px 10px" }}
            value={roleId}
            onChange={(e) => changeRole(e.target.value)}
            aria-label="View as role (prototype simulation)"
          >
            {simulatableRoles().map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          {roleId !== "role-org-admin" && (
            <button className="ac-btn" style={{ padding: "4px 8px", fontSize: 11 }} onClick={() => changeRole("role-org-admin")}>
              Reset
            </button>
          )}
        </label>

        <label className="ac-flex ac-items-center ac-gap-2 ac-text-sm">
          <span className="ac-text-muted">Org</span>
          <select
            className="ac-input"
            style={{ width: 200, padding: "6px 10px" }}
            value={orgId}
            onChange={(e) => setOrgId(e.target.value)}
            aria-label="Organization selector"
          >
            {organizations.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        </label>

        <ThemeToggle />

        <HelpPanel />

        <div ref={notifRef} style={{ position: "relative" }}>
          <button
            className="ac-btn"
            aria-label="Notifications"
            aria-haspopup="true"
            aria-expanded={notifOpen}
            onClick={() => setNotifOpen((v) => !v)}
            style={{ padding: "8px 10px", position: "relative" }}
          >
            <span aria-hidden="true">🔔</span>
            {unresolvedCount > 0 && (
              <span
                aria-hidden="true"
                style={{
                  position: "absolute",
                  top: 2,
                  right: 2,
                  minWidth: 16,
                  height: 16,
                  padding: "0 3px",
                  borderRadius: 8,
                  background: "var(--ac-status-non-compliant)",
                  color: "#fff",
                  fontSize: 10,
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  lineHeight: 1,
                }}
              >
                {unresolvedCount > 99 ? "99+" : unresolvedCount}
              </span>
            )}
          </button>
          {notifOpen && (
            <div className="ac-card" style={{ position: "absolute", right: 0, top: "calc(100% + 6px)", width: 340, maxHeight: 420, overflowY: "auto", zIndex: 50 }}>
              <p className="ac-eyebrow" style={{ marginBottom: 8 }}>
                {PLATFORM_AI_NAME}&apos;s Alerts ({unresolvedCount} open)
              </p>
              {topAlerts.length === 0 ? (
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No open alerts from current fleet data.</p>
              ) : (
                <div className="ac-flex ac-flex-col ac-gap-2">
                  {topAlerts.map((a) => {
                    const badge = SEVERITY_BADGE[a.severity];
                    const alertStatus = statusFor(a.id);
                    const handled = alertStatus !== "OPEN";
                    return (
                      <div
                        key={a.id}
                        className="ac-card"
                        style={{ padding: "8px 10px", opacity: handled ? 0.55 : 1 }}
                      >
                        <button
                          onClick={() => goToAlert(a.href)}
                          style={{ textAlign: "left", cursor: "pointer", width: "100%", background: "none", border: "none", padding: 0 }}
                        >
                          <div className="ac-flex ac-justify-between ac-items-center" style={{ gap: 8 }}>
                            <span className="ac-text-sm" style={{ fontWeight: 600, textDecoration: alertStatus === "RESOLVED" ? "line-through" : undefined }}>
                              {a.title}
                            </span>
                            <span className={`ac-badge ac-badge-${badge.status.toLowerCase()}`} style={{ flexShrink: 0 }}>
                              <span className="ac-badge-dot" aria-hidden="true" />
                              {badge.label}
                            </span>
                          </div>
                          <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{a.message}</p>
                        </button>
                        <div className="ac-flex ac-items-center ac-gap-2" style={{ marginTop: 6 }}>
                          {handled ? (
                            <span className="ac-text-sm ac-text-muted">
                              {alertStatus === "ACKNOWLEDGED" ? "Acknowledged" : "Resolved"} (local only)
                            </span>
                          ) : (
                            <>
                              <button className="ac-btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => acknowledge(a.id)}>
                                Acknowledge
                              </button>
                              <button className="ac-btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => resolve(a.id)}>
                                Resolve
                              </button>
                            </>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
              {alerts.length > topAlerts.length && (
                <p className="ac-text-sm ac-text-muted" style={{ margin: "8px 0 0" }}>
                  +{alerts.length - topAlerts.length} more — ask {PLATFORM_AI_NAME} for the full list.
                </p>
              )}
              <Link
                href="/notifications"
                className="ac-text-sm"
                style={{ display: "block", textAlign: "center", marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--ac-border)" }}
                onClick={() => setNotifOpen(false)}
              >
                View all notifications →
              </Link>
            </div>
          )}
        </div>

        <div ref={userMenuRef} style={{ position: "relative" }}>
          <button
            type="button"
            className="ac-flex ac-items-center ac-gap-2"
            aria-label="User menu"
            aria-expanded={userMenuOpen}
            aria-haspopup="menu"
            onClick={() => setUserMenuOpen((v) => !v)}
            style={{
              background: "transparent",
              border: "1px solid var(--ac-border)",
              borderRadius: "999px",
              padding: "6px 10px",
              cursor: "pointer",
              color: "var(--ac-text-primary)",
            }}
          >
            <span
              aria-hidden="true"
              style={{
                width: 28,
                height: 28,
                borderRadius: "50%",
                background: "var(--ac-bg-surface-hover)",
                border: "1px solid var(--ac-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {initials}
            </span>
            <span className="ac-text-sm">{displayName}</span>
            <span aria-hidden="true" style={{ fontSize: 11 }}>▼</span>
          </button>

          {userMenuOpen && (
            <div
              className="ac-card"
              role="menu"
              aria-label="User account menu"
              style={{ position: "absolute", right: 0, top: "calc(100% + 8px)", minWidth: 220, zIndex: 60, padding: 0 }}
            >
              <button type="button" role="menuitem" className="ac-nav-link" style={{ width: "100%", border: "none", textAlign: "left" }} onClick={() => { setUserMenuOpen(false); router.push("/settings"); }}>
                Profile
              </button>
              <button type="button" role="menuitem" className="ac-nav-link" style={{ width: "100%", border: "none", textAlign: "left" }} onClick={() => { setUserMenuOpen(false); router.push("/settings"); }}>
                My Preferences
              </button>
              <button type="button" role="menuitem" className="ac-nav-link" style={{ width: "100%", border: "none", textAlign: "left" }} onClick={() => { setUserMenuOpen(false); router.push("/organization"); }}>
                Organization Settings
              </button>
              <button type="button" role="menuitem" className="ac-nav-link" style={{ width: "100%", border: "none", textAlign: "left" }} onClick={() => { setUserMenuOpen(false); router.push("/settings"); }}>
                Security
              </button>
              <button type="button" role="menuitem" className="ac-nav-link" style={{ width: "100%", border: "none", textAlign: "left" }} onClick={() => { setUserMenuOpen(false); router.push("/workspace"); }}>
                Workspace / Organization
              </button>
              <div style={{ borderTop: "1px solid var(--ac-border)", marginTop: 4 }} />
              <button type="button" role="menuitem" className="ac-nav-link" style={{ width: "100%", border: "none", textAlign: "left", color: "var(--ac-status-non-compliant)" }} onClick={handleSignOut}>
                Sign Out
              </button>
              {isAuthenticated && (
                <div className="ac-text-sm ac-text-muted" style={{ padding: "8px 12px 10px", borderTop: "1px solid var(--ac-border)", textTransform: "uppercase", letterSpacing: 0.5, fontSize: 11 }}>
                  <div>{isReal ? "REAL ENVIRONMENT · LIVE API DATA" : "DEMO ENVIRONMENT · SYNTHETIC DATA"}</div>
                  {organizationName && (
                    <div style={{ textTransform: "none", marginTop: 4, fontWeight: 600, color: "var(--ac-text-primary)" }}>
                      {organizationName}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
