"use client";

import { useState } from "react";
import { GlobalSearch } from "@/components/search/GlobalSearch";
import { organizations } from "@/lib/mock/organizations";

export function Topbar() {
  const [orgId, setOrgId] = useState(organizations[0].id);
  const [notifOpen, setNotifOpen] = useState(false);

  return (
    <header className="ac-topbar">
      <GlobalSearch />

      <div className="ac-flex ac-items-center ac-gap-4" style={{ marginLeft: "auto" }}>
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

        <div style={{ position: "relative" }}>
          <button
            className="ac-btn"
            aria-label="Notifications"
            aria-haspopup="true"
            aria-expanded={notifOpen}
            onClick={() => setNotifOpen((v) => !v)}
            style={{ padding: "8px 10px" }}
          >
            <span aria-hidden="true">🔔</span>
          </button>
          {notifOpen && (
            <div className="ac-card" style={{ position: "absolute", right: 0, top: "calc(100% + 6px)", width: 280, zIndex: 50 }}>
              <p className="ac-eyebrow" style={{ marginBottom: 8 }}>
                Notifications (mock)
              </p>
              <p className="ac-text-sm">3 assessments require engineering review.</p>
              <hr className="ac-divider" />
              <p className="ac-text-sm">New evidence added to AD-2026-001 / VT-ABC.</p>
            </div>
          )}
        </div>

        <div className="ac-flex ac-items-center ac-gap-2">
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
            PN
          </span>
          <span className="ac-text-sm">Priya Nair</span>
        </div>
      </div>
    </header>
  );
}
