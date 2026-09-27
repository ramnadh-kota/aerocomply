"use client";

import { Suspense, useState, useEffect, useCallback, useMemo } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, workOrderStatusBadge, priorityBadge, overdueBadge } from "@/components/status/StatusBadge";
import { workOrders } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getDemoDroneById } from "@/lib/demo/demoDrones";
import { getTechnicianById } from "@/lib/mock/technicians";
import { getProjectById } from "@/lib/mock/maintenanceProjects";
import type { WorkOrder, WorkOrderStatus, Priority } from "@/lib/mock/types";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import {
  workOrdersApi,
  type BackendWorkOrder,
  type WorkOrderCreatePayload,
} from "@/lib/api/workOrders";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";

const STATUSES = [
  "ALL",
  "DRAFT",
  "OPEN",
  "PLANNED",
  "ASSIGNED",
  "IN_PROGRESS",
  "ON_HOLD",
  "INSPECTION",
  "COMPLETED",
  "CLOSED",
  "CANCELLED",
] as const;

const PRIORITIES: Priority[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

const WORK_ORDER_TYPES = [
  "ALL",
  "CORRECTIVE",
  "PREVENTIVE",
  "SCHEDULED",
  "INSPECTION",
  "COMPONENT_REPLACEMENT",
  "DEFECT_RECTIFICATION",
  "COMPLIANCE",
  "AOG",
] as const;

function isWorkOrderOverdue(wo: BackendWorkOrder): boolean {
  if (!wo.due_at) return false;
  if (wo.status === "COMPLETED" || wo.status === "CLOSED" || wo.status === "CANCELLED") return false;
  return new Date(wo.due_at) < new Date();
}

function RealWorkOrdersList() {
  const searchParams = useSearchParams();
  const assetId = searchParams.get("asset_id");
  const aircraftId = searchParams.get("aircraft_id");

  const { apiBaseUrl } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();

  const [rows, setRows] = useState<BackendWorkOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  // Filters & Search
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [priorityFilter, setPriorityFilter] = useState<string>("ALL");
  const [typeFilter, setTypeFilter] = useState<string>("ALL");
  const [overdueOnly, setOverdueOnly] = useState(false);

  // Pagination
  const [page, setPage] = useState(0);
  const pageSize = 15;

  // Create Modal
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [newWoNumber, setNewWoNumber] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newPriority, setNewPriority] = useState("MEDIUM");
  const [newType, setNewType] = useState("CORRECTIVE");
  const [newCategory, setNewCategory] = useState("AIRFRAME");
  const [newAssetId, setNewAssetId] = useState(assetId ?? "");
  const [newAircraftId, setNewAircraftId] = useState(aircraftId ?? "");
  const [newDueAt, setNewDueAt] = useState("");
  const [newEstHours, setNewEstHours] = useState("");
  const [newLocation, setNewLocation] = useState("");

  const fetchWorkOrders = useCallback(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);

    workOrdersApi
      .list(accessToken, {
        asset_id: assetId ?? undefined,
        aircraft_id: aircraftId ?? undefined,
        status: statusFilter !== "ALL" ? statusFilter : undefined,
        priority: priorityFilter !== "ALL" ? priorityFilter : undefined,
        work_order_type: typeFilter !== "ALL" ? typeFilter : undefined,
        search: search.trim() ? search.trim() : undefined,
        overdue_only: overdueOnly ? true : undefined,
        limit: 100, // Fetch up to 100 for responsive client pagination/sorting
      })
      .then((data) => {
        setRows(data);
      })
      .catch((err) => {
        setError(normalizeApiError(err));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [
    accessToken,
    isAuthenticated,
    assetId,
    aircraftId,
    statusFilter,
    priorityFilter,
    typeFilter,
    search,
    overdueOnly,
  ]);

  useEffect(() => {
    fetchWorkOrders();
  }, [fetchWorkOrders]);

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!accessToken) return;
    if (!newWoNumber.trim()) {
      setCreateError("Work Order Number is required.");
      return;
    }

    setCreateSubmitting(true);
    setCreateError(null);

    const payload: WorkOrderCreatePayload = {
      work_order_number: newWoNumber.trim(),
      title: newTitle.trim() || undefined,
      description: newDescription.trim() || undefined,
      priority: newPriority,
      work_order_type: newType,
      maintenance_category: newCategory,
      asset_id: newAssetId.trim() || undefined,
      aircraft_id: newAircraftId.trim() || undefined,
      due_at: newDueAt ? new Date(newDueAt).toISOString() : undefined,
      estimated_hours: newEstHours ? parseFloat(newEstHours) : undefined,
      location: newLocation.trim() || undefined,
    };

    try {
      await workOrdersApi.create(accessToken, payload);
      setShowCreateModal(false);
      // Reset form
      setNewWoNumber("");
      setNewTitle("");
      setNewDescription("");
      setNewDueAt("");
      setNewEstHours("");
      setNewLocation("");
      fetchWorkOrders();
    } catch (err) {
      setCreateError(normalizeApiError(err).message);
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Client-side pagination slice
  const paginatedRows = useMemo(() => {
    const start = page * pageSize;
    return rows.slice(start, start + pageSize);
  }, [rows, page, pageSize]);

  const totalPages = Math.ceil(rows.length / pageSize);

  const columns: Column<BackendWorkOrder>[] = [
    {
      key: "num",
      header: "WO#",
      render: (w) => (
        <Link href={`/maintenance/work-orders/${w.id}`} className="ac-mono" style={{ fontWeight: 600 }}>
          {w.work_order_number}
        </Link>
      ),
      sortValue: (w) => w.work_order_number,
    },
    {
      key: "title",
      header: "Title & Type",
      render: (w) => (
        <div>
          <div style={{ fontWeight: 500 }}>{w.title || "Untitled Work Order"}</div>
          {w.work_order_type && (
            <span className="ac-text-muted ac-text-sm" style={{ fontSize: 11 }}>
              {w.work_order_type.replace(/_/g, " ")}
            </span>
          )}
        </div>
      ),
      sortValue: (w) => w.title ?? "",
    },
    {
      key: "aircraft",
      header: "Asset / Aircraft",
      render: (w) => <span className="ac-mono ac-text-sm">{w.asset_id || w.aircraft_id || "—"}</span>,
    },
    {
      key: "priority",
      header: "Priority",
      render: (w) => <StatusBadge {...priorityBadge(w.priority)} />,
      sortValue: (w) => w.priority,
    },
    {
      key: "status",
      header: "Status",
      render: (w) => <StatusBadge {...workOrderStatusBadge(w.status)} />,
      sortValue: (w) => w.status,
    },
    {
      key: "due",
      header: "Due Date",
      render: (w) => {
        const overdue = isWorkOrderOverdue(w);
        return (
          <div className="ac-flex ac-items-center ac-gap-2">
            <span className="ac-mono ac-text-sm">
              {w.due_at ? new Date(w.due_at).toLocaleDateString() : "—"}
            </span>
            {overdue && <StatusBadge {...overdueBadge()} />}
          </div>
        );
      },
      sortValue: (w) => w.due_at ?? "",
    },
    {
      key: "created",
      header: "Created",
      render: (w) => new Date(w.created_at).toLocaleDateString(),
      sortValue: (w) => w.created_at,
    },
  ];

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Maintenance", href: "/maintenance/projects" },
          { label: "Work Orders" },
        ]}
      />
      <div className="ac-section-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 className="ac-h1">Work Orders</h1>
          <p className="ac-subtitle">REAL data mode — connected to {apiBaseUrl}</p>
        </div>
        {isAuthenticated && (
          <button
            className="ac-btn ac-btn-primary"
            onClick={() => setShowCreateModal(true)}
            id="create-work-order-btn"
          >
            + Create Work Order
          </button>
        )}
      </div>

      {(assetId || aircraftId) && (
        <div
          className="ac-card ac-flex ac-gap-3"
          style={{
            padding: "var(--ac-space-3)",
            marginBottom: "var(--ac-space-4)",
            alignItems: "center",
            justifyContent: "space-between",
            background: "rgba(59, 130, 246, 0.08)",
            borderColor: "rgba(59, 130, 246, 0.3)",
          }}
        >
          <div className="ac-flex ac-gap-2" style={{ alignItems: "center" }}>
            <span className="ac-badge ac-badge--info">Filtered by {assetId ? "Drone / Asset" : "Aircraft"}</span>
            <span className="ac-mono ac-text-sm">{assetId || aircraftId}</span>
          </div>
          <Link href="/maintenance/work-orders" className="ac-btn ac-btn--sm">
            Clear Filter
          </Link>
        </div>
      )}

      {/* Search & Filter Controls */}
      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)", marginBottom: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap", marginBottom: 12 }}>
          <input
            className="ac-input"
            style={{ width: 260 }}
            placeholder="Search WO#, title, aircraft, location…"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            aria-label="Search work orders"
          />
          <select
            className="ac-input"
            style={{ width: 160 }}
            value={priorityFilter}
            onChange={(e) => {
              setPriorityFilter(e.target.value);
              setPage(0);
            }}
            aria-label="Filter by priority"
          >
            <option value="ALL">All Priorities</option>
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <select
            className="ac-input"
            style={{ width: 200 }}
            value={typeFilter}
            onChange={(e) => {
              setTypeFilter(e.target.value);
              setPage(0);
            }}
            aria-label="Filter by type"
          >
            <option value="ALL">All Types</option>
            {WORK_ORDER_TYPES.filter((t) => t !== "ALL").map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <label className="ac-flex ac-items-center ac-gap-2" style={{ cursor: "pointer", fontSize: 13, userSelect: "none" }}>
            <input
              type="checkbox"
              checked={overdueOnly}
              onChange={(e) => {
                setOverdueOnly(e.target.checked);
                setPage(0);
              }}
            />
            <span>Overdue Only</span>
          </label>
        </div>

        {/* Status Tabs */}
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
          {STATUSES.map((s) => (
            <button
              key={s}
              className="ac-btn ac-btn--sm"
              style={
                statusFilter === s
                  ? { borderColor: "var(--ac-accent)", color: "var(--ac-accent-hover)", fontWeight: 600 }
                  : undefined
              }
              onClick={() => {
                setStatusFilter(s);
                setPage(0);
              }}
            >
              {s.replace(/_/g, " ")}
            </button>
          ))}
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
          emptyMessage={
            assetId
              ? `No work orders found for asset ${assetId}.`
              : "No work orders matching your filters. Create one using the button above to get started."
          }
        >
          <div className="ac-card" style={{ padding: 0 }}>
            <DataTable columns={columns} rows={paginatedRows} getRowHref={(w) => `/maintenance/work-orders/${w.id}`} />
            {rows.length > pageSize && (
              <div
                className="ac-flex ac-justify-between ac-items-center"
                style={{ padding: "12px 16px", borderTop: "1px solid var(--ac-border-subtle)", fontSize: 13 }}
              >
                <span className="ac-text-muted">
                  Showing {page * pageSize + 1} - {Math.min((page + 1) * pageSize, rows.length)} of {rows.length} work orders
                </span>
                <div className="ac-flex ac-gap-2">
                  <button
                    className="ac-btn ac-btn--sm"
                    disabled={page === 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                  >
                    Previous
                  </button>
                  <button
                    className="ac-btn ac-btn--sm"
                    disabled={page >= totalPages - 1}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </RealDataPanel>
      )}

      {/* Create Work Order Modal */}
      {showCreateModal && (
        <div
          className="ac-modal-backdrop"
          onMouseDown={(e) => e.target === e.currentTarget && setShowCreateModal(false)}
        >
          <div
            className="ac-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-wo-title"
            style={{ maxWidth: 560, width: "100%" }}
          >
            <h2 id="create-wo-title" className="ac-modal-title">
              Create Work Order
            </h2>
            <form onSubmit={handleCreateSubmit}>
              <div className="ac-modal-body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {createError && (
                  <div
                    className="ac-card"
                    style={{
                      borderColor: "var(--ac-status-noncompliant)",
                      color: "var(--ac-status-noncompliant)",
                      padding: 10,
                      fontSize: 13,
                    }}
                  >
                    {createError}
                  </div>
                )}
                <div>
                  <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                    Work Order Number *
                  </label>
                  <input
                    className="ac-input"
                    style={{ width: "100%" }}
                    placeholder="e.g. WO-2026-0042"
                    value={newWoNumber}
                    onChange={(e) => setNewWoNumber(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                    Title
                  </label>
                  <input
                    className="ac-input"
                    style={{ width: "100%" }}
                    placeholder="Brief summary of work"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                  />
                </div>
                <div>
                  <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                    Description
                  </label>
                  <textarea
                    className="ac-input"
                    style={{ width: "100%", minHeight: 60 }}
                    placeholder="Detailed scope of maintenance activities..."
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                  />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                      Priority
                    </label>
                    <select
                      className="ac-input"
                      style={{ width: "100%" }}
                      value={newPriority}
                      onChange={(e) => setNewPriority(e.target.value)}
                    >
                      {PRIORITIES.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                      Work Order Type
                    </label>
                    <select
                      className="ac-input"
                      style={{ width: "100%" }}
                      value={newType}
                      onChange={(e) => setNewType(e.target.value)}
                    >
                      {WORK_ORDER_TYPES.filter((t) => t !== "ALL").map((t) => (
                        <option key={t} value={t}>
                          {t.replace(/_/g, " ")}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                      Asset ID (Drone)
                    </label>
                    <input
                      className="ac-input"
                      style={{ width: "100%" }}
                      placeholder="UUID or leave blank"
                      value={newAssetId}
                      onChange={(e) => setNewAssetId(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                      Aircraft ID
                    </label>
                    <input
                      className="ac-input"
                      style={{ width: "100%" }}
                      placeholder="UUID or leave blank"
                      value={newAircraftId}
                      onChange={(e) => setNewAircraftId(e.target.value)}
                    />
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                      Due Date & Time
                    </label>
                    <input
                      type="datetime-local"
                      className="ac-input"
                      style={{ width: "100%" }}
                      value={newDueAt}
                      onChange={(e) => setNewDueAt(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                      Estimated Hours
                    </label>
                    <input
                      type="number"
                      step="0.5"
                      min="0"
                      className="ac-input"
                      style={{ width: "100%" }}
                      placeholder="e.g. 4.5"
                      value={newEstHours}
                      onChange={(e) => setNewEstHours(e.target.value)}
                    />
                  </div>
                </div>
                <div>
                  <label className="ac-label" style={{ display: "block", marginBottom: 4 }}>
                    Facility / Location
                  </label>
                  <input
                    className="ac-input"
                    style={{ width: "100%" }}
                    placeholder="e.g. Hangar 3, Bay B"
                    value={newLocation}
                    onChange={(e) => setNewLocation(e.target.value)}
                  />
                </div>
              </div>
              <div className="ac-modal-actions" style={{ marginTop: 16 }}>
                <button
                  type="button"
                  className="ac-btn"
                  onClick={() => setShowCreateModal(false)}
                  disabled={createSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="ac-btn ac-btn-primary"
                  disabled={createSubmitting}
                >
                  {createSubmitting ? "Creating…" : "Create Work Order"}
                </button>
              </div>
            </form>
          </div>
        </div>
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
