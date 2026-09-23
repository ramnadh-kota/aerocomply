"use client";

// Phase 18.6: Drone detail -- identity, deployment readiness, battery,
// components, usage, and record-flight action.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge, assetStatusBadge as statusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { ReadinessIndicator, type ReadinessBlocker } from "@/components/readiness/ReadinessIndicator";
import { LifecycleHistoryList } from "@/components/lifecycle/LifecycleHistoryList";
import { AssetLifecycleTimeline } from "@/components/lifecycle/AssetLifecycleTimeline";
import { FlightHistoryTable } from "@/components/flights/FlightHistoryTable";
import { MaintenanceSection } from "@/components/maintenance/MaintenanceSection";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { findingsApi, type BackendFinding } from "@/lib/api/findings";
import { missionsApi, type BackendMission } from "@/lib/api/missions";
import { complianceAssessmentsApi, type BackendComplianceAssessment } from "@/lib/api/compliance";
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
import {
  getDemoDroneById,
  getDemoBatteryForDrone,
  getDemoComponentsForDrone,
  getDemoFlightsForDrone,
  getDemoUtilizationForDrone,
  getDemoFindingsForDrone,
  getDemoMaintenanceForDrone,
  getDemoMissionsForDrone,
  getDemoDeploymentReadiness,
  getDemoComplianceForDrone,
} from "@/lib/demo/demoDrones";

const FLIGHT_HISTORY_PAGE_SIZE = 10;

