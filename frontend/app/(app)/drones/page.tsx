"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, assetStatusBadge as statusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { dronesApi, type DroneResponse } from "@/lib/api/drones";
import {
  DEMO_DRONES,
  getDemoDeploymentReadiness,
  getDemoFleetStatistics,
} from "@/lib/demo/demoDrones";

function DemoDrones() {
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const stats = useMemo(() => getDemoFleetStatistics(), []);

  const filteredDrones = useMemo(() => {
    return DEMO_DRONES.filter((d) => {
      const matchesSearch =
        (d.registration?.toLowerCase() ?? "").includes(searchTerm.toLowerCase()) ||
        (d.manufacturer?.toLowerCase() ?? "").includes(searchTerm.toLowerCase()) ||
        (d.model?.toLowerCase() ?? "").includes(searchTerm.toLowerCase());

      const matchesStatus = statusFilter === "ALL" || d.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [searchTerm, statusFilter]);

  const columns: Column<DroneResponse>[] = [
    {
      key: "registration",
      header: "Drone ID",
      render: (d) => (
        <Link href={`/drones/${d.id}`} className="ac-link" style={{ fontWeight: 600 }}>
          {d.registration}
        </Link>
      ),
    },
    { key: "manufacturer", header: "Manufacturer", render: (d) => d.manufacturer ?? "—" },
    { key: "model", header: "Model", render: (d) => d.model ?? "—" },
    {
      key: "status",
      header: "Status",
      render: (d) => <StatusBadge {...statusBadge(d.status)} />,
    },
    {
      key: "readiness",
      header: "Deployment Readiness",
      render: (d) => {
        const readiness = getDemoDeploymentReadiness(d.id);
        return (
          <StatusBadge
            status={readiness.status === "READY" ? "COMPLIANT" : "NON_COMPLIANT"}
            label={readiness.status === "READY" ? "READY FOR FLIGHT" : `BLOCKED (${readiness.blockers.length})`}
          />
        );
      },
    },
  ];

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Drones" }]}
        title="Drone Fleet Operations"
        subtitle="Operational drone fleet, configurations, battery health, maintenance schedules, and pre-flight readiness."
      />

      {/* Dynamic Fleet KPI Statistics */}
      <div
        className="ac-grid-4"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "var(--ac-space-4)",
          marginBottom: "var(--ac-space-4)",
        }}
      >
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <span className="ac-text-sm" style={{ color: "var(--ac-text-muted)" }}>
            Total Fleet
          </span>
          <div style={{ fontSize: 24, fontWeight: 700, marginTop: 4 }}>{stats.totalDrones}</div>
          <span className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>
            Active Airframes: {stats.totalDrones - stats.groundedDrones}
          </span>
        </div>

        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <span className="ac-text-sm" style={{ color: "var(--ac-text-muted)" }}>
            Operationally Ready
          </span>
          <div style={{ fontSize: 24, fontWeight: 700, marginTop: 4, color: "var(--ac-status-compliant)" }}>
            {stats.readyDrones}
          </div>
          <span className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>
            {stats.blockedDrones} Blocked / Attention Required
          </span>
        </div>

        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <span className="ac-text-sm" style={{ color: "var(--ac-text-muted)" }}>
            Maintenance Overdue
          </span>
          <div
            style={{
              fontSize: 24,
              fontWeight: 700,
              marginTop: 4,
              color: stats.maintenanceDueDrones > 0 ? "var(--ac-status-non-compliant)" : "var(--ac-text-primary)",
            }}
          >
            {stats.maintenanceDueDrones}
          </div>
          <span className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>
            Inspection & service due
          </span>
        </div>

        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <span className="ac-text-sm" style={{ color: "var(--ac-text-muted)" }}>
            Open Findings
          </span>
          <div
            style={{
              fontSize: 24,
              fontWeight: 700,
              marginTop: 4,
              color: stats.openFindingsCount > 0 ? "var(--ac-status-in-progress)" : "var(--ac-text-primary)",
            }}
          >
            {stats.openFindingsCount}
          </div>
          <span className="ac-text-xs" style={{ color: "var(--ac-text-muted)" }}>
            Total Flight Hours: {stats.totalFlightHours}h
          </span>
        </div>
      </div>

      {/* Fleet Controls / Filter */}
      <div
        className="ac-card ac-section"
        style={{
          padding: "var(--ac-space-4)",
          display: "flex",
          gap: "var(--ac-space-3)",
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <input
          className="ac-input"
          style={{ width: 240 }}
          placeholder="Search drone ID, make, model…"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          aria-label="Search Drones"
        />
        <select
          className="ac-input"
          style={{ width: 160 }}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          aria-label="Status Filter"
        >
          <option value="ALL">All Statuses</option>
          <option value="ACTIVE">Active Only</option>
          <option value="GROUNDED">Grounded Only</option>
          <option value="MAINTENANCE">Maintenance Only</option>
        </select>
        <span className="ac-text-xs" style={{ color: "var(--ac-text-muted)", marginLeft: "auto" }}>
          Showing {filteredDrones.length} of {DEMO_DRONES.length} synthetic aircraft
        </span>
      </div>

      {/* Fleet Table */}
      <div className="ac-card" style={{ padding: 0 }}>
        <div className="ac-table-desktop">
          <DataTable columns={columns} rows={filteredDrones} getRowHref={(d) => `/drones/${d.id}`} />
        </div>
        <div className="ac-row-cards">
          {filteredDrones.map((d) => {
            const readiness = getDemoDeploymentReadiness(d.id);
            return (
              <div className="ac-row-card" key={d.id}>
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Drone ID</span>
                  <strong>
                    <Link href={`/drones/${d.id}`}>{d.registration}</Link>
                  </strong>
                </div>
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Manufacturer</span>
                  <span>{d.manufacturer ?? "—"}</span>
                </div>
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Model</span>
                  <span>{d.model ?? "—"}</span>
                </div>
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Status</span>
                  <StatusBadge {...statusBadge(d.status)} />
                </div>
                <div className="ac-row-card-field">
                  <span className="ac-row-card-field-label">Readiness</span>
                  <StatusBadge
                    status={readiness.status === "READY" ? "COMPLIANT" : "NON_COMPLIANT"}
                    label={readiness.status === "READY" ? "READY" : "BLOCKED"}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function RealDrones() {
  const { accessToken, isAuthenticated } = useSession();
  const [drones, setDrones] = useState<DroneResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [registration, setRegistration] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [model, setModel] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<NormalizedApiError | null>(null);

  const load = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    dronesApi
      .listDrones(accessToken)
      .then(setDrones)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated]);

  const createDrone = () => {
    if (!accessToken || !registration.trim()) return;
    setCreating(true);
    setCreateError(null);
    dronesApi
      .createDrone(accessToken, {
        registration: registration.trim(),
        manufacturer: manufacturer.trim() || null,
        model: model.trim() || null,
      })
      .then(() => {
        setRegistration("");
        setManufacturer("");
        setModel("");
        load();
      })
      .catch((err) => setCreateError(normalizeApiError(err)))
      .finally(() => setCreating(false));
  };

  const columns: Column<DroneResponse>[] = [
    {
      key: "registration",
      header: "Drone ID",
      render: (d) => <Link href={`/drones/${d.id}`}>{d.registration}</Link>,
    },
    { key: "manufacturer", header: "Manufacturer", render: (d) => d.manufacturer ?? "—" },
    { key: "model", header: "Model", render: (d) => d.model ?? "—" },
    { key: "status", header: "Status", render: (d) => <StatusBadge {...statusBadge(d.status)} /> },
  ];

  const forbidden = error?.kind === "forbidden";

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Drones" }]}
        title="Drones"
        subtitle="Drone assets, batteries, components, flights, and deployment readiness."
      />

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Sign in to view drones. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to view drones.
          </p>
        </div>
      ) : (
        <>
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Create a drone</strong>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
              <input
                className="ac-input"
                style={{ width: 140 }}
                placeholder="DRN-001"
                value={registration}
                onChange={(e) => setRegistration(e.target.value)}
                aria-label="Drone ID"
              />
              <input
                className="ac-input"
                style={{ width: 160 }}
                placeholder="Manufacturer"
                value={manufacturer}
                onChange={(e) => setManufacturer(e.target.value)}
                aria-label="Manufacturer"
              />
              <input
                className="ac-input"
                style={{ width: 160 }}
                placeholder="Model"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                aria-label="Model"
              />
              <button className="ac-btn" onClick={createDrone} disabled={creating || !registration.trim()}>
                {creating ? "Creating…" : "Create Drone"}
              </button>
            </div>
            {createError && (
              <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                {createError.message}
              </p>
            )}
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={drones.length === 0}
            emptyMessage="No drones have been created yet."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <div className="ac-table-desktop">
                <DataTable columns={columns} rows={drones} getRowHref={(d) => `/drones/${d.id}`} />
              </div>
              <div className="ac-row-cards">
                {drones.map((d) => (
                  <div className="ac-row-card" key={d.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Drone ID</span>
                      <strong>
                        <Link href={`/drones/${d.id}`}>{d.registration}</Link>
                      </strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Manufacturer</span>
                      <span>{d.manufacturer ?? "—"}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Model</span>
                      <span>{d.model ?? "—"}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Status</span>
                      <StatusBadge {...statusBadge(d.status)} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </RealDataPanel>
        </>
      )}
    </div>
  );
}

export default function DronesPage() {
  const { sessionType } = useSession();
  if (sessionType === "DEMO") {
    return <DemoDrones />;
  }
  return <RealDrones />;
}
