"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRoleSim, NAV_MODULE_MAP } from "@/lib/role-sim/RoleSimContext";
import { useSidebarDrawer } from "@/components/layout/SidebarDrawerContext";
import { PLATFORM_NAME } from "@/lib/brand";

interface NavItem {
  href: string;
  label: string;
  glyph: string;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", glyph: "◧" },
      { href: "/pilot", label: "Pilot Workflow", glyph: "▶" },
      { href: "/executive", label: "Executive", glyph: "◆" },
      { href: "/finance", label: "MRO Finance", glyph: "$" },
      { href: "/procurement", label: "Procurement", glyph: "◧" },
      { href: "/procurement/parts", label: "Parts Search", glyph: "⛭" },
      { href: "/procurement/cart", label: "My Cart", glyph: "▢" },
      { href: "/procurement/approvals", label: "Approvals", glyph: "✓" },
      { href: "/procurement/purchase-orders", label: "Purchase Orders", glyph: "🗎" },
      { href: "/procurement/vendors", label: "Vendor Intelligence", glyph: "◫" },
      { href: "/ai", label: "AI Command Center", glyph: "✦" },
    ],
  },
  {
    label: "Fleet",
    items: [
      { href: "/aircraft", label: "Aircraft", glyph: "✈" },
      { href: "/engines", label: "Engines", glyph: "◎" },
      { href: "/components", label: "Components", glyph: "▤" },
    ],
  },
  {
    label: "Compliance",
    items: [
      { href: "/compliance", label: "AeroComply", glyph: "◆" },
      { href: "/regulations", label: "Regulations", glyph: "§" },
      { href: "/assessments", label: "Assessments", glyph: "✓" },
      { href: "/evidence", label: "Evidence", glyph: "▣" },
    ],
  },
  {
    label: "Maintenance",
    items: [
      { href: "/maintenance/control-center", label: "Maintenance Control Center", glyph: "◈" },
      { href: "/maintenance/control-tower", label: "Control Tower", glyph: "◉" },
      { href: "/maintenance/discrepancies", label: "Discrepancy Intelligence", glyph: "⚡" },
      { href: "/maintenance/operations", label: "Operations", glyph: "◪" },
      { href: "/maintenance/hangar", label: "Hangar Floor", glyph: "⛭" },
      { href: "/maintenance/planning", label: "Planning", glyph: "◔" },
      { href: "/maintenance/material-readiness", label: "Material Readiness", glyph: "▤" },
      { href: "/maintenance/projects", label: "Projects", glyph: "◈" },
      { href: "/maintenance/work-orders", label: "Work Orders", glyph: "☰" },
      { href: "/maintenance/inspections", label: "Inspections", glyph: "🔍" },
      { href: "/maintenance/technicians", label: "Technicians", glyph: "👷" },
      { href: "/maintenance/tasks", label: "Tasks", glyph: "☑" },
      { href: "/maintenance/defects", label: "Defects", glyph: "⚠" },
      { href: "/maintenance/parts", label: "Parts", glyph: "⛭" },
      { href: "/maintenance/records", label: "Records", glyph: "🗎" },
    ],
  },
  {
    label: "Governance",
    items: [
      { href: "/audit", label: "Audit Trail", glyph: "≡" },
      { href: "/reports", label: "Reports", glyph: "▦" },
      { href: "/organization", label: "Organization", glyph: "◫" },
      { href: "/organization/users", label: "Users", glyph: "◔" },
      { href: "/organization/roles", label: "Roles", glyph: "◈" },
      { href: "/workspace", label: "Workspace", glyph: "▢" },
      { href: "/settings", label: "Settings", glyph: "⚙" },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard" || href === "/organization") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const pathname = usePathname();
  const { accessFor } = useRoleSim();
  const { open, close } = useSidebarDrawer();

  return (
    <>
      <div className={`ac-sidebar-backdrop${open ? " open" : ""}`} onClick={close} aria-hidden="true" />
      <nav className={`ac-sidebar${open ? " open" : ""}`} aria-label="Primary navigation">
      <div style={{ padding: "18px 20px 12px" }}>
        <Link href="/dashboard" style={{ display: "flex", alignItems: "center", gap: 8 }} onClick={close}>
          <span
            aria-hidden="true"
            style={{
              width: 26,
              height: 26,
              borderRadius: 6,
              background: "var(--ac-accent)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 700,
              fontSize: 13,
              color: "white",
            }}
          >
            K
          </span>
          <span style={{ fontWeight: 700, fontSize: 14, letterSpacing: "-0.01em" }}>{PLATFORM_NAME}</span>
        </Link>
      </div>

      <div style={{ flex: 1, overflowY: "auto", paddingBottom: 8 }}>
        {NAV_GROUPS.map((group, gi) => (
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
