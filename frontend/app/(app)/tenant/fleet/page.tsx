"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { assetsApi, type AssetResponse } from "@/lib/api/assets";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

const DEMO_FLEET_ASSETS: AssetResponse[] = [
  {
    id: "00000000-0000-0000-0000-000000000061",
    organization_id: "00000000-0000-0000-0000-000000000001",
    asset_type: "AIRCRAFT",
    manufacturer: "Boeing",
    model: "737-800",
    serial_number: "MSN-30124",
    registration: "VT-XYZ",
    status: "ACTIVE",
    acquired_at: "2024-03-01T00:00:00Z",
    retired_at: null,
    created_at: "2024-03-01T00:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000062",
    organization_id: "00000000-0000-0000-0000-000000000001",
    asset_type: "AIRCRAFT",
    manufacturer: "Airbus",
    model: "A320-200",
    serial_number: "MSN-4512",
    registration: "VT-ABC",
    status: "ACTIVE",
    acquired_at: "2024-05-15T00:00:00Z",
    retired_at: null,
    created_at: "2024-05-15T00:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000063",
    organization_id: "00000000-0000-0000-0000-000000000001",
    asset_type: "AIRCRAFT",
    manufacturer: "ATR",
    model: "72-600",
    serial_number: "MSN-1204",
    registration: "VT-REG",
    status: "ACTIVE",
    acquired_at: "2024-08-20T00:00:00Z",
    retired_at: null,
    created_at: "2024-08-20T00:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000064",
    organization_id: "00000000-0000-0000-0000-000000000001",
    asset_type: "AIRCRAFT",
    manufacturer: "De Havilland",
    model: "Dash 8-Q400",
    serial_number: "MSN-4089",
    registration: "VT-EXP",
    status: "STORED",
    acquired_at: "2023-11-10T00:00:00Z",
    retired_at: null,
    created_at: "2023-11-10T00:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000065",
    organization_id: "00000000-0000-0000-0000-000000000001",
    asset_type: "DRONE",
    manufacturer: "KOTA Aerospace",
    model: "Cargo Heavy X1",
    serial_number: "SN-DR-101",
    registration: "VT-KTA",
    status: "ACTIVE",
    acquired_at: "2025-01-10T00:00:00Z",
    retired_at: null,
    created_at: "2025-01-10T00:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000066",
    organization_id: "00000000-0000-0000-0000-000000000001",
    asset_type: "DRONE",
    manufacturer: "AeroVironment",
    model: "Survey Master Pro",
    serial_number: "SN-DR-102",
    registration: "VT-DRN",
    status: "ACTIVE",
    acquired_at: "2025-02-14T00:00:00Z",
    retired_at: null,
    created_at: "2025-02-14T00:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000067",
    organization_id: "00000000-0000-0000-0000-000000000001",
    asset_type: "DRONE",
    manufacturer: "DJI Enterprise",
    model: "Matrice 350 RTK",
    serial_number: "SN-DR-103",
    registration: "VT-SUR",
    status: "ACTIVE",
    acquired_at: "2025-03-01T00:00:00Z",
    retired_at: null,
    created_at: "2025-03-01T00:00:00Z",
  },
];

