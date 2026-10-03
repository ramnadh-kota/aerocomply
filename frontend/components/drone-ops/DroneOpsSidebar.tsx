"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Logo } from "@/components/branding/Logo";
import { useSidebarDrawer } from "@/components/layout/SidebarDrawerContext";

// ─────────────────────────────────────────────────────────────────────────────
// Drone Operations navigation items — 11 operational + 3 workspace items.
// Matches the structure in the master prompt §3.
// Routes are prefixed /drone-ops/* and gated by DRONE_UAV suite at the
// layout level (DroneOpsLayout/SuiteGuard) — individual items here don't
// need their own guards.
// ─────────────────────────────────────────────────────────────────────────────

interface DroneOpsNavItem {
  href: string;
  label: string;
  icon: string;
  implemented: boolean; // false → renders with a "coming soon" indicator
  badge?: string;       // optional live count badge
}

interface DroneOpsNavGroup {
  label: string;
  items: DroneOpsNavItem[];
}

const DRONE_OPS_NAV: DroneOpsNavGroup[] = [
  {
    label: "DRONE OPERATIONS",
    items: [
      { href: "/drone-ops/overview",      label: "Operations Overview",      icon: "◧",  implemented: true },
      { href: "/drone-ops/live-map",      label: "Live Fleet Map",           icon: "◉",  implemented: true },
      { href: "/drone-ops/missions",      label: "Missions & Routes",        icon: "◔",  implemented: true },
      { href: "/drone-ops/telemetry",     label: "Connectivity & Telemetry", icon: "⇄",  implemented: true },
      { href: "/drone-ops/health",        label: "Fleet Health & HUMS",      icon: "♥",  implemented: true },
      { href: "/drone-ops/copilot",       label: "LISA Copilot",             icon: "✦",  implemented: true },
      { href: "/drone-ops/alerts",        label: "Alerts & Events",          icon: "🔔", implemented: true },
      { href: "/drone-ops/maintenance",   label: "Maintenance",              icon: "⛭",  implemented: false },
      { href: "/drone-ops/airspace",      label: "Airspace & Compliance",    icon: "§",  implemented: false },
      { href: "/drone-ops/analytics",     label: "Analytics & Reports",      icon: "▦",  implemented: false },
      { href: "/drone-ops/integrations",  label: "Drone Integrations",       icon: "◫",  implemented: false },
    ],
  },
  {
    label: "WORKSPACE",
    items: [
      { href: "/tenant/profile",       label: "Organization Settings", icon: "◫", implemented: true },
      { href: "/tenant/users",         label: "Team & Permissions",    icon: "👥", implemented: true },
      { href: "/tenant/subscription",  label: "Subscription & Usage",  icon: "◆", implemented: true },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/drone-ops/overview") return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

interface DroneOpsSidebarProps {
  /** Passed from the drawer context to allow mobile close-on-nav */
  onNav?: () => void;
}

export function DroneOpsSidebar({ onNav }: DroneOpsSidebarProps) {
  const pathname = usePathname();

  return (
    <nav
      className="ac-drone-ops-sidebar"
      aria-label="Drone Operations navigation"
    >
      {/* Logo / back-to-platform link */}
      <div className="ac-drone-ops-sidebar-header">
        <Link href="/dashboard" className="ac-drone-ops-logo-link" title="Back to Kota Platform" onClick={onNav}>
          <Logo height={26} />
        </Link>
        <span className="ac-drone-ops-sidebar-module-label">Drone Ops</span>
      </div>

      {/* Navigation groups */}
      <div className="ac-drone-ops-sidebar-scroll">
        {DRONE_OPS_NAV.map((group) => (
          <div key={group.label} className="ac-drone-ops-nav-group">
            <p className="ac-drone-ops-nav-group-label">{group.label}</p>
            <ul className="ac-drone-ops-nav-list">
              {group.items.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={`ac-drone-ops-nav-link${active ? " active" : ""}${!item.implemented ? " unimplemented" : ""}`}
                      aria-current={active ? "page" : undefined}
                      title={!item.implemented ? "Coming in a future milestone" : undefined}
                      onClick={onNav}
                    >
                      <span className="ac-drone-ops-nav-icon" aria-hidden="true">
                        {item.icon}
                      </span>
                      <span className="ac-drone-ops-nav-label">{item.label}</span>
                      {!item.implemented && (
                        <span className="ac-drone-ops-nav-soon" aria-label="Coming soon">
                          SOON
                        </span>
                      )}
                      {item.badge && (
                        <span className="ac-drone-ops-nav-badge" aria-label={`${item.badge} items`}>
                          {item.badge}
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

      {/* Back to main platform */}
      <div className="ac-drone-ops-sidebar-footer">
        <Link href="/dashboard" className="ac-drone-ops-back-link" onClick={onNav}>
          <span aria-hidden="true">←</span>
          Back to Kota Platform
        </Link>
      </div>
    </nav>
  );
}
