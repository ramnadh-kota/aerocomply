"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, assetStatusBadge as statusBadge, operationalStateBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  assetsApi,
  type AssetResponse,
} from "@/lib/api/assets";
import {
  controlCenterApi,
  type ControlCenterFleetOperationRow,
} from "@/lib/api/controlCenter";
import { AssetRegistrationModal } from "@/components/assets/AssetRegistrationModal";
import { demoStore } from "@/lib/demo/demoStore";

const ASSET_TYPE_ICONS: Record<string, string> = {
  AIRCRAFT: "✈",
  DRONE: "◆",
  HELICOPTER: "🚁",
  EVTOL: "⚡",
  AAM: "✦",
  OTHER: "▤",
};

const ASSET_TYPE_LABELS: Record<string, string> = {
  ALL: "All Assets",
  AIRCRAFT: "Fixed-Wing Aircraft",
  DRONE: "Unmanned Drones (sUAS)",
  HELICOPTER: "Rotorcraft / Helicopters",
  EVTOL: "eVTOL / Advanced Mobility",
};

interface FleetDisplayRow {
  id: string;
  asset_type: string;
  registration: string | null;
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  status: string;
  operational_state?: string;
  readiness_state?: string;
  total_flight_hours?: number;
  total_cycles?: number;
  last_flight_at?: string | null;
  next_action?: string | null;
}

