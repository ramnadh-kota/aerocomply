"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRoleSim, NAV_MODULE_MAP } from "@/lib/role-sim/RoleSimContext";
import { useSidebarDrawer } from "@/components/layout/SidebarDrawerContext";
import { Logo } from "@/components/branding/Logo";
import { useSession } from "@/lib/auth/SessionContext";

export interface NavItem {
  href: string;
  label: string;
  glyph: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

// M21.2 — regrouped from the prior 5 tenant groups (Overview/Fleet/
// Compliance/Maintenance/Governance) into 7 groups that follow the real
// aerospace operational workflow (Operations -> Assets -> MRO ->
// Inspection & Evidence -> Compliance -> Resources -> Administration),
// adapted to the routes that actually exist in this repo (per
// docs/M21_PRODUCT_UI_UX_AUDIT.md §2/§6) rather than a generic template.
// No routes were added or removed from the app; items were only moved
// between groups (plus three previously-orphaned routes that had no nav
// entry at all — see M21_2_REPORT.md §B — were given one). Dynamic detail
// routes (/drones/[id], /aircraft/[id], /findings/[id], etc.) are
// deliberately NOT listed here; they are reached contextually from their
// list pages, per the same audit's Phase-2 guidance.
export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Operations",
    items: [
      { href: "/dashboard", label: "Dashboard", glyph: "◧" },
      { href: "/executive", label: "Executive", glyph: "◆" },
      { href: "/notifications", label: "Notifications", glyph: "🔔" },
      { href: "/pilot", label: "Pilot Workflow", glyph: "▶" },
      { href: "/maintenance/control-center", label: "Maintenance Control Center", glyph: "◈" },
      { href: "/maintenance/control-tower", label: "Control Tower", glyph: "◉" },
      { href: "/maintenance/hangar", label: "Hangar Floor", glyph: "⛭" },
      { href: "/automation", label: "Automation Queue", glyph: "⚙" },
      { href: "/ai", label: "AI Command Center", glyph: "✦" },
    ],
  },
  {
    label: "Assets",
    items: [
      { href: "/fleet/health", label: "Fleet Health", glyph: "♥" },
      { href: "/aircraft", label: "Aircraft", glyph: "✈" },
      { href: "/drones", label: "Drones", glyph: "◆" },
      { href: "/engines", label: "Engines", glyph: "◎" },
      { href: "/components", label: "Components", glyph: "▤" },
      { href: "/facilities", label: "Facilities", glyph: "⌂" },
    ],
  },
  {
    label: "MRO",
    items: [
      { href: "/maintenance/work-orders", label: "Work Orders", glyph: "☰" },
      { href: "/maintenance/tasks", label: "Tasks", glyph: "☑" },
      { href: "/maintenance/planning", label: "Planning", glyph: "◔" },
      { href: "/maintenance/projects", label: "Projects", glyph: "◈" },
      { href: "/maintenance/technicians", label: "Technicians", glyph: "👷" },
      { href: "/maintenance/operations", label: "Maintenance Operations", glyph: "◪" },
      { href: "/maintenance-program", label: "Maintenance Program", glyph: "▦" },
      { href: "/maintenance/discrepancies", label: "Discrepancy Intelligence", glyph: "⚡" },
      { href: "/maintenance/defects", label: "Defects", glyph: "⚠" },
      { href: "/maintenance/deferred", label: "Deferred / MEL", glyph: "◑" },
      { href: "/maintenance/parts", label: "Parts", glyph: "⛭" },
      { href: "/maintenance/material-readiness", label: "Material Readiness", glyph: "▤" },
      { href: "/maintenance/release-readiness", label: "Release Readiness", glyph: "✓" },
      { href: "/maintenance/records", label: "Maintenance Records", glyph: "🗎" },
    ],
  },
  {
    label: "Inspection & Evidence",
    items: [
      { href: "/maintenance/inspections", label: "Inspections", glyph: "🔍" },
      { href: "/evidence", label: "Evidence", glyph: "▣" },
      { href: "/documents", label: "Documents", glyph: "🗎" },
    ],
  },
  {
    label: "Compliance",
    items: [
      { href: "/compliance", label: "AeroComply", glyph: "◆" },
      { href: "/regulations", label: "Regulations", glyph: "§" },
      { href: "/compliance/regulatory-register", label: "Regulatory Register", glyph: "§" },
      { href: "/assessments", label: "Assessments", glyph: "✓" },
      { href: "/assessment-intelligence", label: "Assessment Intelligence", glyph: "◆" },
      { href: "/compliance/pre-audit", label: "Pre-Audit", glyph: "✓" },
      { href: "/audit", label: "Audit Trail", glyph: "≡" },
      { href: "/data-import", label: "Data Import", glyph: "⇧" },
    ],
  },
  {
    label: "Resources",
    items: [
      { href: "/procurement", label: "Procurement", glyph: "◧" },
      { href: "/procurement/parts", label: "Parts Search", glyph: "⛭" },
      { href: "/procurement/cart", label: "My Cart", glyph: "▢" },
      { href: "/procurement/approvals", label: "Approvals", glyph: "✓" },
      { href: "/procurement/purchase-orders", label: "Purchase Orders", glyph: "🗎" },
      { href: "/procurement/vendors", label: "Vendor Intelligence", glyph: "◫" },
      { href: "/finance", label: "MRO Finance", glyph: "$" },
    ],
  },
  {
    label: "Administration",
    items: [
      { href: "/organization", label: "Organization", glyph: "◫" },
      { href: "/organization/users", label: "Users", glyph: "◔" },
      { href: "/organization/roles", label: "Roles", glyph: "◈" },
      { href: "/organization/plan", label: "Plan & Subscription", glyph: "◆" },
      { href: "/organization/readiness", label: "Pilot Readiness", glyph: "✓" },
      { href: "/reports", label: "Reports", glyph: "▦" },
      { href: "/workspace", label: "Workspace", glyph: "▢" },
      { href: "/integrations", label: "Integrations", glyph: "◫" },
      { href: "/settings", label: "Settings", glyph: "⚙" },
    ],
  },
];

