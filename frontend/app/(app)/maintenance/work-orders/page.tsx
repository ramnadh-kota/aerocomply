"use client";

import { Suspense, useState, useEffect } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, workOrderStatusBadge, priorityBadge } from "@/components/status/StatusBadge";
import { workOrders } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getDemoDroneById } from "@/lib/demo/demoDrones";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getProjectById } from "@/lib/mock/maintenanceProjects";
import type { WorkOrder, WorkOrderStatus, Priority } from "@/lib/mock/types";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { workOrdersApi, type BackendWorkOrder } from "@/lib/api/workOrders";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";

const STATUSES: WorkOrderStatus[] = ["DRAFT", "ASSIGNED", "IN_PROGRESS", "WAITING_PARTS", "WAITING_INSPECTION", "COMPLETED", "CANCELLED"];
const PRIORITIES: Priority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

function RealWorkOrdersList() {
  const searchParams = useSearchParams();
  const assetId = searchParams.get("asset_id");
  const aircraftId = searchParams.get("aircraft_id");

  const { apiBaseUrl } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  const [rows, setRows] = useState<BackendWorkOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    workOrdersApi
      .list(accessToken, {
        asset_id: assetId ?? undefined,
        aircraft_id: aircraftId ?? undefined,
      })
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((err) => {
        if (!cancelled) setError(normalizeApiError(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, isAuthenticated, assetId, aircraftId]);

  const columns: Column<BackendWorkOrder>[] = [
    { key: "num", header: "WO#", render: (w) => <span className="ac-mono">{w.work_order_number}</span>, sortValue: (w) => w.work_order_number },
    { key: "aircraft", header: "Asset / Aircraft", render: (w) => <span className="ac-mono">{w.asset_id || w.aircraft_id || "N/A"}</span> },
    { key: "priority", header: "Priority", render: (w) => <StatusBadge {...priorityBadge(w.priority)} /> },
    { key: "status", header: "Status", render: (w) => <StatusBadge {...workOrderStatusBadge(w.status)} /> },
    { key: "created", header: "Created", render: (w) => new Date(w.created_at).toLocaleDateString(), sortValue: (w) => w.created_at },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Work Orders" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Work Orders</h1>
          <p className="ac-subtitle">REAL data mode — connected to {apiBaseUrl}</p>
        </div>
      </div>

      {(assetId || aircraftId) && (
        <div className="ac-card ac-flex ac-gap-3" style={{ padding: "var(--ac-space-3)", marginBottom: "var(--ac-space-4)", alignItems: "center", justifyContent: "space-between", background: "rgba(59, 130, 246, 0.08)", borderColor: "rgba(59, 130, 246, 0.3)" }}>
          <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
            <span className="ac-badge ac-badge--info">Filtered by {assetId ? "Drone / Asset" : "Aircraft"}</span>
            <span className="ac-mono ac-text-sm">{assetId || aircraftId}</span>
          </div>
          <Link href="/maintenance/work-orders" className="ac-btn ac-btn--sm">
            Clear Filter
          </Link>
        </div>
      )}

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            REAL data mode requires signing in. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <RealDataPanel
          loading={loading}
          error={error}
          isEmpty={rows.length === 0}
          emptyMessage={assetId ? `No work orders found for asset ${assetId}.` : "No work orders in the connected database yet. Create one via the backend API (POST /work-orders) to see it here."}
        >
          <div className="ac-card" style={{ padding: 0 }}>
            <DataTable columns={columns} rows={rows} getRowHref={(w) => `/maintenance/work-orders/${w.id}`} />
          </div>
        </RealDataPanel>
      )}
    </div>
  );
}

