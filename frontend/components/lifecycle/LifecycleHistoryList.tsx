// M17.2C — reusable installation-history list for a single serialized
// Battery or Component. Asset-generic by design (not Drone-specific): any
// future caller (Aircraft/Helicopter/eVTOL components) can reuse this the
// same way, since it only depends on the shape of one installation span,
// not on Drone at all. Purely presentational -- renders exactly the
// installed_at/removed_at/asset_id fields the backend returns; never
// computes or infers current state (see the "not authoritative" note on
// each entry).

import type { BatteryInstallationResponse, ComponentInstallationResponse } from "@/lib/api/drones";

type InstallationSpan = BatteryInstallationResponse | ComponentInstallationResponse;

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function LifecycleHistoryList({
  installations,
  emptyMessage = "No lifecycle history recorded yet.",
}: {
  installations: InstallationSpan[];
  emptyMessage?: string;
}) {
  if (installations.length === 0) {
    return (
      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
        {emptyMessage}
      </p>
    );
  }

  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 10 }}>
      {installations.map((span) => (
        <li key={span.id} className="ac-card" style={{ padding: 10 }}>
          <div className="ac-text-sm" style={{ fontWeight: 600 }}>
            Installed
          </div>
          <div className="ac-text-sm ac-text-muted" style={{ marginTop: 2 }}>
            Asset: <span className="ac-mono" style={{ wordBreak: "break-all" }}>{span.asset_id}</span>
          </div>
          <div className="ac-text-sm ac-text-muted">{formatTimestamp(span.installed_at)}</div>

          {span.removed_at ? (
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid var(--ac-border)" }}>
              <div className="ac-text-sm" style={{ fontWeight: 600 }}>
                Removed
              </div>
              <div className="ac-text-sm ac-text-muted">{formatTimestamp(span.removed_at)}</div>
            </div>
          ) : (
            <div className="ac-text-sm" style={{ marginTop: 8, opacity: 0.7 }}>
              Currently installed (not yet removed).
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
