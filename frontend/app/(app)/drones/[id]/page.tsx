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
import { FlightHistoryTable } from "@/components/flights/FlightHistoryTable";
import { MaintenanceSection } from "@/components/maintenance/MaintenanceSection";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  canRecordFlight,
  dronesApi,
  type AssetLifecycleEventResponse,
  type BatteryInstallationResponse,
  type BatteryResponse,
  type ComponentInstallationResponse,
  type ComponentResponse,
  type DeploymentReadinessResponse,
  type DroneResponse,
  type FlightResponse,
  type MaintenanceDueItem,
  type UtilizationResponse,
} from "@/lib/api/drones";

const FLIGHT_HISTORY_PAGE_SIZE = 10;

function statusBadge(status: string) {
  if (status === "ACTIVE" || status === "GOOD" || status === "READY")
    return { status: "COMPLIANT" as const, label: status };
  if (status === "GROUNDED" || status === "CRITICAL" || status === "BLOCKED")
    return { status: "NON_COMPLIANT" as const, label: status };
  return { status: "UNKNOWN" as const, label: status };
}

function RealDroneDetail({ assetId }: { assetId: string }) {
  const { accessToken, isAuthenticated, user } = useSession();
  const [drone, setDrone] = useState<DroneResponse | null>(null);
  const [batteries, setBatteries] = useState<BatteryResponse[]>([]);
  const [components, setComponents] = useState<ComponentResponse[]>([]);
  const [utilization, setUtilization] = useState<UtilizationResponse | null>(null);
  const [readiness, setReadiness] = useState<DeploymentReadinessResponse | null>(null);
  const [batteryHistory, setBatteryHistory] = useState<Record<string, BatteryInstallationResponse[]>>({});
  const [componentHistory, setComponentHistory] = useState<Record<string, ComponentInstallationResponse[]>>({});
  const [lifecycleEvents, setLifecycleEvents] = useState<AssetLifecycleEventResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [flights, setFlights] = useState<FlightResponse[]>([]);
  const [flightsTotal, setFlightsTotal] = useState(0);
  const [flightsOffset, setFlightsOffset] = useState(0);
  const [flightsLoading, setFlightsLoading] = useState(true);
  const [flightsError, setFlightsError] = useState<NormalizedApiError | null>(null);

  const [flightMinutes, setFlightMinutes] = useState("");
  const [flightCycles, setFlightCycles] = useState("1");
  const [flightError, setFlightError] = useState<NormalizedApiError | null>(null);
  const [recordingFlight, setRecordingFlight] = useState(false);

  const [maintenanceItems, setMaintenanceItems] = useState<MaintenanceDueItem[]>([]);
  const [maintenanceLoading, setMaintenanceLoading] = useState(true);
  const [maintenanceError, setMaintenanceError] = useState<NormalizedApiError | null>(null);

  // M17.5C: per-battery/per-component maintenance, keyed by id -- same
  // "bounded by how many this drone actually has" fan-out as
  // batteryHistory/componentHistory below, not a second unbounded call.
  const [batteryMaintenance, setBatteryMaintenance] = useState<Record<string, MaintenanceDueItem[]>>({});
  const [componentMaintenance, setComponentMaintenance] = useState<Record<string, MaintenanceDueItem[]>>({});

  // Maintenance status is fetched separately for the same reason flight
  // history is: recording a maintenance rule/accomplishment (or a new
  // flight, which changes usage-based due status) should only refresh
  // maintenance, never the rest of the drone detail.
  const loadMaintenance = () => {
    if (!accessToken) return;
    setMaintenanceLoading(true);
    setMaintenanceError(null);
    dronesApi
      .getMaintenanceDue(accessToken, assetId)
      .then(setMaintenanceItems)
      .catch((err) => setMaintenanceError(normalizeApiError(err)))
      .finally(() => setMaintenanceLoading(false));
  };

  const loadBatteryMaintenance = (batteryId: string) => {
    if (!accessToken) return Promise.resolve();
    return dronesApi
      .getBatteryMaintenanceDue(accessToken, batteryId)
      .then((items) => setBatteryMaintenance((prev) => ({ ...prev, [batteryId]: items })));
  };

  const loadComponentMaintenance = (componentId: string) => {
    if (!accessToken) return Promise.resolve();
    return dronesApi
      .getComponentMaintenanceDue(accessToken, componentId)
      .then((items) => setComponentMaintenance((prev) => ({ ...prev, [componentId]: items })));
  };

  // Flight history is fetched separately from the rest of the drone detail
  // data so that paginating (or refreshing after recording a flight) never
  // re-fetches battery/component/lifecycle data that hasn't changed.
  const loadFlights = (offset: number) => {
    if (!accessToken) return;
    setFlightsLoading(true);
    setFlightsError(null);
    dronesApi
      .listFlights(accessToken, assetId, { limit: FLIGHT_HISTORY_PAGE_SIZE, offset })
      .then((page) => {
        setFlights(page.items);
        setFlightsTotal(page.total);
        setFlightsOffset(page.offset);
      })
      .catch((err) => setFlightsError(normalizeApiError(err)))
      .finally(() => setFlightsLoading(false));
  };

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
      dronesApi.getUtilization(accessToken, assetId),
      dronesApi.getDeploymentReadiness(accessToken, assetId),
      dronesApi.getAssetLifecycleHistory(accessToken, assetId),
    ])
      .then(async ([d, b, c, u, r, lifecycle]) => {
        setDrone(d);
        setBatteries(b);
        setComponents(c);
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

        // Same bounded-fan-out precedent, one maintenance-due call per
        // battery/component this drone currently has.
        await Promise.all([
          ...b.map((battery) => loadBatteryMaintenance(battery.id)),
          ...c.map((component) => loadComponentMaintenance(component.id)),
        ]);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
    loadFlights(0);
    loadMaintenance();
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
        cycles: Number(flightCycles) || 1,
      })
      .then(() => {
        setFlightMinutes("");
        setFlightCycles("1");
        // Only the data a new flight can actually change: the utilization
        // summary, the attached battery's cycle count (via a fresh
        // battery list), and page 1 of flight history -- not the whole
        // drone detail (lifecycle timelines, components, etc. are
        // unaffected by recording a flight).
        Promise.all([
          dronesApi.getUtilization(accessToken, assetId),
          dronesApi.listBatteries(accessToken, assetId),
        ]).then(([u, b]) => {
          setUtilization(u);
          setBatteries(b);
          // A flight can change the attached battery's cycle count, which
          // changes its maintenance evaluation too.
          b.forEach((battery) => loadBatteryMaintenance(battery.id));
        });
        loadFlights(0);
        loadMaintenance();
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
                        {accessToken && (
                          <div style={{ marginTop: 6 }}>
                            <span className="ac-text-sm ac-text-muted" style={{ fontWeight: 600 }}>
                              Maintenance
                            </span>
                            <div style={{ marginTop: 6 }}>
                              <MaintenanceSection
                                items={batteryMaintenance[b.id] ?? []}
                                loading={false}
                                error={null}
                                canWrite={canRecordFlight(user)}
                                intervalOptions={[
                                  { value: "BATTERY_CYCLES", label: "Battery Cycles" },
                                ]}
                                emptyMessage="No maintenance rules configured for this battery yet."
                                onCreateAndLink={(draft) =>
                                  dronesApi
                                    .createMaintenanceRequirement(accessToken, draft)
                                    .then((requirement) =>
                                      dronesApi.addBatteryMaintenanceApplicability(
                                        accessToken,
                                        b.id,
                                        requirement.id
                                      )
                                    )
                                    .then(() => loadBatteryMaintenance(b.id))
                                }
                                onAccomplish={(requirementId) =>
                                  dronesApi
                                    .recordBatteryMaintenanceAccomplishment(
                                      accessToken,
                                      b.id,
                                      requirementId,
                                      { accomplished_at: new Date().toISOString().slice(0, 10) }
                                    )
                                    .then(() => loadBatteryMaintenance(b.id))
                                }
                              />
                            </div>
                          </div>
                        )}
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
                        {accessToken && (
                          <div style={{ marginTop: 6 }}>
                            <span className="ac-text-sm ac-text-muted" style={{ fontWeight: 600 }}>
                              Maintenance
                            </span>
                            <div style={{ marginTop: 6 }}>
                              <MaintenanceSection
                                items={componentMaintenance[c.id] ?? []}
                                loading={false}
                                error={null}
                                canWrite={canRecordFlight(user)}
                                intervalOptions={[
                                  { value: "COMPONENT_HOURS", label: "Component Hours" },
                                  { value: "COMPONENT_CYCLES", label: "Component Cycles" },
                                ]}
                                emptyMessage="No maintenance rules configured for this component yet."
                                onCreateAndLink={(draft) =>
                                  dronesApi
                                    .createMaintenanceRequirement(accessToken, draft)
                                    .then((requirement) =>
                                      dronesApi.addComponentMaintenanceApplicability(
                                        accessToken,
                                        c.id,
                                        requirement.id
                                      )
                                    )
                                    .then(() => loadComponentMaintenance(c.id))
                                }
                                onAccomplish={(requirementId) =>
                                  dronesApi
                                    .recordComponentMaintenanceAccomplishment(
                                      accessToken,
                                      c.id,
                                      requirementId,
                                      { accomplished_at: new Date().toISOString().slice(0, 10) }
                                    )
                                    .then(() => loadComponentMaintenance(c.id))
                                }
                              />
                            </div>
                          </div>
                        )}
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
                <strong className="ac-text-sm">Flight Operations</strong>

                {utilization ? (
                  <div
                    className="ac-flex ac-gap-4"
                    style={{ marginTop: 10, flexWrap: "wrap" }}
                  >
                    <div>
                      <div className="ac-kpi-value">{utilization.total_flights}</div>
                      <div className="ac-kpi-label">Total Flights</div>
                    </div>
                    <div>
                      <div className="ac-kpi-value">{(utilization.total_minutes / 60).toFixed(1)}</div>
                      <div className="ac-kpi-label">Flight Hours</div>
                    </div>
                    <div>
                      <div className="ac-kpi-value">{utilization.total_cycles}</div>
                      <div className="ac-kpi-label">Cycles</div>
                    </div>
                  </div>
                ) : (
                  <p className="ac-text-sm ac-text-muted" style={{ marginTop: 10 }}>
                    Loading utilization…
                  </p>
                )}

                {canRecordFlight(user) && (
                  <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--ac-border)" }}>
                    <span className="ac-text-sm ac-text-muted" style={{ fontWeight: 600 }}>
                      Record Flight
                    </span>
                    <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
                      <input
                        className="ac-input"
                        style={{ width: 160 }}
                        placeholder="Duration (min)"
                        value={flightMinutes}
                        onChange={(e) => setFlightMinutes(e.target.value.replace(/\D/g, ""))}
                        aria-label="Flight duration in minutes"
                      />
                      <input
                        className="ac-input"
                        style={{ width: 100 }}
                        placeholder="Cycles"
                        value={flightCycles}
                        onChange={(e) => setFlightCycles(e.target.value.replace(/\D/g, ""))}
                        aria-label="Flight cycles"
                      />
                      <button
                        className="ac-btn"
                        onClick={recordFlight}
                        disabled={recordingFlight || !flightMinutes.trim()}
                      >
                        {recordingFlight ? "Recording…" : "Record Flight"}
                      </button>
                    </div>
                    {flightError && (
                      <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                        {flightError.message}
                      </p>
                    )}
                  </div>
                )}

                <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--ac-border)" }}>
                  <span className="ac-text-sm ac-text-muted" style={{ fontWeight: 600 }}>
                    Flight History
                  </span>
                  <div style={{ marginTop: 8 }}>
                    {flightsError ? (
                      <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>
                        {flightsError.message}
                      </p>
                    ) : flightsLoading && flights.length === 0 ? (
                      <p className="ac-text-sm ac-text-muted">Loading flight history…</p>
                    ) : (
                      accessToken && (
                        <FlightHistoryTable
                          flights={flights}
                          total={flightsTotal}
                          limit={FLIGHT_HISTORY_PAGE_SIZE}
                          offset={flightsOffset}
                          loading={flightsLoading}
                          accessToken={accessToken}
                          onPageChange={loadFlights}
                        />
                      )
                    )}
                  </div>
                </div>
              </div>

              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <strong className="ac-text-sm">Maintenance</strong>
                <div style={{ marginTop: 10 }}>
                  {accessToken && (
                    <MaintenanceSection
                      items={maintenanceItems}
                      loading={maintenanceLoading}
                      error={maintenanceError}
                      canWrite={canRecordFlight(user)}
                      intervalOptions={[
                        { value: "FLIGHT_HOURS", label: "Flight Hours" },
                        { value: "FLIGHT_CYCLES", label: "Flight Cycles" },
                        { value: "CALENDAR", label: "Calendar Days" },
                      ]}
                      emptyMessage="No maintenance rules configured for this drone yet."
                      onCreateAndLink={(draft) =>
                        dronesApi
                          .createMaintenanceRequirement(accessToken, draft)
                          .then((requirement) =>
                            dronesApi.addMaintenanceApplicability(
                              accessToken,
                              assetId,
                              requirement.id
                            )
                          )
                          .then(() => loadMaintenance())
                      }
                      onAccomplish={(requirementId) =>
                        dronesApi
                          .recordMaintenanceAccomplishment(accessToken, assetId, requirementId, {
                            accomplished_at: new Date().toISOString().slice(0, 10),
                          })
                          .then(() => loadMaintenance())
                      }
                    />
                  )}
                </div>
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