function DemoWorkOrdersListPage() {
  const searchParams = useSearchParams();
  const assetId = searchParams.get("asset_id");
  const aircraftId = searchParams.get("aircraft_id");

  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [priorityFilter, setPriorityFilter] = useState<string>("ALL");
  const [search, setSearch] = useState("");

  const rows = workOrders.filter((w) => {
    if (assetId && w.assetId !== assetId && w.aircraftId !== assetId) return false;
    if (aircraftId && w.aircraftId !== aircraftId) return false;
    if (statusFilter !== "ALL" && w.status !== statusFilter) return false;
    if (priorityFilter !== "ALL" && w.priority !== priorityFilter) return false;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      const aircraft = getAircraftById(w.aircraftId);
      const drone = w.assetId ? getDemoDroneById(w.assetId) : undefined;
      const haystack = `${w.workOrderNumber} ${w.title} ${aircraft ? currentRegistration(aircraft) : ""} ${drone ? drone.registration : ""}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  const columns: Column<WorkOrder>[] = [
    { key: "num", header: "WO#", render: (w) => <span className="ac-mono">{w.workOrderNumber}</span>, sortValue: (w) => w.workOrderNumber },
    { key: "title", header: "Task", render: (w) => w.title },
    {
      key: "aircraft",
      header: "Asset / Aircraft",
      render: (w) => {
        if (w.assetId) {
          const drone = getDemoDroneById(w.assetId);
          return drone ? (
            <Link href={`/drones/${drone.id}`} className="ac-mono">
              {drone.registration}
            </Link>
          ) : (
            <span className="ac-mono">{w.assetId}</span>
          );
        }
        const a = getAircraftById(w.aircraftId);
        return a ? (
          <Link href={`/aircraft/${a.id}`} className="ac-mono">
            {currentRegistration(a)}
          </Link>
        ) : (
          w.aircraftId
        );
      },
    },
    {
      key: "project",
      header: "Project",
      render: (w) => {
        const p = w.projectId ? getProjectById(w.projectId) : undefined;
        return p ? <Link href={`/maintenance/projects/${p.id}`} className="ac-mono">{p.projectNumber}</Link> : "Ad hoc";
      },
    },
    { key: "priority", header: "Priority", render: (w) => <StatusBadge {...priorityBadge(w.priority)} /> },
    { key: "tech", header: "Assigned Technician", render: (w) => (w.assignedTechnicianId ? getTechnicianById(w.assignedTechnicianId)?.name : "Unassigned") },
    { key: "due", header: "Due Date", render: (w) => w.dueDate, sortValue: (w) => w.dueDate },
    { key: "status", header: "Status", render: (w) => <StatusBadge {...workOrderStatusBadge(w.status)} /> },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Work Orders" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Work Orders</h1>
          <p className="ac-subtitle">{rows.length} of {workOrders.length} shown</p>
        </div>
      </div>

      {(assetId || aircraftId) && (
        <div className="ac-card ac-flex ac-gap-3" style={{ padding: "var(--ac-space-3)", marginBottom: "var(--ac-space-4)", alignItems: "center", justifyContent: "space-between", background: "rgba(59, 130, 246, 0.08)", borderColor: "rgba(59, 130, 246, 0.3)" }}>
          <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
            <span className="ac-badge ac-badge--info">Filtered by {assetId ? "Drone / Asset" : "Aircraft"}</span>
            <span className="ac-mono ac-text-sm">{assetId || aircraftId}</span>
          </div>
          <Link href="/maintenance/work-orders" className="ac-btn ac-btn--sm">
            Clear Filter
          </Link>
        </div>
      )}

      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap", marginBottom: 10 }}>
          <input
            className="ac-input"
            style={{ width: 240 }}
            placeholder="Search WO#, task, or aircraft…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search work orders"
          />
          <select className="ac-input" style={{ width: 160 }} value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)} aria-label="Filter by priority">
            <option value="ALL">All Priorities</option>
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          <button className="ac-btn" style={statusFilter === "ALL" ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined} onClick={() => setStatusFilter("ALL")}>
            All
          </button>
          {STATUSES.map((s) => (
            <button key={s} className="ac-btn" style={statusFilter === s ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)" } : undefined} onClick={() => setStatusFilter(s)}>
              {s.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={rows} getRowHref={(w) => `/maintenance/work-orders/${w.id}`} />
      </div>
    </div>
  );
}

export default function WorkOrdersListPage() {
  const { isReal } = useDataMode();
  return (
    <Suspense fallback={<div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>Loading work orders...</div>}>
      {isReal ? <RealWorkOrdersList /> : <DemoWorkOrdersListPage />}
    </Suspense>
  );
}