function DemoAssets() {
  const [assets, setAssets] = useState<AssetResponse[]>(demoStore.getAssets());
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    setAssets(demoStore.getAssets());
    return demoStore.subscribe(() => {
      setAssets(demoStore.getAssets());
    });
  }, []);

  const stats = useMemo(() => {
    return {
      total: assets.length,
      aircraft: assets.filter((a) => a.asset_type === "AIRCRAFT").length,
      drones: assets.filter((a) => a.asset_type === "DRONE").length,
      helicopters: assets.filter((a) => a.asset_type === "HELICOPTER").length,
      evtol: assets.filter((a) => a.asset_type === "EVTOL" || a.asset_type === "AAM").length,
      inService: assets.filter((a) => a.status === "IN_SERVICE" || a.status === "ACTIVE").length,
    };
  }, [assets]);

  const filteredAssets = useMemo(() => {
    return assets.filter((a) => {
      const q = searchTerm.toLowerCase();
      const matchesSearch =
        !q ||
        (a.registration?.toLowerCase() ?? "").includes(q) ||
        (a.manufacturer?.toLowerCase() ?? "").includes(q) ||
        (a.model?.toLowerCase() ?? "").includes(q) ||
        (a.serial_number?.toLowerCase() ?? "").includes(q);

      const matchesType =
        typeFilter === "ALL" ||
        a.asset_type === typeFilter ||
        (typeFilter === "EVTOL" && a.asset_type === "AAM");

      const matchesStatus = statusFilter === "ALL" || a.status === statusFilter;
      return matchesSearch && matchesType && matchesStatus;
    });
  }, [assets, searchTerm, typeFilter, statusFilter]);

  const columns: Column<AssetResponse>[] = [
    {
      key: "asset_type",
      header: "Class",
      render: (a) => (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontWeight: 600,
            fontSize: "0.85rem",
            color: "var(--ac-primary, #38bdf8)",
          }}
        >
          <span>{ASSET_TYPE_ICONS[a.asset_type] || "✈"}</span>
          <span>{a.asset_type}</span>
        </span>
      ),
    },
    {
      key: "registration",
      header: "Registration / Identifier",
      render: (a) => (
        <Link href={`/assets/${a.id}`} className="ac-link" style={{ fontWeight: 700 }}>
          {a.registration}
        </Link>
      ),
    },
    {
      key: "manufacturer",
      header: "Manufacturer",
      render: (a) => a.manufacturer ?? "—",
    },
    {
      key: "model",
      header: "Model",
      render: (a) => a.model ?? "—",
    },
    {
      key: "serial_number",
      header: "Serial / MSN",
      render: (a) => a.serial_number ?? "—",
    },
    {
      key: "status",
      header: "Lifecycle Status",
      render: (a) => <StatusBadge {...statusBadge(a.status)} />,
    },
    {
      key: "actions",
      header: "Direct Console",
      render: (a) => (
        <div style={{ display: "flex", gap: 6 }}>
          <Link
            href={`/assets/${a.id}`}
            className="ac-button-secondary"
            style={{ fontSize: "0.75rem", padding: "4px 8px" }}
          >
            Universal Detail
          </Link>
          {a.asset_type === "DRONE" && (
            <Link
              href={`/drones/${a.id}`}
              className="ac-button-secondary"
              style={{ fontSize: "0.75rem", padding: "4px 8px", color: "#38bdf8" }}
            >
              Drone Ops →
            </Link>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="ac-page">
      <PageHeader
        title="Aerospace Fleet Registry"
        subtitle="Unified domain registry for fixed-wing aircraft, unmanned aerial systems (drones), rotorcraft/helicopters, and eVTOL/AAM assets."
        actions={
          <button
            type="button"
            className="ac-btn"
            style={{ background: "var(--ac-primary, #38bdf8)", color: "#000", fontWeight: 600 }}
            onClick={() => setIsModalOpen(true)}
          >
            + Add Asset
          </button>
        }
      />

      {/* KPI Highlights */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 12,
          marginBottom: 20,
        }}
      >
        <div className="ac-card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--ac-text-muted, #9ca3af)", textTransform: "uppercase" }}>
            Total Airframes
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "#fff", marginTop: 4 }}>
            {stats.total}
          </div>
        </div>
        <div className="ac-card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", color: "#9ca3af", textTransform: "uppercase" }}>
            ✈ Fixed-Wing
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "#38bdf8", marginTop: 4 }}>
            {stats.aircraft}
          </div>
        </div>
        <div className="ac-card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", color: "#9ca3af", textTransform: "uppercase" }}>
            ◆ Drones (sUAS)
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "#a855f7", marginTop: 4 }}>
            {stats.drones}
          </div>
        </div>
        <div className="ac-card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", color: "#9ca3af", textTransform: "uppercase" }}>
            🚁 Rotorcraft
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "#10b981", marginTop: 4 }}>
            {stats.helicopters}
          </div>
        </div>
        <div className="ac-card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", color: "#9ca3af", textTransform: "uppercase" }}>
            ⚡ eVTOL / AAM
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "#f59e0b", marginTop: 4 }}>
            {stats.evtol}
          </div>
        </div>
      </div>

      {/* Asset Type Filter Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {["ALL", "AIRCRAFT", "DRONE", "HELICOPTER", "EVTOL"].map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => setTypeFilter(type)}
            className={typeFilter === type ? "ac-button-primary" : "ac-button-secondary"}
            style={{ fontSize: "0.85rem", padding: "6px 14px", borderRadius: "20px" }}
          >
            {ASSET_TYPE_ICONS[type] ? `${ASSET_TYPE_ICONS[type]} ` : ""}
            {ASSET_TYPE_LABELS[type]}
          </button>
        ))}
      </div>

      {/* Search & Status Filters */}
      <div
        className="ac-card"
        style={{
          padding: "12px 16px",
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 16,
          alignItems: "center",
        }}
      >
        <input
          type="text"
          placeholder="Search tail, model, manufacturer, serial..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{
            flex: 1,
            minWidth: 240,
            padding: "8px 12px",
            background: "#1f2937",
            border: "1px solid #374151",
            borderRadius: 6,
            color: "#fff",
            fontSize: "0.875rem",
          }}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{
            padding: "8px 12px",
            background: "#1f2937",
            border: "1px solid #374151",
            borderRadius: 6,
            color: "#fff",
            fontSize: "0.875rem",
          }}
        >
          <option value="ALL">All Lifecycle States</option>
          <option value="ACTIVE">ACTIVE</option>
          <option value="IN_SERVICE">IN_SERVICE</option>
          <option value="MAINTENANCE">MAINTENANCE</option>
          <option value="INSPECTION">INSPECTION</option>
          <option value="GROUNDED">GROUNDED</option>
          <option value="RETIRED">RETIRED</option>
        </select>
      </div>

      {/* Fleet Table */}
      <div className="ac-card" style={{ padding: 0 }}>
        <div className="ac-table-desktop">
          <DataTable
            columns={columns}
            rows={filteredAssets}
            getRowHref={(a) => `/assets/${a.id}`}
          />
        </div>
      </div>

      <AssetRegistrationModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
      />
    </div>
  );
}