// M20.6: Findings panel for the drone detail page, mirroring
// AircraftFindingsPanel (frontend/app/(app)/aircraft/[id]/page.tsx) exactly
// -- same findingsApi client, same RealDataPanel/StatusBadge usage, same
// raise/disposition/close flow, substituting asset_id for aircraft_id. No
// new backend route: reuses GET /findings?asset_id=, POST /findings,
// POST /findings/{id}/dispositions, POST /findings/{id}/close.
function DroneFindingsPanel({ droneId }: { droneId: string }) {
  const { accessToken, isAuthenticated } = useSession();
  const [findings, setFindings] = useState<BackendFinding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [severity, setSeverity] = useState("MINOR");
  const [submitting, setSubmitting] = useState(false);

  const refresh = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    findingsApi
      .listForAsset(accessToken, droneId)
      .then((data) => setFindings(data))
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, [accessToken, isAuthenticated, droneId]);

  const submit = async () => {
    if (!accessToken || !title.trim() || !description.trim()) return;
    setSubmitting(true);
    try {
      await findingsApi.create(accessToken, { title, description, severity, asset_id: droneId });
      setTitle("");
      setDescription("");
      setSeverity("MINOR");
      setShowForm(false);
      refresh();
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  const close = async (findingId: string) => {
    if (!accessToken) return;
    try {
      await findingsApi.close(accessToken, findingId);
      refresh();
    } catch (err) {
      setError(normalizeApiError(err));
    }
  };

  const dispose = async (findingId: string) => {
    if (!accessToken) return;
    try {
      await findingsApi.addDisposition(accessToken, findingId, {
        disposition_type: "NO_ACTION_REQUIRED",
      });
      refresh();
    } catch (err) {
      setError(normalizeApiError(err));
    }
  };

  return (
    <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
      <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
        <strong className="ac-text-sm">Findings (live)</strong>
        {isAuthenticated && (
          <button className="ac-btn" style={{ fontSize: 12, padding: "4px 10px" }} onClick={() => setShowForm((v) => !v)}>
            {showForm ? "Cancel" : "Raise Finding"}
          </button>
        )}
      </div>

      {showForm && (
        <div className="ac-card" style={{ marginBottom: 10 }}>
          <div className="ac-grid-2" style={{ gap: 8, marginBottom: 8 }}>
            <input
              className="ac-input"
              placeholder="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
            <select className="ac-input" value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="OBSERVATION">Observation</option>
              <option value="MINOR">Minor</option>
              <option value="MAJOR">Major</option>
              <option value="CRITICAL">Critical</option>
            </select>
          </div>
          <textarea
            className="ac-input"
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            style={{ width: "100%", minHeight: 60, marginBottom: 8 }}
          />
          <button className="ac-btn ac-btn-primary" disabled={submitting} onClick={submit}>
            {submitting ? "Submitting…" : "Submit Finding"}
          </button>
        </div>
      )}

      <RealDataPanel loading={loading} error={error} isEmpty={findings.length === 0} emptyMessage="No findings recorded for this drone yet.">
        <div className="ac-card" style={{ padding: 0 }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Severity</th>
                <th>Status</th>
                <th>Discovered</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((f) => (
                <tr key={f.id}>
                  <td className="ac-text-sm">{f.title}</td>
                  <td><StatusBadge status={f.severity === "CRITICAL" || f.severity === "MAJOR" ? "NON_COMPLIANT" : "PENDING"} label={f.severity} /></td>
                  <td><StatusBadge status={f.status === "CLOSED" ? "COMPLIANT" : f.status === "IN_PROGRESS" ? "REVIEW_REQUIRED" : "PENDING"} label={f.status.replace(/_/g, " ")} /></td>
                  <td className="ac-text-sm">{new Date(f.discovered_at).toLocaleDateString()}</td>
                  <td className="ac-text-sm">
                    {f.status !== "CLOSED" && f.dispositions.length === 0 && (
                      <button className="ac-btn" style={{ fontSize: 11, padding: "2px 8px", marginRight: 6 }} onClick={() => dispose(f.id)}>
                        No Action Required
                      </button>
                    )}
                    {f.status !== "CLOSED" && f.dispositions.length > 0 && (
                      <button className="ac-btn ac-btn-primary" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => close(f.id)}>
                        Close
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </RealDataPanel>
    </div>
  );
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

  const [missions, setMissions] = useState<BackendMission[]>([]);
  const [missionsLoading, setMissionsLoading] = useState(true);
  const [missionsError, setMissionsError] = useState<NormalizedApiError | null>(null);
  const [authorizingMissionId, setAuthorizingMissionId] = useState<string | null>(null);

  const [compliance, setCompliance] = useState<BackendComplianceAssessment[]>([]);
  const [complianceLoading, setComplianceLoading] = useState(true);
  const [complianceError, setComplianceError] = useState<NormalizedApiError | null>(null);

  // M17.5C: per-battery/per-component maintenance, keyed by id -- same
  // "bounded by how many this drone actually has" fan-out as
  // batteryHistory/componentHistory below, not a second unbounded call.
  const [batteryMaintenance, setBatteryMaintenance] = useState<Record<string, MaintenanceDueItem[]>>({});
  const [componentMaintenance, setComponentMaintenance] = useState<Record<string, MaintenanceDueItem[]>>({});
  const [batteryMaintenanceLoading, setBatteryMaintenanceLoading] = useState<Record<string, boolean>>({});
  const [componentMaintenanceLoading, setComponentMaintenanceLoading] = useState<Record<string, boolean>>({});
  const [batteryMaintenanceErrors, setBatteryMaintenanceErrors] = useState<Record<string, NormalizedApiError | null>>({});
  const [componentMaintenanceErrors, setComponentMaintenanceErrors] = useState<Record<string, NormalizedApiError | null>>({});

  const loadMissions = () => {
    if (!accessToken) return;
    setMissionsLoading(true);
    setMissionsError(null);
    missionsApi
      .listMissions(accessToken, { asset_id: assetId })
      .then((res) => setMissions(res.items))
      .catch((err) => setMissionsError(normalizeApiError(err)))
      .finally(() => setMissionsLoading(false));
  };

  const loadCompliance = () => {
    if (!accessToken) return;
    setComplianceLoading(true);
    setComplianceError(null);
    complianceAssessmentsApi
      .listForAsset(accessToken, assetId)
      .then(setCompliance)
      .catch((err) => setComplianceError(normalizeApiError(err)))
      .finally(() => setComplianceLoading(false));
  };

  const handleAuthorizeMission = async (missionId: string) => {
    if (!accessToken) return;
    setAuthorizingMissionId(missionId);
    try {
      await missionsApi.authorizeMission(accessToken, missionId);
      loadMissions();
    } catch (err) {
      setMissionsError(normalizeApiError(err));
    } finally {
      setAuthorizingMissionId(null);
    }
  };

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
    setBatteryMaintenanceLoading((prev) => ({ ...prev, [batteryId]: true }));
    setBatteryMaintenanceErrors((prev) => ({ ...prev, [batteryId]: null }));
    return dronesApi
      .getBatteryMaintenanceDue(accessToken, batteryId)
      .then((items) => setBatteryMaintenance((prev) => ({ ...prev, [batteryId]: items })))
      .catch((err) => setBatteryMaintenanceErrors((prev) => ({ ...prev, [batteryId]: normalizeApiError(err) })))
      .finally(() => setBatteryMaintenanceLoading((prev) => ({ ...prev, [batteryId]: false })));
  };

  const loadComponentMaintenance = (componentId: string) => {
    if (!accessToken) return Promise.resolve();
    setComponentMaintenanceLoading((prev) => ({ ...prev, [componentId]: true }));
    setComponentMaintenanceErrors((prev) => ({ ...prev, [componentId]: null }));
    return dronesApi
      .getComponentMaintenanceDue(accessToken, componentId)
      .then((items) => setComponentMaintenance((prev) => ({ ...prev, [componentId]: items })))
      .catch((err) => setComponentMaintenanceErrors((prev) => ({ ...prev, [componentId]: normalizeApiError(err) })))
      .finally(() => setComponentMaintenanceLoading((prev) => ({ ...prev, [componentId]: false })));
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
    loadMissions();
    loadCompliance();
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
      <PageHeader
        breadcrumbs={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Drones", href: "/drones" },
          { label: drone?.registration ?? "Drone" },
        ]}
        title={drone?.registration ?? "Drone"}
        subtitle={`${drone?.manufacturer ?? "—"} ${drone?.model ?? ""}`}
        actions={
          <Link href={`/maintenance/work-orders?asset_id=${assetId}`} className="ac-btn">
            Maintenance / Work Orders →
          </Link>
        }
      />

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
                <strong className="ac-text-sm">Deployment Readiness Signals</strong>
                <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
                  Operational signals from the connected drone record. This is not an inspection, evidence, compliance, or release authorization decision.
                </p>
                {readiness && (
                  <div style={{ marginTop: 8 }}>
                    <ReadinessIndicator
                      status={readiness.status}
                      blockers={readiness.blockers.map((b, i): ReadinessBlocker => {
                        // M21.1: if this string blocker has a matching
                        // structured finding_blockers entry (same index
                        // order as evaluate_deployment_readiness appends
                        // both lists), link through to the canonical
                        // /findings/{id} page instead of rendering plain text.
                        const findingBlockers = readiness.finding_blockers ?? [];
                        const finding = findingBlockers[i - (readiness.blockers.length - findingBlockers.length)];
                        return {
                          key: `${b}-${i}`,
                          label: b,
                          href: finding ? `/findings/${finding.finding_id}` : undefined,
                        };
                      })}
                    />
                  </div>
                )}
              </div>

              {/* Real Mission Operations & Internal Authorization */}
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
                  <div>
                    <strong className="ac-text-sm">Assigned Missions & Pre-Flight</strong>
                    <p className="ac-text-xs ac-text-muted" style={{ margin: "2px 0 0" }}>
                      Internal operational mission dispatch. Does not constitute regulatory airspace authorization.
                    </p>
                  </div>
                  <StatusBadge
                    status={missions.length > 0 ? "REVIEW_REQUIRED" : "NOT_APPLICABLE"}
                    label={`${missions.length} Missions`}
                  />
                </div>

                {missionsError && (
                  <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>
                    {missionsError.message}
                  </p>
                )}

                {missionsLoading ? (
                  <p className="ac-text-sm ac-text-muted">Loading missions…</p>
                ) : missions.length === 0 ? (
                  <p className="ac-text-sm ac-text-muted">No missions scheduled for this drone yet.</p>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 8 }}>
                    {missions.map((m) => (
                      <div
                        key={m.id}
                        style={{
                          background: "var(--ac-bg-subtle, rgba(255,255,255,0.03))",
                          border: "1px solid var(--ac-border)",
                          borderRadius: 6,
                          padding: "var(--ac-space-3)",
                        }}
                      >
                        <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 8 }}>
                          <div>
                            <strong className="ac-text-sm">{m.purpose}</strong>
                            <div className="ac-text-xs ac-text-muted" style={{ marginTop: 2 }}>
                              Area: <strong>{m.operating_area || "Standard Corridor"}</strong>
                              {m.pilot_user_id && <> • Pilot: <span className="ac-mono">{m.pilot_user_id}</span></>}
                              {m.planned_start && <> • Planned: {new Date(m.planned_start).toLocaleString()}</>}
                            </div>
                          </div>
                          <div className="ac-flex ac-gap-2 ac-items-center">
                            <StatusBadge
                              status={
                                m.status === "AUTHORIZED" || m.status === "COMPLETED"
                                  ? "COMPLIANT"
                                  : m.status === "IN_PROGRESS"
                                  ? "REVIEW_REQUIRED"
                                  : m.status === "CANCELLED"
                                  ? "NON_COMPLIANT"
                                  : "PENDING"
                              }
                              label={m.status}
                            />
                            {m.status === "PLANNED" && (
                              <button
                                className="ac-btn ac-btn--sm"
                                disabled={authorizingMissionId === m.id}
                                onClick={() => handleAuthorizeMission(m.id)}
                              >
                                {authorizingMissionId === m.id ? "Authorizing…" : "Authorize Mission"}
                              </button>
                            )}
                          </div>
                        </div>

                        {m.authorized_at && (
                          <div className="ac-text-xs ac-text-muted" style={{ marginTop: 6 }}>
                            Operationally authorized on {new Date(m.authorized_at).toLocaleString()}
                            {m.authorized_by_user_id && <> by <span className="ac-mono">{m.authorized_by_user_id}</span></>}
                          </div>
                        )}

                        <div style={{ marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--ac-border)" }}>
                          <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 6, flexWrap: "wrap", gap: 6 }}>
                            <span className="ac-text-xs ac-text-muted" style={{ fontWeight: 600 }}>
                              Pre-Flight Evaluation Matrix:
                            </span>
                            <span className="ac-badge ac-badge--secondary" style={{ fontSize: 10 }}>
                              PRE-FLIGHT: MANUAL CLEARANCE REQUIRED (External Controls Unevaluated)
                            </span>
                          </div>
                          <div
                            style={{
                              display: "grid",
                              gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
                              gap: 8,
                              marginTop: 6,
                            }}
                          >
                            <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 8px" }}>
                              <span className="ac-text-xs">Airframe Condition</span>
                              <StatusBadge
                                status={readiness?.status === "READY" ? "COMPLIANT" : "NON_COMPLIANT"}
                                label={readiness?.status === "READY" ? "PASS" : "BLOCK"}
                              />
                            </div>
                            <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 8px" }}>
                              <span className="ac-text-xs">Battery Status</span>
                              <StatusBadge
                                status={batteries.length > 0 && !batteries.some((b) => b.status === "CRITICAL" || b.status === "RETIRED") ? "COMPLIANT" : "NON_COMPLIANT"}
                                label={batteries.length > 0 && !batteries.some((b) => b.status === "CRITICAL" || b.status === "RETIRED") ? "PASS" : "CHECK"}
                              />
                            </div>
                            <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 8px" }}>
                              <span className="ac-text-xs">Maintenance Due</span>
                              <StatusBadge
                                status={maintenanceItems.every((item) => item.due_status === "NOT_DUE") ? "COMPLIANT" : "NON_COMPLIANT"}
                                label={maintenanceItems.every((item) => item.due_status === "NOT_DUE") ? "PASS" : "DUE"}
                              />
                            </div>
                            <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 8px" }}>
                              <span className="ac-text-xs">Inspection Gate</span>
                              <StatusBadge
                                status={!readiness?.blockers?.some((b) => b.toLowerCase().includes("inspection")) ? "COMPLIANT" : "NON_COMPLIANT"}
                                label={!readiness?.blockers?.some((b) => b.toLowerCase().includes("inspection")) ? "PASS" : "BLOCK"}
                              />
                            </div>
                            <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 8px" }}>
                              <span className="ac-text-xs">Open Findings</span>
                              <StatusBadge
                                status={!readiness?.finding_blockers?.length ? "COMPLIANT" : "NON_COMPLIANT"}
                                label={!readiness?.finding_blockers?.length ? "PASS" : "BLOCK"}
                              />
                            </div>
                            <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 8px" }}>
                              <span className="ac-text-xs">Pilot Qualification</span>
                              <span className="ac-badge ac-badge--secondary" style={{ fontSize: 10 }}>NOT EVALUATED</span>
                            </div>
                            <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 8px" }}>
                              <span className="ac-text-xs">Airspace Auth</span>
                              <span className="ac-badge ac-badge--secondary" style={{ fontSize: 10 }}>NOT INTEGRATED</span>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Real Compliance Assessments for Drone */}
              <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
                <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
                  <div>
                    <strong className="ac-text-sm">Compliance Determinations ({compliance.length})</strong>
                    <p className="ac-text-xs ac-text-muted" style={{ margin: "2px 0 0" }}>
                      Asset-scoped regulatory compliance determinations and assessment records.
                    </p>
                  </div>
                </div>

                {complianceError && (
                  <p className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>
                    {complianceError.message}
                  </p>
                )}

                {complianceLoading ? (
                  <p className="ac-text-sm ac-text-muted">Loading compliance assessments…</p>
                ) : compliance.length === 0 ? (
                  <p className="ac-text-sm ac-text-muted">No compliance assessments recorded for this drone asset.</p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--ac-border)", textAlign: "left" }}>
                          <th style={{ padding: "6px 8px" }}>Requirement ID</th>
                          <th style={{ padding: "6px 8px" }}>Status</th>
                          <th style={{ padding: "6px 8px" }}>Evaluated</th>
                          <th style={{ padding: "6px 8px" }}>Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {compliance.map((c) => (
                          <tr key={c.id} style={{ borderBottom: "1px solid var(--ac-border)" }}>
                            <td style={{ padding: "8px" }} className="ac-mono">{c.requirement_id}</td>
                            <td style={{ padding: "8px" }}>
                              <StatusBadge
                                status={c.status === "COMPLIANT" ? "COMPLIANT" : c.status === "NOT_APPLICABLE" ? "NOT_APPLICABLE" : "NON_COMPLIANT"}
                                label={c.status}
                              />
                            </td>
                            <td style={{ padding: "8px" }}>{new Date(c.evaluated_at).toLocaleDateString()}</td>
                            <td style={{ padding: "8px" }}>{c.notes || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
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
                                loading={batteryMaintenanceLoading[b.id] ?? false}
                                error={batteryMaintenanceErrors[b.id] ?? null}
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
                                loading={componentMaintenanceLoading[c.id] ?? false}
                                error={componentMaintenanceErrors[c.id] ?? null}
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

              <DroneFindingsPanel droneId={assetId} />
            </div>
          )}
        </RealDataPanel>
      )}
    </div>
  );
}

// Demo Drone Detail for SessionType === "DEMO"
function DemoDroneDetail({ assetId }: { assetId: string }) {
  const drone = getDemoDroneById(assetId);

  if (!drone) {
    return (
      <div>
        <PageHeader
          breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Drones", href: "/drones" }, { label: "Not Found" }]}
          title="Drone Not Found"
          subtitle="The requested synthetic drone could not be located in the demo environment."
        />
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            No synthetic drone found with ID &ldquo;{assetId}&rdquo;. <Link href="/drones">Return to Fleet →</Link>
          </p>
        </div>
      </div>
    );
  }

  const readiness = getDemoDeploymentReadiness(drone.id);
  const battery = getDemoBatteryForDrone(drone.id);
  const components = getDemoComponentsForDrone(drone.id);
  const flights = getDemoFlightsForDrone(drone.id);
  const utilization = getDemoUtilizationForDrone(drone.id);
  const maintenance = getDemoMaintenanceForDrone(drone.id);
  const findings = getDemoFindingsForDrone(drone.id);
  const missions = getDemoMissionsForDrone(drone.id);
  const compliance = getDemoComplianceForDrone(drone.id);

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Drones", href: "/drones" },
          { label: drone.registration ?? "Drone" },
        ]}
        title={drone.registration ?? "Drone"}
        subtitle={`${drone.manufacturer ?? "Unknown Manufacturer"} ${drone.model ?? "Unknown Model"} • S/N: ${drone.serial_number ?? "—"}`}
        actions={
          <Link href={`/maintenance/work-orders?asset_id=${drone.id}`} className="ac-btn">
            Maintenance / Work Orders →
          </Link>
        }
      />

      {/* Deployment Readiness Card */}
      <div
        className="ac-card"
        style={{
          padding: "var(--ac-space-4)",
          marginBottom: "var(--ac-space-4)",
          borderLeft: `4px solid ${readiness.status === "READY" ? "var(--ac-status-compliant)" : "var(--ac-status-non-compliant)"}`,
        }}
      >
        <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 12 }}>
          <div>
            <span className="ac-text-xs ac-text-muted" style={{ textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Operational Deployment Gate
            </span>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4 }}>
              <strong style={{ fontSize: 18 }}>
                {readiness.status === "READY" ? "Ready for Flight Operations" : "Flight Operations Blocked"}
              </strong>
              <StatusBadge
                status={readiness.status === "READY" ? "COMPLIANT" : "NON_COMPLIANT"}
                label={readiness.status === "READY" ? "READY" : "BLOCKED"}
              />
            </div>
          </div>
          <div className="ac-flex ac-gap-2">
            <StatusBadge {...statusBadge(drone.status)} />
          </div>
        </div>

        {readiness.blockers.length > 0 && (
          <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--ac-border)" }}>
            <span className="ac-text-xs" style={{ fontWeight: 600, color: "var(--ac-status-non-compliant)" }}>
              Blocking Conditions ({readiness.blockers.length}):
            </span>
            <ul style={{ margin: "6px 0 0", paddingLeft: 20, fontSize: 13 }}>
              {readiness.blockers.map((b, idx) => (
                <li key={idx} style={{ color: "var(--ac-text-primary)", marginBottom: 2 }}>
                  {b}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4)" }}>
        {/* Airframe Identity & Utilization Overview */}
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <strong className="ac-text-sm">Airframe Identity & Utilization</strong>
          <div
            className="ac-grid-4"
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
              gap: "var(--ac-space-3)",
              marginTop: 12,
            }}
          >
            <div>
              <span className="ac-text-xs ac-text-muted">Serial Number</span>
              <p className="ac-text-sm" style={{ margin: "2px 0 0", fontWeight: 600 }}>
                {drone.serial_number ?? "—"}
              </p>
            </div>
            <div>
              <span className="ac-text-xs ac-text-muted">Assigned Base / Facility</span>
              <p className="ac-text-sm" style={{ margin: "2px 0 0", fontWeight: 600 }}>
                {drone.facility_id ?? "Default Hub"}
              </p>
            </div>
            <div>
              <span className="ac-text-xs ac-text-muted">Total Recorded Flights</span>
              <p className="ac-text-sm" style={{ margin: "2px 0 0", fontWeight: 600 }}>
                {utilization.total_flights} flights
              </p>
            </div>
            <div>
              <span className="ac-text-xs ac-text-muted">Cumulative Flight Time</span>
              <p className="ac-text-sm" style={{ margin: "2px 0 0", fontWeight: 600 }}>
                {(utilization.total_minutes / 60).toFixed(1)} hrs ({utilization.total_minutes} mins)
              </p>
            </div>
          </div>
        </div>

        {/* Mission Operations & Pre-Flight Gate */}
        {missions.length > 0 && (
          <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
            <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 12 }}>
              <strong className="ac-text-sm">Assigned Mission & Pre-Flight Gate</strong>
              <StatusBadge status="PENDING" label={`${missions.length} Scheduled Mission`} />
            </div>

            {missions.map((m) => (
              <div
                key={m.id}
                style={{
                  background: "var(--ac-bg-subtle, rgba(255,255,255,0.03))",
                  border: "1px solid var(--ac-border)",
                  borderRadius: 6,
                  padding: "var(--ac-space-3)",
                  marginBottom: 10,
                }}
              >
                <div className="ac-flex ac-justify-between ac-items-center" style={{ flexWrap: "wrap", gap: 8 }}>
                  <div>
                    <strong className="ac-text-sm">{m.mission_code}</strong>: {m.purpose}
                    <div className="ac-text-xs ac-text-muted" style={{ marginTop: 2 }}>
                      Pilot: <strong>{m.pilot_name}</strong> • Area: <strong>{m.operating_area}</strong> • Planned:{" "}
                      {new Date(m.planned_start).toLocaleDateString()}
                    </div>
                  </div>
                  <StatusBadge
                    status={m.overall_preflight === "READY" ? "COMPLIANT" : "NON_COMPLIANT"}
                    label={`PRE-FLIGHT: ${m.overall_preflight}`}
                  />
                </div>

                <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid var(--ac-border)" }}>
                  <span className="ac-text-xs ac-text-muted" style={{ fontWeight: 600 }}>
                    Pre-Flight Assessment Matrix:
                  </span>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                      gap: 8,
                      marginTop: 8,
                    }}
                  >
                    <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 10px" }}>
                      <span className="ac-text-xs">Airframe Condition</span>
                      <StatusBadge
                        status={m.preflight_checks.airframe_condition === "PASS" ? "COMPLIANT" : "NON_COMPLIANT"}
                        label={m.preflight_checks.airframe_condition}
                      />
                    </div>
                    <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 10px" }}>
                      <span className="ac-text-xs">Battery System</span>
                      <StatusBadge
                        status={m.preflight_checks.battery_state === "PASS" ? "COMPLIANT" : "NON_COMPLIANT"}
                        label={m.preflight_checks.battery_state}
                      />
                    </div>
                    <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 10px" }}>
                      <span className="ac-text-xs">Maintenance Due</span>
                      <StatusBadge
                        status={m.preflight_checks.maintenance_status === "PASS" ? "COMPLIANT" : "NON_COMPLIANT"}
                        label={m.preflight_checks.maintenance_status}
                      />
                    </div>
                    <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 10px" }}>
                      <span className="ac-text-xs">Inspection Gate</span>
                      <StatusBadge
                        status={m.preflight_checks.inspection_clearance === "PASS" ? "COMPLIANT" : "NON_COMPLIANT"}
                        label={m.preflight_checks.inspection_clearance}
                      />
                    </div>
                    <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 10px" }}>
                      <span className="ac-text-xs">Open Findings</span>
                      <StatusBadge
                        status={m.preflight_checks.open_findings === "PASS" ? "COMPLIANT" : "NON_COMPLIANT"}
                        label={m.preflight_checks.open_findings}
                      />
                    </div>
                    <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 10px" }}>
                      <span className="ac-text-xs">Pilot Qualification</span>
                      <StatusBadge
                        status={m.preflight_checks.pilot_qualification === "PASS" ? "COMPLIANT" : "NON_COMPLIANT"}
                        label={m.preflight_checks.pilot_qualification}
                      />
                    </div>
                    <div className="ac-flex ac-justify-between ac-items-center ac-card" style={{ padding: "6px 10px" }}>
                      <span className="ac-text-xs">Airspace Auth</span>
                      <StatusBadge
                        status={m.preflight_checks.airspace_authorization === "PASS" ? "COMPLIANT" : "NON_COMPLIANT"}
                        label={m.preflight_checks.airspace_authorization}
                      />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Battery Lifecycle & Installed Pack */}
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
            <strong className="ac-text-sm">Power & Battery System</strong>
            {battery && (
              <StatusBadge
                status={battery.status === "GOOD" ? "COMPLIANT" : battery.status === "MONITOR" || battery.status === "SERVICE_DUE" ? "REVIEW_REQUIRED" : "NON_COMPLIANT"}
                label={battery.status}
              />
            )}
          </div>

          {battery ? (
            <div
              className="ac-grid-4"
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                gap: "var(--ac-space-3)",
              }}
            >
              <div>
                <span className="ac-text-xs ac-text-muted">Serial Number</span>
                <p className="ac-text-sm" style={{ margin: "2px 0 0", fontWeight: 600 }}>
                  {battery.serial_number}
                </p>
              </div>
              <div>
                <span className="ac-text-xs ac-text-muted">Model / Chemistry</span>
                <p className="ac-text-sm" style={{ margin: "2px 0 0", fontWeight: 600 }}>
                  {battery.model ?? "LiPo Smart Pack"}
                </p>
              </div>
              <div>
                <span className="ac-text-xs ac-text-muted">Cycle Count</span>
                <p className="ac-text-sm" style={{ margin: "2px 0 0", fontWeight: 600 }}>
                  {battery.cycle_count} cycles
                </p>
              </div>
              <div>
                <span className="ac-text-xs ac-text-muted">Nominal Voltage & Capacity</span>
                <p className="ac-text-sm" style={{ margin: "2px 0 0", fontWeight: 600 }}>
                  {battery.voltage ?? "—"}V • {battery.capacity_mah ?? "—"} mAh
                </p>
              </div>
            </div>
          ) : (
            <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
              No battery currently installed.
            </p>
          )}
        </div>

        {/* Installed Components & Traceability */}
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <strong className="ac-text-sm">Configuration & Installed Components ({components.length})</strong>
          <div style={{ marginTop: 10 }}>
            {components.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">No line-replaceable components registered.</p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--ac-border)", textAlign: "left" }}>
                      <th style={{ padding: "6px 8px" }}>Component</th>
                      <th style={{ padding: "6px 8px" }}>Manufacturer / Model</th>
                      <th style={{ padding: "6px 8px" }}>Serial Number</th>
                      <th style={{ padding: "6px 8px" }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {components.map((c) => (
                      <tr key={c.id} style={{ borderBottom: "1px solid var(--ac-border)" }}>
                        <td style={{ padding: "8px" }}>
                          <strong>{c.name}</strong>
                          <div className="ac-text-xs ac-text-muted">{c.component_type}</div>
                        </td>
                        <td style={{ padding: "8px" }}>{c.manufacturer ? `${c.manufacturer} ${c.model ?? ""}` : (c.model ?? "—")}</td>
                        <td style={{ padding: "8px" }}>{c.serial_number ?? "—"}</td>
                        <td style={{ padding: "8px" }}>
                          <StatusBadge
                            status={c.status === "SERVICEABLE" || c.status === "ACTIVE" ? "COMPLIANT" : "NON_COMPLIANT"}
                            label={c.status}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Flight Operations History */}
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <strong className="ac-text-sm">Flight Operations Log ({flights.length})</strong>
          <div style={{ marginTop: 10 }}>
            {flights.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">No flight records logged.</p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--ac-border)", textAlign: "left" }}>
                      <th style={{ padding: "6px 8px" }}>Flight Date</th>
                      <th style={{ padding: "6px 8px" }}>Duration</th>
                      <th style={{ padding: "6px 8px" }}>Cycles</th>
                      <th style={{ padding: "6px 8px" }}>Pilot</th>
                      <th style={{ padding: "6px 8px" }}>Mission Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {flights.map((f) => (
                      <tr key={f.id} style={{ borderBottom: "1px solid var(--ac-border)" }}>
                        <td style={{ padding: "8px" }}>{new Date(f.flown_at).toLocaleDateString()}</td>
                        <td style={{ padding: "8px" }}>{f.duration_minutes} mins</td>
                        <td style={{ padding: "8px" }}>{f.cycles}</td>
                        <td style={{ padding: "8px" }}>{f.pilot_user_id ?? "Chief Pilot"}</td>
                        <td style={{ padding: "8px" }}>{f.notes ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Maintenance Schedule */}
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <strong className="ac-text-sm">Maintenance & Inspection Requirements ({maintenance.length})</strong>
          <div style={{ marginTop: 10 }}>
            {maintenance.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">No maintenance rules configured for this drone.</p>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--ac-border)", textAlign: "left" }}>
                      <th style={{ padding: "6px 8px" }}>Task / Title</th>
                      <th style={{ padding: "6px 8px" }}>Interval</th>
                      <th style={{ padding: "6px 8px" }}>Due Status</th>
                      <th style={{ padding: "6px 8px" }}>Status / Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {maintenance.map((m) => (
                      <tr key={m.requirement.id} style={{ borderBottom: "1px solid var(--ac-border)" }}>
                        <td style={{ padding: "8px" }}>
                          <strong>{m.requirement.description}</strong>
                          {m.requirement.task_reference && (
                            <div className="ac-text-xs ac-text-muted">{m.requirement.task_reference}</div>
                          )}
                        </td>
                        <td style={{ padding: "8px" }}>
                          {m.requirement.fh_interval
                            ? `${m.requirement.fh_interval} FH`
                            : m.requirement.fc_interval
                            ? `${m.requirement.fc_interval} FC`
                            : m.requirement.calendar_interval_days
                            ? `${m.requirement.calendar_interval_days} Days`
                            : m.requirement.interval_type}
                        </td>
                        <td style={{ padding: "8px" }}>
                          <StatusBadge
                            status={m.due_status === "NOT_DUE" ? "COMPLIANT" : m.due_status === "DUE_SOON" ? "REVIEW_REQUIRED" : "NON_COMPLIANT"}
                            label={m.due_status}
                          />
                        </td>
                        <td style={{ padding: "8px" }}>{m.reason ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Findings & Compliance */}
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <strong className="ac-text-sm">Findings & Dispositions ({findings.length})</strong>
          <div style={{ marginTop: 10 }}>
            {findings.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">No open or historical findings recorded for this airframe.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {findings.map((f) => (
                  <div
                    key={f.id}
                    className="ac-card"
                    style={{
                      padding: "var(--ac-space-3)",
                      borderLeft: `3px solid ${f.severity === "CRITICAL" ? "var(--ac-status-non-compliant)" : f.severity === "MAJOR" ? "#f59e0b" : "var(--ac-border)"}`,
                    }}
                  >
                    <div className="ac-flex ac-justify-between ac-items-center">
                      <div>
                        <strong>{f.title}</strong>
                        <span className="ac-text-xs ac-text-muted" style={{ marginLeft: 8 }}>
                          [{f.severity}]
                        </span>
                      </div>
                      <StatusBadge
                        status={f.status === "CLOSED" ? "COMPLIANT" : f.status === "IN_PROGRESS" ? "REVIEW_REQUIRED" : "NON_COMPLIANT"}
                        label={f.status}
                      />
                    </div>
                    <p className="ac-text-sm" style={{ margin: "6px 0 0", color: "var(--ac-text-muted)" }}>
                      {f.description}
                    </p>
                    {f.dispositions && f.dispositions.length > 0 && (
                      <div className="ac-text-xs" style={{ marginTop: 6, color: "var(--ac-text-secondary)" }}>
                        Disposition: {f.dispositions[0].disposition_type}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Compliance Determinations for Drone */}
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <div className="ac-flex ac-justify-between ac-items-center" style={{ marginBottom: 10 }}>
            <div>
              <strong className="ac-text-sm">Compliance Determinations ({compliance.length})</strong>
              <p className="ac-text-xs ac-text-muted" style={{ margin: "2px 0 0" }}>
                Asset-scoped regulatory compliance determinations and assessment records.
              </p>
            </div>
            <StatusBadge
              status={
                compliance.length === 0
                  ? "UNKNOWN"
                  : compliance.every((c) => c.status === "COMPLIANT")
                  ? "COMPLIANT"
                  : compliance.some((c) => c.status === "NON_COMPLIANT")
                  ? "NON_COMPLIANT"
                  : "REVIEW_REQUIRED"
              }
              label={
                compliance.length === 0
                  ? "NO DETERMINATIONS"
                  : compliance.every((c) => c.status === "COMPLIANT")
                  ? "ALL COMPLIANT"
                  : compliance.some((c) => c.status === "NON_COMPLIANT")
                  ? "NON-COMPLIANT DETECTED"
                  : "REVIEW REQUIRED"
              }
            />
          </div>

          <div style={{ marginTop: 10 }}>
            {compliance.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">No compliance determinations recorded for this drone asset.</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {compliance.map((c) => (
                  <div
                    key={c.id}
                    className="ac-card"
                    style={{
                      padding: "var(--ac-space-3)",
                      borderLeft: `3px solid ${
                        c.status === "COMPLIANT"
                          ? "var(--ac-status-compliant)"
                          : c.status === "NON_COMPLIANT"
                          ? "var(--ac-status-non-compliant)"
                          : "#f59e0b"
                      }`,
                    }}
                  >
                    <div className="ac-flex ac-justify-between ac-items-center">
                      <div>
                        <strong>{c.requirement_number}</strong>: {c.title}
                        <span className="ac-text-xs ac-text-muted" style={{ marginLeft: 8 }}>
                          [{c.authority}]
                        </span>
                      </div>
                      <StatusBadge status={c.status} label={c.status} />
                    </div>
                    {c.notes && (
                      <p className="ac-text-sm" style={{ margin: "6px 0 0", color: "var(--ac-text-muted)" }}>
                        {c.notes}
                      </p>
                    )}
                    <div className="ac-text-xs ac-text-muted" style={{ marginTop: 6 }}>
                      Evaluated: {c.evaluated_at}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DroneDetailPage() {
  const params = useParams<{ id: string }>();
  const { sessionType } = useSession();

  if (sessionType === "DEMO") {
    return <DemoDroneDetail assetId={params.id} />;
  }
  return <RealDroneDetail assetId={params.id} />;
}
