"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, assetStatusBadge as statusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  assetsApi,
  type AssetResponse,
  type AssetCreateRequest,
} from "@/lib/api/assets";
import { DEMO_ASSETS } from "@/lib/demo/demoAssets";

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

function RegisterAssetModal({
  isOpen,
  onClose,
  onSubmit,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: AssetCreateRequest) => Promise<void>;
}) {
  const [assetType, setAssetType] = useState("AIRCRAFT");
  const [registration, setRegistration] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [model, setModel] = useState("");
  const [serialNumber, setSerialNumber] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleFormSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!registration.trim()) {
      setFormError("Tail number / registration is required.");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      await onSubmit({
        asset_type: assetType,
        registration: registration.trim().toUpperCase(),
        manufacturer: manufacturer.trim() || undefined,
        model: model.trim() || undefined,
        serial_number: serialNumber.trim() || undefined,
        status,
      });
      onClose();
    } catch (err: any) {
      setFormError(err.message || "Failed to register asset");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.65)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        className="ac-card"
        style={{
          width: "100%",
          maxWidth: 520,
          background: "var(--ac-card-bg, #111827)",
          padding: "24px",
          borderRadius: "12px",
          border: "1px solid var(--ac-border, #374151)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>Register Aerospace Asset</h2>
          <button
            type="button"
            onClick={onClose}
            className="ac-button-secondary"
            style={{ padding: "4px 8px", cursor: "pointer" }}
          >
            ✕
          </button>
        </div>

        {formError && (
          <div
            style={{
              padding: "10px 14px",
              background: "rgba(239, 68, 68, 0.15)",
              border: "1px solid #ef4444",
              borderRadius: "6px",
              color: "#fca5a5",
              marginBottom: 16,
              fontSize: "0.875rem",
            }}
          >
            {formError}
          </div>
        )}

        <form onSubmit={handleFormSubmit}>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: 4 }}>
                Asset Class / Type *
              </label>
              <select
                value={assetType}
                onChange={(e) => setAssetType(e.target.value)}
                style={{ width: "100%", padding: "8px 10px", borderRadius: 6, background: "#1f2937", color: "#fff", border: "1px solid #4b5563" }}
              >
                <option value="AIRCRAFT">Fixed-Wing Aircraft</option>
                <option value="DRONE">Unmanned Drone (sUAS)</option>
                <option value="HELICOPTER">Rotorcraft / Helicopter</option>
                <option value="EVTOL">eVTOL / Advanced Mobility</option>
              </select>
            </div>

            <div>
              <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: 4 }}>
                Registration / Tail Number *
              </label>
              <input
                type="text"
                placeholder="e.g. N737AA, DRN-M300-01"
                value={registration}
                onChange={(e) => setRegistration(e.target.value)}
                required
                style={{ width: "100%", padding: "8px 10px", borderRadius: 6, background: "#1f2937", color: "#fff", border: "1px solid #4b5563" }}
              />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: 4 }}>
                  Manufacturer
                </label>
                <input
                  type="text"
                  placeholder="e.g. Boeing, DJI, Bell"
                  value={manufacturer}
                  onChange={(e) => setManufacturer(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, background: "#1f2937", color: "#fff", border: "1px solid #4b5563" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: 4 }}>
                  Model
                </label>
                <input
                  type="text"
                  placeholder="e.g. 737-800, M300 RTK"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, background: "#1f2937", color: "#fff", border: "1px solid #4b5563" }}
                />
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: 4 }}>
                  Serial Number (MSN/S/N)
                </label>
                <input
                  type="text"
                  placeholder="e.g. MSN-30124"
                  value={serialNumber}
                  onChange={(e) => setSerialNumber(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, background: "#1f2937", color: "#fff", border: "1px solid #4b5563" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: 4 }}>
                  Initial Lifecycle Status
                </label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6, background: "#1f2937", color: "#fff", border: "1px solid #4b5563" }}
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="IN_SERVICE">IN_SERVICE</option>
                  <option value="MAINTENANCE">MAINTENANCE</option>
                  <option value="PLANNED">PLANNED</option>
                </select>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
              <button
                type="button"
                onClick={onClose}
                className="ac-button-secondary"
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="ac-button-primary"
                disabled={submitting}
              >
                {submitting ? "Registering..." : "Register Asset"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

function DemoAssets() {
  const [assets, setAssets] = useState<AssetResponse[]>(DEMO_ASSETS);
  const [searchTerm, setSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [isModalOpen, setIsModalOpen] = useState(false);

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

  async function handleCreateDemoAsset(data: AssetCreateRequest) {
    const newAsset: AssetResponse = {
      id: `demo-asset-${Date.now()}`,
      organization_id: "demo-org-id",
      asset_type: data.asset_type,
      registration: data.registration,
      manufacturer: data.manufacturer || null,
      model: data.model || null,
      serial_number: data.serial_number || null,
      status: data.status || "ACTIVE",
      acquired_at: new Date().toISOString(),
      retired_at: null,
      created_at: new Date().toISOString(),
    };
    setAssets((prev) => [newAsset, ...prev]);
  }

  return (
    <div className="ac-page">
      <PageHeader
        title="Aerospace Fleet Registry"
        subtitle="Unified domain registry for fixed-wing aircraft, unmanned aerial systems (drones), rotorcraft/helicopters, and eVTOL/AAM assets."
        actions={
          <button
            type="button"
            className="ac-button-primary"
            onClick={() => setIsModalOpen(true)}
          >
            + Register Asset
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

      <RegisterAssetModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleCreateDemoAsset}
      />
    </div>
  );
}

function RealAssets() {
  const { accessToken } = useSession();
  const [assets, setAssets] = useState<AssetResponse[]>([]);
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
      const data = await assetsApi.listAssets(accessToken, {
        asset_type: typeFilter === "ALL" ? undefined : typeFilter,
        status: statusFilter === "ALL" ? undefined : statusFilter,
        search: searchTerm.trim() || undefined,
      });
      setAssets(data);
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    fetchAssets();
  }, [accessToken, typeFilter, statusFilter, searchTerm]);

  async function handleCreateRealAsset(data: AssetCreateRequest) {
    if (!accessToken) return;
    await assetsApi.createAsset(accessToken, data);
    await fetchAssets();
  }

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
    { key: "manufacturer", header: "Manufacturer", render: (a) => a.manufacturer ?? "—" },
    { key: "model", header: "Model", render: (a) => a.model ?? "—" },
    { key: "serial_number", header: "Serial / MSN", render: (a) => a.serial_number ?? "—" },
    {
      key: "status",
      header: "Lifecycle Status",
      render: (a) => <StatusBadge {...statusBadge(a.status)} />,
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
            className="ac-button-primary"
            onClick={() => setIsModalOpen(true)}
          >
            + Register Asset
          </button>
        }
      />

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

      <RealDataPanel
        loading={loading}
        error={error}
        isEmpty={assets.length === 0}
        emptyMessage="No assets registered in this fleet yet."
      >
        <div className="ac-card" style={{ padding: 0 }}>
          <div className="ac-table-desktop">
            <DataTable
              columns={columns}
              rows={assets}
              getRowHref={(a) => `/assets/${a.id}`}
            />
          </div>
        </div>
      </RealDataPanel>

      <RegisterAssetModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSubmit={handleCreateRealAsset}
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