function RealAssets() {
  const { accessToken } = useSession();
  const [fleetOps, setFleetOps] = useState<ControlCenterFleetOperationRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [isModalOpen, setIsModalOpen] = useState(false);

  async function fetchAssets() {
    if (!accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const ops = await controlCenterApi.getFleetOperations(accessToken);
      setFleetOps(ops);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAssets();
  }, [accessToken]);

  const filteredFleet = useMemo(() => {
    return fleetOps.filter((a) => {
      const q = searchTerm.toLowerCase();
      const matchesSearch =
        !q ||
        (a.registration?.toLowerCase() ?? "").includes(q) ||
        (a.manufacturer?.toLowerCase() ?? "").includes(q) ||
        (a.model?.toLowerCase() ?? "").includes(q) ||
        (a.serial_number?.toLowerCase() ?? "").includes(q);

      const matchesType =
        typeFilter === "ALL" ||
        a.asset_type === typeFilter ||
        (typeFilter === "EVTOL" && a.asset_type === "AAM");

      const matchesStatus =
        statusFilter === "ALL" ||
        a.lifecycle_status === statusFilter ||
        a.operational_state === statusFilter;

      return matchesSearch && matchesType && matchesStatus;
    });
  }, [fleetOps, searchTerm, typeFilter, statusFilter]);

  const stats = useMemo(() => {
    return {
      total: fleetOps.length,
      aircraft: fleetOps.filter((a) => a.asset_type === "AIRCRAFT").length,
      drones: fleetOps.filter((a) => a.asset_type === "DRONE").length,
      helicopters: fleetOps.filter((a) => a.asset_type === "HELICOPTER").length,
      evtol: fleetOps.filter((a) => a.asset_type === "EVTOL" || a.asset_type === "AAM").length,
      ready: fleetOps.filter((a) => a.readiness_state === "READY").length,
      blocked: fleetOps.filter((a) => a.readiness_state === "BLOCKED").length,
    };
  }, [fleetOps]);

  const columns: Column<ControlCenterFleetOperationRow>[] = [
    {
      key: "asset_type",
      header: "Class",
      render: (a) => (
        <span
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontWeight: 600,
            fontSize: "0.85rem",
            color: "var(--ac-primary, #38bdf8)",
          }}
        >
          <span>{ASSET_TYPE_ICONS[a.asset_type] || "✈"}</span>
          <span>{a.asset_type}</span>
        </span>
      ),
    },
    {
      key: "registration",
      header: "Registration / Identifier",
      render: (a) => (
        <Link href={`/assets/${a.asset_id}`} className="ac-link" style={{ fontWeight: 700 }}>
          {a.registration || "—"}
        </Link>
      ),
    },
    { key: "manufacturer", header: "Manufacturer / Model", render: (a) => `${a.manufacturer || "—"} ${a.model ? `· ${a.model}` : ""}` },
    {
      key: "operational_state",
      header: "Operational State",
      render: (a) => <StatusBadge {...operationalStateBadge(a.operational_state)} />,
    },
    {
      key: "readiness_state",
      header: "Readiness",
      render: (a) => (
        <span
          style={{
            fontSize: "0.75rem",
            fontWeight: 700,
            padding: "3px 8px",
            borderRadius: 4,
            background: a.readiness_state === "READY" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
            color: a.readiness_state === "READY" ? "#10b981" : "#ef4444",
          }}
        >
          {a.readiness_state}
        </span>
      ),
    },
    {
      key: "total_flight_hours",
      header: "Flight Hours",
      render: (a) => <span className="ac-mono">{a.total_flight_hours} hrs</span>,
    },
    {
      key: "total_cycles",
      header: "Cycles",
      render: (a) => <span className="ac-mono">{a.total_cycles}</span>,
    },
    {
      key: "next_action",
      header: "Next Required Action",
      render: (a) => <span className="ac-text-sm" style={{ color: "#d1d5db" }}>{a.next_action || "Ready"}</span>,
    },
    {
      key: "actions",
      header: "Console",
      render: (a) => (
        <div style={{ display: "flex", gap: 6 }}>
          <Link
            href={`/assets/${a.asset_id}`}
            className="ac-button-secondary"
            style={{ fontSize: "0.75rem", padding: "4px 8px" }}
          >
            Workspace →
          </Link>
        </div>
      ),
    },
  ];

  return (
    <div className="ac-page">
      <PageHeader
        title="Aerospace Fleet Operations"
        subtitle="Unified operational workspace across fixed-wing aircraft, drones (sUAS), helicopters, and eVTOL assets."
        actions={
          <div style={{ display: "flex", gap: 8 }}>
            <Link
              href="/import"
              className="ac-btn"
              style={{ background: "#374151", color: "#fff" }}
            >
              Import Flight Data
            </Link>
            <button
              type="button"
              className="ac-btn"
              style={{ background: "var(--ac-primary, #38bdf8)", color: "#000", fontWeight: 600 }}
              onClick={() => setIsModalOpen(true)}
            >
              + Add Asset
            </button>
          </div>
        }
      />

      {/* KPI Highlights */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          gap: 12,
          marginBottom: 20,
        }}
      >
        <div className="ac-card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--ac-text-muted, #9ca3af)", textTransform: "uppercase" }}>
            Total Airframes
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "#fff", marginTop: 4 }}>
            {stats.total}
          </div>
        </div>
        <div className="ac-card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", color: "#9ca3af", textTransform: "uppercase" }}>
            Operational Ready
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "#10b981", marginTop: 4 }}>
            {stats.ready} <span style={{ fontSize: "0.85rem", color: "#9ca3af" }}>/ {stats.total}</span>
          </div>
        </div>
        <div className="ac-card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", color: "#9ca3af", textTransform: "uppercase" }}>
            Restricted / Blocked
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: stats.blocked > 0 ? "#ef4444" : "#10b981", marginTop: 4 }}>
            {stats.blocked}
          </div>
        </div>
        <div className="ac-card" style={{ padding: "16px 20px" }}>
          <div style={{ fontSize: "0.75rem", color: "#9ca3af", textTransform: "uppercase" }}>
            ✈ Aircraft / ◆ Drones
          </div>
          <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "#38bdf8", marginTop: 4 }}>
            {stats.aircraft} / {stats.drones}
          </div>
        </div>
      </div>

      {/* Asset Type Filter Tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        {["ALL", "AIRCRAFT", "DRONE", "HELICOPTER", "EVTOL"].map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => setTypeFilter(type)}
            className={typeFilter === type ? "ac-button-primary" : "ac-button-secondary"}
            style={{ fontSize: "0.85rem", padding: "6px 14px", borderRadius: "20px" }}
          >
            {ASSET_TYPE_ICONS[type] ? `${ASSET_TYPE_ICONS[type]} ` : ""}
            {ASSET_TYPE_LABELS[type]}
          </button>
        ))}
      </div>

      {/* Search & Status Filters */}
      <div
        className="ac-card"
        style={{
          padding: "12px 16px",
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 16,
          alignItems: "center",
        }}
      >
        <input
          type="text"
          placeholder="Search tail, model, manufacturer, serial..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{
            flex: 1,
            minWidth: 240,
            padding: "8px 12px",
            background: "#1f2937",
            border: "1px solid #374151",
            borderRadius: 6,
            color: "#fff",
            fontSize: "0.875rem",
          }}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{
            padding: "8px 12px",
            background: "#1f2937",
            border: "1px solid #374151",
            borderRadius: 6,
            color: "#fff",
            fontSize: "0.875rem",
          }}
        >
          <option value="ALL">All Operational States</option>
          <option value="AVAILABLE">AVAILABLE</option>
          <option value="IN_MISSION">IN_MISSION</option>
          <option value="MAINTENANCE">MAINTENANCE</option>
          <option value="UNDER_INSPECTION">UNDER_INSPECTION</option>
          <option value="GROUNDED">GROUNDED</option>
          <option value="AOG">AOG</option>
          <option value="INACTIVE">INACTIVE</option>
        </select>
      </div>

      <RealDataPanel
        loading={loading}
        error={error}
        isEmpty={fleetOps.length === 0}
        emptyMessage="No assets registered in this fleet yet."
      >
        <div className="ac-card" style={{ padding: 0 }}>
          <div className="ac-table-desktop">
            <DataTable
              columns={columns}
              rows={filteredFleet}
              getRowHref={(a) => `/assets/${a.asset_id}`}
            />
          </div>
        </div>
      </RealDataPanel>

      <AssetRegistrationModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onCreated={() => fetchAssets()}
      />
    </div>
  );
}

export default function AssetsPage() {
  const { sessionType } = useSession();
  if (sessionType === "DEMO") {
    return <DemoAssets />;
  }
  return <RealAssets />;
}
