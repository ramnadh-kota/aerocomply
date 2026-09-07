"use client";

import { useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, workOrderStatusBadge, priorityBadge } from "@/components/status/StatusBadge";
import { workOrders } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getProjectById } from "@/lib/mock/maintenanceProjects";
import type { WorkOrder, WorkOrderStatus, Priority } from "@/lib/mock/types";
import { useEffect } from "react";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { workOrdersApi, type BackendWorkOrder } from "@/lib/api/workOrders";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";

const STATUSES: WorkOrderStatus[] = ["DRAFT", "ASSIGNED", "IN_PROGRESS", "WAITING_PARTS", "WAITING_INSPECTION", "COMPLETED", "CANCELLED"];
const PRIORITIES: Priority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

function RealWorkOrdersList() {
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
      .list(accessToken)
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
  }, [accessToken, isAuthenticated]);

  const columns: Column<BackendWorkOrder>[] = [
    { key: "num", header: "WO#", render: (w) => <span className="ac-mono">{w.work_order_number}</span>, sortValue: (w) => w.work_order_number },
    { key: "aircraft", header: "Aircraft ID", render: (w) => <span className="ac-mono">{w.aircraft_id}</span> },
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
          emptyMessage="No work orders in the connected database yet. Create one via the backend API (POST /work-orders) to see it here."
        >
          <div className="ac-card" style={{ padding: 0 }}>
            <DataTable columns={columns} rows={rows} getRowHref={(w) => `/maintenance/work-orders/${w.id}`} />
          </div>
        </RealDataPanel>
      )}
    </div>
  );
}

export default function WorkOrdersListPage() {
  const { isReal } = useDataMode();
  if (isReal) return <RealWorkOrdersList />;
  return <DemoWorkOrdersListPage />;
}

function DemoWorkOrdersListPage() {
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [priorityFilter, setPriorityFilter] = useState<string>("ALL");
  const [search, setSearch] = useState("");

  const rows = workOrders.filter((w) => {
    if (statusFilter !== "ALL" && w.status !== statusFilter) return false;
    if (priorityFilter !== "ALL" && w.priority !== priorityFilter) return false;
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      const aircraft = getAircraftById(w.aircraftId);
      const haystack = `${w.workOrderNumber} ${w.title} ${aircraft ? currentRegistration(aircraft) : ""}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });

  const columns: Column<WorkOrder>[] = [
    { key: "num", header: "WO#", render: (w) => <span className="ac-mono">{w.workOrderNumber}</span>, sortValue: (w) => w.workOrderNumber },
    { key: "title", header: "Task", render: (w) => w.title },
    {
      key: "aircraft",
      header: "Aircraft",
      render: (w) => {
        const a = getAircraftById(w.aircraftId);
        return a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : w.aircraftId;
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
