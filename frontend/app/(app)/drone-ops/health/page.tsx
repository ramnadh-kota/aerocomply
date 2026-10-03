"use client";

import { useSearchParams, useRouter } from "next/navigation";
import { useSession } from "@/lib/auth/SessionContext";
import { HUMSHealthPanel } from "@/components/intelligence/HUMSHealthPanel";
import { Suspense, useEffect, useState } from "react";
import { humsApi, type HUMSAssetHealthSummary } from "@/lib/api/hums";
import { dronesApi, type DroneResponse } from "@/lib/api/drones";
import Link from "next/link";

function HealthContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const rawAssetId = searchParams.get("assetId");
  const { accessToken } = useSession();
  const [drones, setDrones] = useState<DroneResponse[]>([]);
  const [health, setHealth] = useState<HUMSAssetHealthSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    dronesApi
      .listDrones(accessToken)
      .then((data) => setDrones(data))
      .catch(() => setDrones([]));
  }, [accessToken]);

  const selectedAssetId = rawAssetId || (drones.length > 0 ? drones[0].id : null);
  const selectedDrone = drones.find((d) => d.id === selectedAssetId);

  useEffect(() => {
    if (!selectedAssetId || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    humsApi
      .getAssetHealth(accessToken, selectedAssetId)
      .then(setHealth)
      .catch(() => setHealth(null))
      .finally(() => setLoading(false));
  }, [selectedAssetId, accessToken]);

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
            Fleet Health &amp; HUMS
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: "13px", color: "var(--ac-text-muted)" }}>
            Health and Usage Monitoring Systems (HUMS), sensor thresholds, and vibration diagnostics.
          </p>
        </div>

        {/* Drone Selector Dropdown */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <label htmlFor="health-drone-select" style={{ fontSize: "13px", color: "var(--ac-text-secondary)", fontWeight: 500 }}>
            Select Asset:
          </label>
          <select
            id="health-drone-select"
            value={selectedAssetId ?? ""}
            onChange={(e) => router.push(`/drone-ops/health?assetId=${e.target.value}`)}
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

      {/* Main Health Panel */}
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
          <HUMSHealthPanel health={health} accessToken={accessToken} />
        </div>
      ) : (
        <div style={{ padding: "32px", textAlign: "center", color: "var(--ac-text-muted)" }}>
          {loading ? "Loading HUMS diagnostics…" : "Select a drone asset to view HUMS diagnostics."}
        </div>
      )}
    </div>
  );
}

export default function FleetHealthPage() {
  return (
    <Suspense fallback={<div style={{ padding: "24px", color: "var(--ac-text-muted)" }}>Loading Health &amp; HUMS…</div>}>
      <HealthContent />
    </Suspense>
  );
}
