"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  href: string;
  label: string;
  glyph: string;
}

const PRIMARY_NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", glyph: "◧" },
  { href: "/aircraft", label: "Aircraft", glyph: "✈" },
  { href: "/engines", label: "Engines", glyph: "◎" },
  { href: "/components", label: "Components", glyph: "▤" },
  { href: "/regulations", label: "Regulations", glyph: "§" },
  { href: "/assessments", label: "Assessments", glyph: "✓" },
  { href: "/evidence", label: "Evidence", glyph: "▣" },
  { href: "/audit", label: "Audit Trail", glyph: "≡" },
];

const MAINTENANCE_NAV: NavItem[] = [
  { href: "/maintenance/projects", label: "Projects", glyph: "◈" },
  { href: "/maintenance/work-orders", label: "Work Orders", glyph: "☰" },
  { href: "/maintenance/technicians", label: "Technician Workbench", glyph: "👷" },
  { href: "/maintenance/tasks", label: "Tasks / Checklists", glyph: "☑" },
  { href: "/maintenance/defects", label: "Defects", glyph: "⚠" },
  { href: "/maintenance/parts", label: "Parts & Inventory", glyph: "⛭" },
  { href: "/maintenance/records", label: "Maintenance Records", glyph: "🗎" },
];

const WORKSPACE_NAV: NavItem[] = [
  { href: "/workspace", label: "Workspace", glyph: "▢" },
  { href: "/organization", label: "Organization", glyph: "◫" },
  { href: "/settings", label: "Settings", glyph: "⚙" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === "/dashboard";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav className="ac-sidebar" aria-label="Primary navigation">
      <div style={{ padding: "18px 20px 12px" }}>
        <Link href="/dashboard" style={{ display: "flex", alignItems: "center", gap: 8 }}>
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
            A
          </span>
          <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em" }}>AeroComply</span>
        </Link>
      </div>

      <div style={{ flex: 1, overflowY: "auto", paddingBottom: 8 }}>
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {PRIMARY_NAV.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className={`ac-nav-link${isActive(pathname, item.href) ? " active" : ""}`}
                aria-current={isActive(pathname, item.href) ? "page" : undefined}
              >
                <span aria-hidden="true" style={{ width: 16, textAlign: "center" }}>
                  {item.glyph}
                </span>
                {item.label}
              </Link>
            </li>
          ))}
        </ul>

        <p className="ac-nav-section-label">Maintenance</p>
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {MAINTENANCE_NAV.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className={`ac-nav-link${isActive(pathname, item.href) ? " active" : ""}`}
                aria-current={isActive(pathname, item.href) ? "page" : undefined}
              >
                <span aria-hidden="true" style={{ width: 16, textAlign: "center" }}>
                  {item.glyph}
                </span>
                {item.label}
              </Link>
            </li>
          ))}
        </ul>

        <p className="ac-nav-section-label">Manage</p>
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {WORKSPACE_NAV.map((item) => (
            <li key={item.href}>
              <Link
                href={item.href}
                className={`ac-nav-link${isActive(pathname, item.href) ? " active" : ""}`}
                aria-current={isActive(pathname, item.href) ? "page" : undefined}
              >
                <span aria-hidden="true" style={{ width: 16, textAlign: "center" }}>
                  {item.glyph}
                </span>
                {item.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>

      <div className="ac-prototype-banner" role="note">
        <span aria-hidden="true">⚠</span>
M0.5 Prototype · Mock Data
      </div>
    </nav>
  );
}
