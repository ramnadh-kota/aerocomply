"use client";

import { type ReactNode, useState } from "react";
import { DroneOpsSidebar } from "./DroneOpsSidebar";

// ─────────────────────────────────────────────────────────────────────────────
// DroneOpsLayout — the full-screen operational shell.
//
// This replaces the standard .ac-shell layout for drone-ops routes:
// - No standard .ac-sidebar (main app sidebar is hidden within drone-ops)
// - No .ac-topbar (the OperationsTopbar lives inside the content area)
// - Full viewport — map and dashboard panels need every pixel
//
// Mobile: sidebar slides in as a drawer (same pattern as the main app sidebar).
// ─────────────────────────────────────────────────────────────────────────────

interface DroneOpsLayoutProps {
  children: ReactNode;
}

export function DroneOpsLayout({ children }: DroneOpsLayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="ac-drone-ops-shell">
      {/* Mobile backdrop */}
      {sidebarOpen && (
        <div
          className="ac-drone-ops-sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar — always visible on desktop, drawer on mobile */}
      <div className={`ac-drone-ops-sidebar-wrapper${sidebarOpen ? " open" : ""}`}>
        <DroneOpsSidebar onNav={() => setSidebarOpen(false)} />
      </div>

      {/* Main content area */}
      <div className="ac-drone-ops-content">
        {/* Mobile menu toggle */}
        <button
          className="ac-drone-ops-menu-toggle"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open Drone Operations menu"
          aria-expanded={sidebarOpen}
        >
          <span aria-hidden="true">☰</span>
          <span style={{ fontSize: 11, marginLeft: 4 }}>DRONE OPS</span>
        </button>

        {children}
      </div>
    </div>
  );
}
