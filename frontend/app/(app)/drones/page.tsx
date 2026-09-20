"use client";

// Phase 18.6: Drone Operations. REAL-mode tenant page. Drone identity is
// the existing Asset (asset_type=DRONE) -- see backend/app/services/
// drone_service.py.

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, assetStatusBadge as statusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { dronesApi, type DroneResponse } from "@/lib/api/drones";

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
  return <RealDrones />;
}
