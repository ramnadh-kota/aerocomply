"use client";

// Phase 18.6: Drone detail -- identity, deployment readiness, battery,
// components, usage, and record-flight action.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { LifecycleHistoryList } from "@/components/lifecycle/LifecycleHistoryList";
import { AssetLifecycleTimeline } from "@/components/lifecycle/AssetLifecycleTimeline";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  dronesApi,
  type AssetLifecycleEventResponse,
  type BatteryInstallationResponse,
  type BatteryResponse,
  type ComponentInstallationResponse,
  type ComponentResponse,
  type DeploymentReadinessResponse,
  type DroneResponse,
  type FlightResponse,
  type UtilizationResponse,
} from "@/lib/api/drones";

function statusBadge(status: string) {
  if (status === "ACTIVE" || status === "GOOD" || status === "READY")
    return { status: "COMPLIANT" as const, label: status };
  if (status === "GROUNDED" || status === "CRITICAL" || status === "BLOCKED")
    return { status: "NON_COMPLIANT" as const, label: status };
  return { status: "UNKNOWN" as const, label: status };
}

function RealDroneDetail({ assetId }: { assetId: string }) {
  const { accessToken, isAuthenticated } = useSession();
  const [drone, setDrone] = useState<DroneResponse | null>(null);
  const [batteries, setBatteries] = useState<BatteryResponse[]>([]);
  const [components, setComponents] = useState<ComponentResponse[]>([]);
  const [flights, setFlights] = useState<FlightResponse[]>([]);
  const [utilization, setUtilization] = useState<UtilizationResponse | null>(null);
  const [readiness, setReadiness] = useState<DeploymentReadinessResponse | null>(null);
  const [batteryHistory, setBatteryHistory] = useState<Record<string, BatteryInstallationResponse[]>>({});
  const [componentHistory, setComponentHistory] = useState<Record<string, ComponentInstallationResponse[]>>({});
  const [lifecycleEvents, setLifecycleEvents] = useState<AssetLifecycleEventResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [flightMinutes, setFlightMinutes] = useState("");
  const [flightError, setFlightError] = useState<NormalizedApiError | null>(null);
  const [recordingFlight, setRecordingFlight] = useState(false);

  const load = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    Promise.all([
      dronesApi.getDrone(accessToken, assetId),
      dronesApi.listBatteries(accessToken, assetId),
      dronesApi.listComponents(accessToken, assetId),
      dronesApi.listFlights(accessToken, assetId),
      dronesApi.getUtilization(accessToken, assetId),
      dronesApi.getDeploymentReadiness(accessToken, assetId),
      dronesApi.getAssetLifecycleHistory(accessToken, assetId),
    ])
      .then(async ([d, b, c, f, u, r, lifecycle]) => {
        setDrone(d);
        setBatteries(b);
        setComponents(c);
        setFlights(f);
        setUtilization(u);
        setReadiness(r);
        setLifecycleEvents(lifecycle.items);

        // One history call per battery/component currently on this asset --
        // bounded by how many of each a single drone actually carries, not
        // an unbounded fan-out.
        const [batteryHistories, componentHistories] = await Promise.all([
          Promise.all(b.map((battery) => dronesApi.getBatteryHistory(accessToken, battery.id))),
          Promise.all(c.map((component) => dronesApi.getComponentHistory(accessToken, component.id))),
        ]);
        setBatteryHistory(
          Object.fromEntries(b.map((battery, i) => [battery.id, batteryHistories[i].items]))
        );
        setComponentHistory(
          Object.fromEntries(c.map((component, i) => [component.id, componentHistories[i].items]))
        );
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated, assetId]);

  const recordFlight = () => {
    if (!accessToken || !flightMinutes.trim()) return;
    setRecordingFlight(true);
    setFlightError(null);
    dronesApi
      .recordFlight(accessToken, assetId, {
        flown_at: new Date().toISOString(),
        duration_minutes: Number(flightMinutes),
      })
      .then(() => {
        setFlightMinutes("");
        load();
      })
      .catch((err) => setFlightError(normalizeApiError(err)))
      .finally(() => setRecordingFlight(false));
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Drones", href: "/drones" },
          { label: drone?.registration ?? "Drone" },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{drone?.registration ?? "Drone"}</h1>
          <p className="ac-subtitle">
            {drone?.manufacturer ?? "—"} {drone?.model ?? ""}
          </p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Sign in to view this drone. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <RealDataPanel loading={loading} error={error} isEmpty={false} emptyMessage="Drone not found.">
          {drone && (
            <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4)" }}>
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <strong className="ac-text-sm">Deployment Readiness</strong>
                {readiness && (
                  <div style={{ marginTop: 8 }}>
                    <StatusBadge {...statusBadge(readiness.status)} />
                    {readiness.blockers.length > 0 && (
                      <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                        {readiness.blockers.map((b) => (
                          <li key={b} className="ac-text-sm">
                            {b}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>

              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <strong className="ac-text-sm">Battery</strong>
                {batteries.length === 0 ? (
                  <p className="ac-text-sm" style={{ marginTop: 8, opacity: 0.7 }}>
                    No battery assigned.
                  </p>
                ) : (
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: "var(--ac-space-4)" }}>
                    {batteries.map((b) => (
                      <div key={b.id}>
                        <div className="ac-flex ac-gap-2" style={{ alignItems: "center", flexWrap: "wrap" }}>
                          <span className="ac-text-sm">{b.serial_number}</span>
                          <StatusBadge {...statusBadge(b.status)} />
                          <span className="ac-text-sm" style={{ opacity: 0.7 }}>
                            {b.cycle_count} cycles{b.health_percent != null ? ` · ${b.health_percent}% health` : ""}
                          </span>
                        </div>
                        <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0", wordBreak: "break-all" }}>
                          Battery ID: <span className="ac-mono">{b.id}</span>
                        </p>
                        <p className="ac-text-sm ac-text-muted" style={{ margin: "6px 0" }}>
                          Current assignment: {b.asset_id ? (
                            <span className="ac-mono">{b.asset_id}</span>
                          ) : (
                            "Not currently installed"
                          )}
                        </p>
                        <div style={{ marginTop: 6 }}>
                          <span className="ac-text-sm ac-text-muted" style={{ fontWeight: 600 }}>
                            Lifecycle History
                          </span>
                          <div style={{ marginTop: 6 }}>
                            <LifecycleHistoryList installations={batteryHistory[b.id] ?? []} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <strong className="ac-text-sm">Components ({components.length})</strong>
                {components.length === 0 ? (
                  <p className="ac-text-sm" style={{ marginTop: 8, opacity: 0.7 }}>
                    No components assigned.
                  </p>
                ) : (
                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: "var(--ac-space-4)" }}>
                    {components.map((c) => (
                      <div key={c.id}>
                        <div className="ac-text-sm">
                          {c.name} ({c.component_type})
                        </div>
                        <p className="ac-text-sm ac-text-muted" style={{ margin: "2px 0", wordBreak: "break-all" }}>
                          Component ID: <span className="ac-mono">{c.id}</span>
                        </p>
                        <p className="ac-text-sm ac-text-muted" style={{ margin: "6px 0" }}>
                          Current assignment: {c.asset_id ? (
                            <span className="ac-mono">{c.asset_id}</span>
                          ) : (
                            "Not currently installed"
                          )}
                        </p>
                        <div style={{ marginTop: 6 }}>
                          <span className="ac-text-sm ac-text-muted" style={{ fontWeight: 600 }}>
                            Lifecycle History
                          </span>
                          <div style={{ marginTop: 6 }}>
                            <LifecycleHistoryList installations={componentHistory[c.id] ?? []} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <strong className="ac-text-sm">Asset Lifecycle Timeline</strong>
                <div style={{ marginTop: 10 }}>
                  <AssetLifecycleTimeline events={lifecycleEvents} />
                </div>
              </div>

              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <strong className="ac-text-sm">Usage</strong>
                {utilization && (
                  <p className="ac-text-sm" style={{ margin: "8px 0" }}>
                    {utilization.total_flights} flights · {utilization.total_minutes} minutes ·{" "}
                    {utilization.total_cycles} cycles
                  </p>
                )}
                <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
                  <input
                    className="ac-input"
                    style={{ width: 160 }}
                    placeholder="Flight duration (min)"
                    value={flightMinutes}
                    onChange={(e) => setFlightMinutes(e.target.value.replace(/\D/g, ""))}
                    aria-label="Flight duration in minutes"
                  />
                  <button className="ac-btn" onClick={recordFlight} disabled={recordingFlight || !flightMinutes.trim()}>
                    {recordingFlight ? "Recording…" : "Record Flight"}
                  </button>
                </div>
                {flightError && (
                  <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                    {flightError.message}
                  </p>
                )}
              </div>
            </div>
          )}
        </RealDataPanel>
      )}
    </div>
  );
}

export default function DroneDetailPage() {
  const params = useParams<{ id: string }>();
  return <RealDroneDetail assetId={params.id} />;
}