// KOTA AEROSPACE PLATFORM CONTROL PLANE — the exclusive navigation for
// PLATFORM_ADMIN/PLATFORM_STAFF (see isPlatformUser below). Deliberately a
// separate, flat list rather than tenant NAV_GROUPS + an appended
// "Platform" section: a platform operator administers organizations,
// product catalog, plans, and platform governance, never a specific
// tenant's operational workflows (aircraft, maintenance, evidence, etc.).
export const PLATFORM_NAV_GROUPS: NavGroup[] = [
  {
    label: "Platform Control Plane",
    items: [
      { href: "/platform/organizations", label: "Organizations", glyph: "⛨" },
      { href: "/platform/product-catalog", label: "Product Catalog", glyph: "▤" },
      { href: "/platform/plans", label: "Plans", glyph: "◈" },
      { href: "/platform/audit", label: "Audit / Activity", glyph: "≡" },
      { href: "/platform/approvals", label: "Approvals", glyph: "✓" },
      { href: "/platform/monitoring", label: "Monitoring & Health", glyph: "♥" },
    ],
  },
];

export function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard" || href === "/organization") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const pathname = usePathname();
  const { accessFor } = useRoleSim();
  const { open, close } = useSidebarDrawer();
  const { user } = useSession();
  // Platform Admin / Platform Staff are real backend roles (never a
  // role-sim demo role) that hold zero tenant permissions on the backend
  // (see app/core/permissions.py's ROLE_PERMISSIONS) -- they can never act
  // on tenant data no matter what this sidebar shows. This check only
  // decides which nav *group* renders: a platform user sees the Platform
  // Control Plane exclusively, not the tenant application nav appended
  // alongside it, because a platform operator's job is administering the
  // platform (organizations, product catalog, plans, audit), never
  // operating a specific tenant's fleet/maintenance/compliance workflows.
  // The backend independently enforces PLATFORM_MANAGE on every
  // /platform/* call regardless of what's shown here.
  const isPlatformUser = user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;
  const groups = isPlatformUser ? PLATFORM_NAV_GROUPS : NAV_GROUPS;

  return (
    <>
      <div className={`ac-sidebar-backdrop${open ? " open" : ""}`} onClick={close} aria-hidden="true" />
      <nav className={`ac-sidebar${open ? " open" : ""}`} aria-label="Primary navigation">
      <div style={{ padding: "18px 20px 12px" }}>
        <Link
          href={isPlatformUser ? "/platform/organizations" : "/dashboard"}
          style={{ display: "flex", alignItems: "center" }}
          onClick={close}
        >
          <Logo height={30} />
        </Link>
      </div>

      <div style={{ flex: 1, overflowY: "auto", paddingBottom: 8 }}>
        {groups.map((group, gi) => (
          <div key={group.label}>
            {gi > 0 && <p className="ac-nav-section-label">{group.label}</p>}
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {group.items.map((item) => {
                const navModule = NAV_MODULE_MAP[item.href];
                const level = navModule ? accessFor(navModule) : "APPROVE";
                const denied = level === "NONE";
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={`ac-nav-link${isActive(pathname, item.href) ? " active" : ""}`}
                      aria-current={isActive(pathname, item.href) ? "page" : undefined}
                      aria-disabled={denied || undefined}
                      title={denied ? "Not available for the simulated role (prototype only — not enforced)" : undefined}
                      style={denied ? { opacity: 0.4 } : undefined}
                      onClick={(e) => {
                        if (denied) e.preventDefault();
                        else close();
                      }}
                    >
                      <span aria-hidden="true" style={{ width: 16, textAlign: "center" }}>
                        {item.glyph}
                      </span>
                      {item.label}
                      {denied && (
                        <span aria-hidden="true" style={{ marginLeft: "auto", fontSize: 11 }}>
                          🔒
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className="ac-prototype-banner" role="note">
        <span aria-hidden="true">⚠</span>
M0.6 Prototype · Mock Data
      </div>
      </nav>
    </>
  );
}