export default function TenantFleetPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [assets, setAssets] = useState<AssetResponse[]>(
    isDemo ? DEMO_FLEET_ASSETS : []
  );
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [typeFilter, setTypeFilter] = useState("ALL");
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (isDemo) {
      setAssets(DEMO_FLEET_ASSETS);
      setLoading(false);
      return;
    }

    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    assetsApi
      .listAssets(accessToken)
      .then(setAssets)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [isDemo, isAuthenticated, accessToken]);

  const filteredAssets = assets.filter((a) => {
    const matchesType = typeFilter === "ALL" || a.asset_type === typeFilter;
    const q = search.toLowerCase();
    const matchesSearch =
      (a.registration ?? "").toLowerCase().includes(q) ||
      (a.model ?? "").toLowerCase().includes(q) ||
      (a.manufacturer ?? "").toLowerCase().includes(q);
    return matchesType && matchesSearch;
  });

  const aircraftCount = assets.filter((a) => a.asset_type === "AIRCRAFT").length;
  const droneCount = assets.filter((a) => a.asset_type === "DRONE").length;

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Fleet & Assets" },
        ]}
        eyebrow="FLEET GOVERNANCE"
        title="Fleet &amp; Asset Administration"
        subtitle="Tenant-level registry of fixed-wing aircraft, drone UAVs, and future eVTOL/AAM assets."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/aircraft" className="ac-btn">
              Aircraft Floor View →
            </Link>
            <Link href="/drones" className="ac-btn">
              Drone Operations View →
            </Link>
          </div>
        }
      />

      <div style={{ marginBottom: 16 }}>
        {isDemo ? (
          <div
            style={{
              padding: "10px 16px",
              background: "rgba(59, 130, 246, 0.08)",
              border: "1px solid rgba(59, 130, 246, 0.25)",
              borderRadius: 6,
              fontSize: 13,
            }}
          >
            <strong>DEMO MODE</strong> · Viewing mixed fleet for KOTA Aerospace Demo Operations ({aircraftCount} aircraft, {droneCount} drones).
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={filteredAssets.length === 0}
            emptyMessage="No fleet assets registered."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      {/* KPI Cards */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: 16,
          marginBottom: 20,
        }}
      >
        <div className="ac-card">
          <div className="ac-eyebrow">TOTAL FLEET ASSETS</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{assets.length}</div>
          <div className="ac-text-sm" style={{ opacity: 0.7 }}>Registered in tenant scope</div>
        </div>

        <div className="ac-card">
          <div className="ac-eyebrow">FIXED-WING AIRCRAFT</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{aircraftCount}</div>
          <div className="ac-text-sm" style={{ opacity: 0.7 }}>Commercial transport</div>
        </div>

        <div className="ac-card">
          <div className="ac-eyebrow">DRONE UAV FLEET</div>
          <div style={{ fontSize: 24, fontWeight: 700 }}>{droneCount}</div>
          <div className="ac-text-sm" style={{ opacity: 0.7 }}>Autonomous &amp; tactical UAS</div>
        </div>
      </div>

      {/* Search and Filters */}
      <div
        className="ac-card"
        style={{
          padding: 12,
          marginBottom: 16,
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <input
          type="text"
          className="ac-input"
          placeholder="Search by registration, model, manufacturer..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ width: "100%", maxWidth: 360 }}
        />
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <label style={{ fontSize: 13, fontWeight: 500 }}>Asset Class:</label>
          <select
            className="ac-input"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{ minWidth: 160 }}
          >
            <option value="ALL">All Asset Classes ({assets.length})</option>
            <option value="AIRCRAFT">Aircraft ({aircraftCount})</option>
            <option value="DRONE">Drone UAV ({droneCount})</option>
          </select>
        </div>
      </div>

      {/* Table */}
      <div className="ac-card" style={{ padding: 0 }}>
        <div style={{ overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Registration / ID</th>
                <th>Asset Class</th>
                <th>Manufacturer &amp; Model</th>
                <th>Serial Number</th>
                <th>Status</th>
                <th>Acquired</th>
                <th style={{ textAlign: "right" }}>Operational Link</th>
              </tr>
            </thead>
            <tbody>
              {filteredAssets.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "32px 16px", opacity: 0.7 }}>
                    No assets matching filter criteria.
                  </td>
                </tr>
              ) : (
                filteredAssets.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <span className="ac-mono" style={{ fontWeight: 600 }}>
                        {a.registration ?? a.id.slice(0, 8)}
                      </span>
                    </td>
                    <td>
                      <span
                        className="ac-mono"
                        style={{
                          fontSize: 11,
                          padding: "2px 6px",
                          borderRadius: 4,
                          background:
                            a.asset_type === "DRONE"
                              ? "rgba(139, 92, 246, 0.15)"
                              : "rgba(59, 130, 246, 0.15)",
                          color: a.asset_type === "DRONE" ? "#a78bfa" : "#60a5fa",
                          border: "1px solid var(--border-color, #27272a)",
                        }}
                      >
                        {a.asset_type}
                      </span>
                    </td>
                    <td>
                      <div style={{ fontWeight: 500 }}>
                        {a.manufacturer ? `${a.manufacturer} ` : ""}
                        {a.model ?? "Generic Asset"}
                      </div>
                    </td>
                    <td className="ac-mono" style={{ fontSize: 12 }}>
                      {a.serial_number ?? "—"}
                    </td>
                    <td>
                      <StatusBadge
                        status={a.status === "ACTIVE" ? "ACTIVE" : "STORED"}
                        label={a.status}
                      />
                    </td>
                    <td className="ac-mono" style={{ fontSize: 12 }}>
                      {a.acquired_at ? new Date(a.acquired_at).toLocaleDateString() : "—"}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {a.asset_type === "DRONE" ? (
                        <Link
                          href={`/drones/${a.id}`}
                          className="ac-btn"
                          style={{ fontSize: 11, padding: "3px 8px" }}
                        >
                          Drone Detail →
                        </Link>
                      ) : (
                        <Link
                          href={`/aircraft/${a.id}`}
                          className="ac-btn"
                          style={{ fontSize: 11, padding: "3px 8px" }}
                        >
                          Aircraft Detail →
                        </Link>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
