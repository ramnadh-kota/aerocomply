"use client";

// Platform Admin — Soft-Delete Governance Queue.
// REAL-mode only. Consumes GET/POST /platform/deleted-records/...
// (backend/app/api/v1/platform.py) -- the tenant-facing half is a plain
// DELETE /assets/{id} (soft delete only, see
// backend/app/services/deletion_service.py); this page is where Platform
// Admin sees what tenants have deleted and either restores it or, as a
// separate and more privileged step, permanently deletes it.
//
// Backend enforces PLATFORM_MANAGE to list, DATA_RESTORE to restore, and
// the narrower DATA_PERMANENT_DELETE (PLATFORM_ADMIN only) to permanently
// delete -- this page hiding a button is a UX convenience only; a 403 here
// renders as a normal API error, never a silent no-op.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { deletionApi, type DeletedRecordResponse } from "@/lib/api/deletion";
import { platformApi, type BackendPlatformOrganization } from "@/lib/api/platform";

const PAGE_SIZE = 50;

function PermanentDeleteDialog({
  record,
  onClose,
  onConfirm,
  submitting,
  error,
}: {
  record: DeletedRecordResponse | null;
  onClose: () => void;
  onConfirm: (reason: string) => void;
  submitting: boolean;
  error: string | null;
}) {
  const [reason, setReason] = useState("");

  useEffect(() => {
    setReason("");
  }, [record]);

  if (!record) return null;

  return (
    <div className="ac-modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="ac-modal" role="dialog" aria-modal="true" aria-labelledby="perm-delete-title" style={{ maxWidth: 520, width: "100%" }}>
        <h2 id="perm-delete-title" className="ac-modal-title">Permanently Delete Record</h2>
        <div className="ac-modal-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            This is irreversible. <strong>{record.identifier ?? record.entity_id}</strong> ({record.entity_type}
            {record.entity_type === "ASSET" ? `, organization ${record.organization_id}` : ""}) will be permanently
            removed only if it has no dependent records —{" "}
            {record.entity_type === "ORGANIZATION"
              ? "any remaining users or assets block this by design"
              : record.entity_type === "WORKORDER"
              ? "any remaining tasks, part requirements, findings, or similar history block this by design"
              : "flights, components, work orders, and similar history block this by design"}
            .
          </p>
          <div>
            <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }} htmlFor="perm-delete-reason">
              Reason (required)
            </label>
            <textarea
              id="perm-delete-reason"
              className="ac-input"
              style={{ width: "100%", minHeight: 60 }}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this being permanently deleted?"
            />
          </div>
          {error && <p className="ac-text-sm" style={{ color: "var(--ac-danger, #ef4444)", margin: 0 }}>{error}</p>}
        </div>
        <div className="ac-modal-actions">
          <button className="ac-btn" onClick={onClose} disabled={submitting}>
            Cancel
          </button>
          <button
            className="ac-btn ac-btn-primary"
            style={{ background: "var(--ac-danger, #ef4444)" }}
            disabled={submitting || !reason.trim()}
            onClick={() => onConfirm(reason.trim())}
          >
            {submitting ? "Deleting…" : "Permanently Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}

function RealDeletedRecordsQueue() {
  const { accessToken, isAuthenticated } = useSession();
  const [items, setItems] = useState<DeletedRecordResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [orgs, setOrgs] = useState<BackendPlatformOrganization[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [entityType, setEntityType] = useState<"" | "ASSET" | "ORGANIZATION" | "WORKORDER">("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [restoringId, setRestoringId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<DeletedRecordResponse | null>(null);
  const [deleteSubmitting, setDeleteSubmitting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    platformApi.listOrganizations(accessToken).then(setOrgs).catch(() => setOrgs([]));
  }, [accessToken]);

  const refresh = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    deletionApi
      .listDeletedRecords(accessToken, {
        entity_type: entityType || undefined,
        organization_id: organizationId || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        setError(normalizeApiError(err));
        setItems([]);
        setTotal(0);
      })
      .finally(() => setLoading(false));
  };

  useEffect(refresh, [accessToken, isAuthenticated, entityType, organizationId, offset]);

  const orgName = (id: string) => orgs.find((o) => o.id === id)?.name ?? id;

  async function handleRestore(record: DeletedRecordResponse) {
    if (!accessToken) return;
    setActionError(null);
    setRestoringId(record.entity_id);
    try {
      if (record.entity_type === "ORGANIZATION") {
        await deletionApi.restoreOrganization(accessToken, record.entity_id);
      } else if (record.entity_type === "WORKORDER") {
        await deletionApi.restoreWorkOrder(accessToken, record.entity_id);
      } else {
        await deletionApi.restoreAsset(accessToken, record.entity_id);
      }
      refresh();
    } catch (err) {
      setActionError(normalizeApiError(err).message || "Failed to restore record.");
    } finally {
      setRestoringId(null);
    }
  }

  async function handlePermanentDelete(reason: string) {
    if (!accessToken || !deleteTarget) return;
    setDeleteSubmitting(true);
    setDeleteError(null);
    try {
      if (deleteTarget.entity_type === "ORGANIZATION") {
        await deletionApi.permanentlyDeleteOrganization(accessToken, deleteTarget.entity_id, reason);
      } else if (deleteTarget.entity_type === "WORKORDER") {
        await deletionApi.permanentlyDeleteWorkOrder(accessToken, deleteTarget.entity_id, reason);
      } else {
        await deletionApi.permanentlyDeleteAsset(accessToken, deleteTarget.entity_id, reason);
      }
      setDeleteTarget(null);
      refresh();
    } catch (err) {
      setDeleteError(normalizeApiError(err).message || "Failed to permanently delete record.");
    } finally {
      setDeleteSubmitting(false);
    }
  }

  const columns: Column<DeletedRecordResponse>[] = [
    {
      key: "organization",
      header: "Organization",
      render: (r) => (
        <Link href={`/platform/organizations/${r.organization_id}`} className="ac-text-sm">
          {orgName(r.organization_id)}
        </Link>
      ),
    },
    { key: "entity_type", header: "Entity Type", render: (r) => <span className="ac-text-sm">{r.entity_type}</span> },
    {
      key: "identifier",
      header: "Identifier",
      render: (r) => (
        <span className="ac-mono ac-text-sm">
          {r.identifier ?? r.entity_id} {r.asset_type ? `(${r.asset_type})` : ""}
        </span>
      ),
    },
    {
      key: "deleted_at",
      header: "Deleted At",
      render: (r) => <span className="ac-text-sm">{new Date(r.deleted_at).toLocaleString()}</span>,
      sortValue: (r) => r.deleted_at,
    },
    { key: "deleted_by", header: "Deleted By", render: (r) => <span className="ac-text-sm" style={{ wordBreak: "break-all" }}>{r.deleted_by ?? "—"}</span> },
    { key: "reason", header: "Reason", render: (r) => <span className="ac-text-sm">{r.deletion_reason ?? "—"}</span> },
    { key: "status", header: "Status", render: (r) => <StatusBadge status="NON_COMPLIANT" label={r.status} /> },
    {
      key: "actions",
      header: "Actions",
      render: (r) => (
        <div className="ac-flex ac-gap-2">
          <button
            className="ac-btn"
            style={{ fontSize: 12, padding: "2px 8px" }}
            disabled={restoringId === r.entity_id}
            onClick={() => handleRestore(r)}
          >
            {restoringId === r.entity_id ? "Restoring…" : "Restore"}
          </button>
          <button
            className="ac-btn"
            style={{ fontSize: 12, padding: "2px 8px", color: "var(--ac-danger, #ef4444)" }}
            onClick={() => {
              setDeleteError(null);
              setDeleteTarget(r);
            }}
          >
            Permanently Delete
          </button>
        </div>
      ),
    },
  ];

  if (!isAuthenticated) {
    return (
      <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
        <p className="ac-text-sm" style={{ margin: 0 }}>
          Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
        </p>
      </div>
    );
  }

  const forbidden = error?.kind === "forbidden";
  const rangeStart = total === 0 ? 0 : offset + 1;
  const rangeEnd = Math.min(offset + items.length, total);

  return (
    <div>
      <Breadcrumbs items={[{ label: "Platform Admin", href: "/platform/organizations" }, { label: "Deletion Requests" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Platform — Deletion Requests</h1>
          <p className="ac-subtitle">
            Assets (aircraft/drones/helicopters) a tenant has deleted, and organizations whose admin requested
            deletion of the whole tenant. Restore reverses either; permanent deletion is irreversible and blocked
            automatically while dependent records still exist (flights/components/work orders for an asset; any
            remaining users or assets for an organization).
          </p>
        </div>
      </div>

      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-3" style={{ flexWrap: "wrap" }}>
          <div>
            <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }} htmlFor="deleted-records-type-filter">
              Entity Type
            </label>
            <select
              id="deleted-records-type-filter"
              className="ac-select"
              style={{ minWidth: 180 }}
              value={entityType}
              onChange={(e) => {
                setEntityType(e.target.value as "" | "ASSET" | "ORGANIZATION" | "WORKORDER");
                setOffset(0);
              }}
            >
              <option value="">All types</option>
              <option value="ASSET">Asset (Aircraft/Drone/Helicopter)</option>
              <option value="ORGANIZATION">Organization</option>
              <option value="WORKORDER">Work Order</option>
            </select>
          </div>
          <div>
            <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }} htmlFor="deleted-records-org-filter">
              Organization
            </label>
            <select
              id="deleted-records-org-filter"
              className="ac-select"
              style={{ minWidth: 240 }}
              value={organizationId}
              onChange={(e) => {
                setOrganizationId(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All organizations</option>
              {orgs.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {actionError && (
        <div className="ac-card ac-section" style={{ padding: "var(--ac-space-3)", borderColor: "var(--ac-danger, #ef4444)" }}>
          <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-danger, #ef4444)" }}>{actionError}</p>
        </div>
      )}

      {forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to view the deletion-requests queue.
          </p>
        </div>
      ) : (
        <>
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!error && items.length === 0}
            emptyMessage="Nothing is currently soft-deleted."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <DataTable columns={columns} rows={items} caption="Soft-deleted records awaiting restore or permanent deletion" />
            </div>
          </RealDataPanel>

          {!loading && !error && total > 0 && (
            <div className="ac-flex ac-gap-2" style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", marginTop: "var(--ac-space-3)" }}>
              <span className="ac-text-sm ac-text-muted">
                Showing {rangeStart}–{rangeEnd} of {total}
              </span>
              <div className="ac-flex ac-gap-2">
                <button className="ac-btn" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0}>
                  ← Previous
                </button>
                <button className="ac-btn" onClick={() => setOffset(offset + PAGE_SIZE)} disabled={offset + PAGE_SIZE >= total}>
                  Next →
                </button>
              </div>
            </div>
          )}
        </>
      )}

      <PermanentDeleteDialog
        record={deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={handlePermanentDelete}
        submitting={deleteSubmitting}
        error={deleteError}
      />
    </div>
  );
}

export default function PlatformDeletedRecordsPage() {
  return <RealDeletedRecordsQueue />;
}
