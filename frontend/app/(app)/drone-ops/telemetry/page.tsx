"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { useSession } from "@/lib/auth/SessionContext";
import { TelemetryPanel } from "@/components/intelligence/TelemetryPanel";
import { dronesApi, type DroneResponse } from "@/lib/api/drones";
import Link from "next/link";

function TelemetryContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const rawAssetId = searchParams.get("assetId");
  const { accessToken } = useSession();
  const [drones, setDrones] = useState<DroneResponse[]>([]);
  const [loadingDrones, setLoadingDrones] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    dronesApi
      .listDrones(accessToken)
      .then((data) => setDrones(data))
      .catch(() => setDrones([]))
      .finally(() => setLoadingDrones(false));
  }, [accessToken]);

  const selectedAssetId = rawAssetId || (drones.length > 0 ? drones[0].id : null);
  const selectedDrone = drones.find((d) => d.id === selectedAssetId);

  return (
    <div style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto" }}>
      {/* Header with Asset Selector */}
      <header
        style={{
          marginBottom: "24px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <h1 style={{ fontSize: "24px", fontWeight: 600, color: "var(--ac-text-primary)", margin: 0 }}>
            Connectivity &amp; Telemetry
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--ac-text-muted)" }}>
            Live MAVLink telemetry stream, data quality indicators, and flight records.
          </p>
        </div>

        {/* Drone Selector Dropdown */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <label htmlFor="drone-select" style={{ fontSize: "13px", color: "var(--ac-text-secondary)", fontWeight: 500 }}>
            Select Asset:
          </label>
          <select
            id="drone-select"
            value={selectedAssetId ?? ""}
            onChange={(e) => router.push(`/drone-ops/telemetry?assetId=${e.target.value}`)}
            style={{
              padding: "6px 12px",
              background: "var(--ac-bg-card)",
              color: "var(--ac-text-primary)",
              border: "1px solid var(--ac-border)",
              borderRadius: "6px",
              fontSize: "13px",
              fontWeight: 500,
            }}
          >
            {drones.map((d) => (
              <option key={d.id} value={d.id}>
                {d.registration} ({d.model ?? "Drone"})
              </option>
            ))}
          </select>

          {selectedAssetId && (
            <Link
              href={`/drones/${selectedAssetId}`}
              className="ac-btn-outline"
              style={{ fontSize: "12px", padding: "6px 12px", textDecoration: "none" }}
            >
              Inspect Asset →
            </Link>
          )}
        </div>
      </header>

      {/* Main Telemetry Panel */}
      {selectedAssetId ? (
        <div style={{ background: "var(--ac-bg-card)", border: "1px solid var(--ac-border)", borderRadius: "8px", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", borderBottom: "1px solid var(--ac-border-subtle)", paddingBottom: "12px" }}>
            <div>
              <h2 style={{ fontSize: "16px", margin: 0, color: "var(--ac-text-primary)" }}>
                {selectedDrone?.registration ?? selectedAssetId}
              </h2>
              <span style={{ fontSize: "11px", color: "var(--ac-text-muted)" }}>UUID: {selectedAssetId}</span>
            </div>
          </div>
          <TelemetryPanel assetId={selectedAssetId} accessToken={accessToken} />
        </div>
      ) : loadingDrones ? (
        <div style={{ padding: "32px", textAlign: "center", color: "var(--ac-text-muted)" }}>
          Discovering drone fleet assets…
        </div>
      ) : (
        <div style={{ padding: "32px", textAlign: "center", color: "var(--ac-text-muted)" }}>
          No drone assets registered in organization.
        </div>
      )}
    </div>
  );
}

export default function TelemetryPage() {
  return (
    <Suspense fallback={<div style={{ padding: "24px", color: "var(--ac-text-muted)" }}>Loading Telemetry…</div>}>
      <TelemetryContent />
    </Suspense>
  );
}
