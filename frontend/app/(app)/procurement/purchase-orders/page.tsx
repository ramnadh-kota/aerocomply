"use client";

import { Fragment, useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { purchaseOrders } from "@/lib/mock/procurement";
import { procurementRepository } from "@/lib/domain/repositories";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { purchaseOrdersApi, type BackendPurchaseOrder } from "@/lib/api/purchaseOrders";
import { procurementRequestsApi, type BackendProcurementRequest } from "@/lib/api/procurementRequests";
import { vendorsApi, type BackendVendor } from "@/lib/api/vendors";
import { ApiError, normalizeApiError } from "@/lib/apiClient";

// M11.8 — Purchase Order list. The demo/mock dataset below has no direct
// "New PO" button (Rule 4 — technicians cannot issue POs), and that stays
// true. The backend-authoritative panels DO include real PO creation: an
// "Approved Procurement Requests" panel lists real APPROVED requests and
// lets an authorized user turn one into a real Purchase Order via the
// existing backend create endpoint (backend/app/api/v1/purchase_orders.py)
// — no parallel creation logic, no client-side fabrication. The backend
// itself enforces duplicate-PO safety: create_purchase_order requires the
// linked request to still be APPROVED and flips it to ORDERED, so a second
// creation attempt against the same request is rejected with a 409.

function poStatusBadge(status: string): { status: Parameters<typeof StatusBadge>[0]["status"]; label: string } {
  switch (status) {
    case "RECEIVED": return { status: "COMPLIANT", label: "Received" };
    case "PARTIALLY_RECEIVED": return { status: "REVIEW_REQUIRED", label: "Partially Received" };
    case "CANCELLED": return { status: "NON_COMPLIANT", label: "Cancelled" };
    case "SENT": case "ACKNOWLEDGED": return { status: "PENDING", label: status.replace(/_/g, " ") };
    default: return { status: "INSUFFICIENT_DATA", label: status.replace(/_/g, " ") };
  }
}

function money(cents: number, currency: string): string {
  return `${currency} ${(cents / 100).toLocaleString()}`;
}

// Valid next transitions per the backend's own state machine
// (backend/app/services/purchase_order_service.py _ALLOWED_TRANSITIONS) —
// the frontend must never offer a button for a transition the backend
// doesn't actually allow from the current status.
const NEXT_ACTIONS: Record<string, { key: "submit" | "approve" | "send" | "cancel"; label: string }[]> = {
  DRAFT: [
    { key: "submit", label: "Submit for Approval" },
    { key: "cancel", label: "Cancel" },
  ],
  PENDING_APPROVAL: [
    { key: "approve", label: "Approve" },
    { key: "cancel", label: "Cancel" },
  ],
  APPROVED: [
    { key: "send", label: "Send to Vendor" },
    { key: "cancel", label: "Cancel" },
  ],
  SENT: [{ key: "cancel", label: "Cancel" }],
};

const RECEIVABLE_STATUSES = new Set(["SENT", "ACKNOWLEDGED", "PARTIALLY_RECEIVED"]);

export default function PurchaseOrdersPage() {
  const { mode: dataMode } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  const isRealModeSession = dataMode === "REAL" && isAuthenticated && !!accessToken;

  const [backendPOs, setBackendPOs] = useState<BackendPurchaseOrder[] | null>(null);
  const [backendStatus, setBackendStatus] = useState<"idle" | "loading" | "loaded" | "unavailable">("idle");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [receiveQuantities, setReceiveQuantities] = useState<Record<string, number>>({});
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{ poId: string; text: string; isError: boolean } | null>(null);

  const [approvedRequests, setApprovedRequests] = useState<BackendProcurementRequest[] | null>(null);
  const [requestsStatus, setRequestsStatus] = useState<"idle" | "loading" | "loaded" | "unavailable">("idle");
  const [backendVendors, setBackendVendors] = useState<BackendVendor[] | null>(null);
  const [createExpandedId, setCreateExpandedId] = useState<string | null>(null);
  const [createForm, setCreateForm] = useState<{
    poNumber: string;
    vendorId: string;
    quantity: number;
    unitPriceDollars: string;
    notes: string;
  } | null>(null);
  const [createBusy, setCreateBusy] = useState(false);
  const [createMessage, setCreateMessage] = useState<{ requestId: string; text: string; isError: boolean } | null>(null);

  function refetchPurchaseOrders(token: string) {
    setBackendStatus("loading");
    return purchaseOrdersApi
      .list(token)
      .then((result) => {
        setBackendPOs(result);
        setBackendStatus("loaded");
      })
      .catch(() => {
        setBackendPOs(null);
        setBackendStatus("unavailable");
      });
  }

  function refetchApprovedRequests(token: string) {
    setRequestsStatus("loading");
    return procurementRequestsApi
      .list(token, "APPROVED")
      .then((result) => {
        setApprovedRequests(result);
        setRequestsStatus("loaded");
      })
      .catch(() => {
        setApprovedRequests(null);
        setRequestsStatus("unavailable");
      });
  }

  useEffect(() => {
    if (!isRealModeSession || !accessToken) {
      setBackendPOs(null);
      setBackendStatus("idle");
      setApprovedRequests(null);
      setRequestsStatus("idle");
      setBackendVendors(null);
      return;
    }
    refetchPurchaseOrders(accessToken);
    refetchApprovedRequests(accessToken);
    vendorsApi
      .list(accessToken)
      .then(setBackendVendors)
      .catch(() => setBackendVendors(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isRealModeSession, accessToken]);

  function startCreatePo(request: BackendProcurementRequest) {
    setCreateExpandedId(request.id);
    setCreateMessage(null);
    setCreateForm({
      poNumber: `PO-${request.id.slice(0, 8).toUpperCase()}`,
      vendorId: request.selected_vendor_id ?? request.preferred_vendor_id ?? "",
      quantity: request.quantity,
      unitPriceDollars: "",
      notes: "",
    });
  }

  async function submitCreatePo(request: BackendProcurementRequest) {
    if (!accessToken || !createForm) return;
    if (!createForm.vendorId) {
      setCreateMessage({ requestId: request.id, text: "Select a vendor before creating the purchase order.", isError: true });
      return;
    }
    if (createForm.quantity <= 0) {
      setCreateMessage({ requestId: request.id, text: "Quantity must be greater than zero.", isError: true });
      return;
    }
    const unitPriceCents = createForm.unitPriceDollars.trim()
      ? Math.round(Number(createForm.unitPriceDollars) * 100)
      : null;
    if (createForm.unitPriceDollars.trim() && (!Number.isFinite(unitPriceCents) || (unitPriceCents ?? -1) < 0)) {
      setCreateMessage({ requestId: request.id, text: "Unit price must be a valid non-negative amount.", isError: true });
      return;
    }
    setCreateBusy(true);
    setCreateMessage(null);
    try {
      await purchaseOrdersApi.create(accessToken, {
        po_number: createForm.poNumber,
        vendor_id: createForm.vendorId,
        aircraft_id: request.aircraft_id,
        currency: "USD",
        notes: createForm.notes.trim() || null,
        lines: [
          {
            procurement_request_id: request.id,
            part_number: request.part_number,
            description: request.description,
            quantity: createForm.quantity,
            unit_price_cents: unitPriceCents,
          },
        ],
      });
      setCreateMessage({ requestId: request.id, text: "Purchase order created.", isError: false });
      setCreateExpandedId(null);
      setCreateForm(null);
      await Promise.all([refetchApprovedRequests(accessToken), refetchPurchaseOrders(accessToken)]);
    } catch (err) {
      setCreateMessage({ requestId: request.id, text: describeError(err), isError: true });
    } finally {
      setCreateBusy(false);
    }
  }

  async function runTransition(poId: string, action: "submit" | "approve" | "send" | "cancel") {
    if (!accessToken) return;
    setBusyAction(`${poId}:${action}`);
    setActionMessage(null);
    try {
      if (action === "submit") await purchaseOrdersApi.submitForApproval(accessToken, poId);
      else if (action === "approve") await purchaseOrdersApi.approve(accessToken, poId);
      else if (action === "send") await purchaseOrdersApi.send(accessToken, poId);
      else if (action === "cancel") await purchaseOrdersApi.cancel(accessToken, poId);
      setActionMessage({ poId, text: "Updated.", isError: false });
      await refetchPurchaseOrders(accessToken);
    } catch (err) {
      setActionMessage({ poId, text: describeError(err), isError: true });
    } finally {
      setBusyAction(null);
    }
  }

  async function runReceive(po: BackendPurchaseOrder) {
    if (!accessToken) return;
    const lines = po.lines
      .map((line) => ({ line_id: line.id, quantity: receiveQuantities[line.id] ?? 0 }))
      .filter((l) => l.quantity > 0);
    if (lines.length === 0) {
      setActionMessage({ poId: po.id, text: "Enter a received quantity for at least one line.", isError: true });
      return;
    }
    setBusyAction(`${po.id}:receive`);
    setActionMessage(null);
    try {
      await purchaseOrdersApi.receive(accessToken, po.id, lines);
      setActionMessage({ poId: po.id, text: "Receipt recorded — inventory updated.", isError: false });
      setReceiveQuantities({});
      await refetchPurchaseOrders(accessToken);
    } catch (err) {
      setActionMessage({ poId: po.id, text: describeError(err), isError: true });
    } finally {
      setBusyAction(null);
    }
  }

  function describeError(err: unknown): string {
    if (err instanceof ApiError && err.status === 403) return "PERMISSION_DENIED — your role cannot perform this action.";
    if (err instanceof ApiError && err.status === 409) return `CONFLICT — ${err.message}`;
    return normalizeApiError(err).message;
  }

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Procurement", href: "/procurement" }, { label: "Purchase Orders" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Purchase Orders</h1>
          <p className="ac-subtitle">Generated only from approved procurement requests. {purchaseOrders.length} PO(s) exist this session.</p>
        </div>
      </div>

      {isRealModeSession && (
        <div className="ac-card" style={{ marginBottom: 16, padding: 0 }}>
          <div style={{ padding: 12 }}>
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>
              Approved Procurement Requests
              {requestsStatus === "loaded" && " · Live Postgres Data"}
            </p>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 8px" }}>
              Approved requests awaiting a purchase order. Creating one calls the real backend and
              converts the request to ORDERED — a second attempt against the same request is
              rejected by the backend.
            </p>
            {requestsStatus === "unavailable" && (
              <p className="ac-text-sm" style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid var(--ac-status-review)", background: "color-mix(in srgb, var(--ac-status-review) 10%, transparent)" }}>
                BACKEND_UNAVAILABLE — real procurement requests could not be retrieved.
              </p>
            )}
            {requestsStatus === "loaded" && approvedRequests && approvedRequests.length === 0 && (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No approved procurement requests are awaiting a purchase order.</p>
            )}
          </div>
          {requestsStatus === "loaded" && approvedRequests && approvedRequests.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table className="ac-table" style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th>Request</th>
                    <th>Part</th>
                    <th>Qty</th>
                    <th>Priority</th>
                    <th>Vendor</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {approvedRequests.map((request) => {
                    const vendor = backendVendors?.find(
                      (v) => v.id === (request.selected_vendor_id ?? request.preferred_vendor_id)
                    );
                    return (
                      <Fragment key={request.id}>
                        <tr>
                          <td className="ac-mono" style={{ fontSize: 11 }}>{request.id.slice(0, 8)}…</td>
                          <td className="ac-mono">{request.part_number}</td>
                          <td>{request.quantity}</td>
                          <td>{request.priority}</td>
                          <td>{vendor ? vendor.name : "Not selected"}</td>
                          <td>
                            <button
                              className="ac-btn"
                              style={{ fontSize: 12, padding: "2px 8px" }}
                              onClick={() => {
                                if (createExpandedId === request.id) {
                                  setCreateExpandedId(null);
                                  setCreateForm(null);
                                } else {
                                  startCreatePo(request);
                                }
                              }}
                            >
                              {createExpandedId === request.id ? "Close" : "Create Purchase Order"}
                            </button>
                          </td>
                        </tr>
                        {createExpandedId === request.id && createForm && (
                          <tr>
                            <td colSpan={6} style={{ padding: "8px 12px" }}>
                              <div className="ac-flex ac-items-center ac-gap-2" style={{ flexWrap: "wrap", marginBottom: 8 }}>
                                <label className="ac-text-sm">
                                  PO Number
                                  <input
                                    className="ac-input"
                                    style={{ display: "block", width: 160 }}
                                    value={createForm.poNumber}
                                    onChange={(e) => setCreateForm({ ...createForm, poNumber: e.target.value })}
                                  />
                                </label>
                                <label className="ac-text-sm">
                                  Vendor
                                  <select
                                    className="ac-input"
                                    style={{ display: "block", width: 200 }}
                                    value={createForm.vendorId}
                                    onChange={(e) => setCreateForm({ ...createForm, vendorId: e.target.value })}
                                  >
                                    <option value="">Select a vendor…</option>
                                    {(backendVendors ?? []).map((v) => (
                                      <option key={v.id} value={v.id}>
                                        {v.name}{v.approved ? "" : " (unapproved)"}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                                <label className="ac-text-sm">
                                  Quantity
                                  <input
                                    className="ac-input"
                                    style={{ display: "block", width: 80 }}
                                    type="number"
                                    min={1}
                                    value={createForm.quantity}
                                    onChange={(e) => setCreateForm({ ...createForm, quantity: Number(e.target.value) })}
                                  />
                                </label>
                                <label className="ac-text-sm">
                                  Unit Price (USD)
                                  <input
                                    className="ac-input"
                                    style={{ display: "block", width: 100 }}
                                    type="number"
                                    min={0}
                                    step="0.01"
                                    placeholder="Optional"
                                    value={createForm.unitPriceDollars}
                                    onChange={(e) => setCreateForm({ ...createForm, unitPriceDollars: e.target.value })}
                                  />
                                </label>
                                <label className="ac-text-sm" style={{ flex: 1, minWidth: 160 }}>
                                  Notes
                                  <input
                                    className="ac-input"
                                    style={{ display: "block", width: "100%" }}
                                    placeholder="Optional"
                                    value={createForm.notes}
                                    onChange={(e) => setCreateForm({ ...createForm, notes: e.target.value })}
                                  />
                                </label>
                              </div>
                              <div className="ac-flex ac-items-center ac-gap-2">
                                <button
                                  className="ac-btn ac-btn-primary"
                                  disabled={createBusy}
                                  onClick={() => submitCreatePo(request)}
                                >
                                  {createBusy ? "Creating…" : "Submit"}
                                </button>
                                {createMessage && createMessage.requestId === request.id && (
                                  <span className="ac-text-sm" style={{ color: createMessage.isError ? "var(--ac-status-review)" : "var(--ac-status-compliant)" }}>
                                    {createMessage.text}
                                  </span>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {isRealModeSession && (
        <div className="ac-card" style={{ marginBottom: 16, padding: 0 }}>
          <div style={{ padding: 12 }}>
            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>
              Backend Purchase Orders
              {backendStatus === "loaded" && " · Live Postgres Data"}
            </p>
            {backendStatus === "unavailable" && (
              <p className="ac-text-sm" style={{ padding: "8px 10px", borderRadius: 6, border: "1px solid var(--ac-status-review)", background: "color-mix(in srgb, var(--ac-status-review) 10%, transparent)" }}>
                BACKEND_UNAVAILABLE — real purchase orders could not be retrieved. The table below is the existing demo dataset, not a fallback for this panel.
              </p>
            )}
            {backendStatus === "loaded" && backendPOs && backendPOs.length === 0 && (
              <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No purchase orders recorded in the backend for this organization yet.</p>
            )}
          </div>
          {backendStatus === "loaded" && backendPOs && backendPOs.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table className="ac-table" style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th>PO Number</th>
                    <th>Vendor ID</th>
                    <th>Total</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {backendPOs.map((po) => (
                    <Fragment key={po.id}>
                      <tr>
                        <td className="ac-mono">{po.po_number}</td>
                        <td className="ac-mono" style={{ fontSize: 11 }}>{po.vendor_id.slice(0, 8)}…</td>
                        <td>{money(po.total_cents, po.currency)}</td>
                        <td><StatusBadge {...poStatusBadge(po.status)} /></td>
                        <td>
                          <button className="ac-btn" style={{ fontSize: 12, padding: "2px 8px" }} onClick={() => setExpandedId(expandedId === po.id ? null : po.id)}>
                            {expandedId === po.id ? "Close" : "Details / Actions"}
                          </button>
                        </td>
                      </tr>
                      {expandedId === po.id && (
                        <tr>
                          <td colSpan={5} style={{ padding: "8px 12px" }}>
                            <div style={{ marginBottom: 8 }}>
                              <p className="ac-text-sm ac-text-muted" style={{ margin: "0 0 6px" }}>Lines</p>
                              {po.lines.map((line) => (
                                <div key={line.id} className="ac-flex ac-items-center ac-gap-2" style={{ marginBottom: 4, flexWrap: "wrap" }}>
                                  <span className="ac-mono ac-text-sm">{line.part_number}</span>
                                  <span className="ac-text-sm ac-text-muted">{line.description}</span>
                                  <span className="ac-text-sm">Ordered {line.quantity} · Received {line.received_quantity}</span>
                                  {RECEIVABLE_STATUSES.has(po.status) && line.received_quantity < line.quantity && (
                                    <input
                                      className="ac-input"
                                      style={{ width: 70 }}
                                      type="number"
                                      min={0}
                                      max={line.quantity - line.received_quantity}
                                      placeholder="Qty"
                                      value={receiveQuantities[line.id] ?? ""}
                                      onChange={(e) =>
                                        setReceiveQuantities((prev) => ({ ...prev, [line.id]: Number(e.target.value) }))
                                      }
                                    />
                                  )}
                                </div>
                              ))}
                            </div>
                            <div className="ac-flex ac-items-center ac-gap-2" style={{ flexWrap: "wrap" }}>
                              {(NEXT_ACTIONS[po.status] ?? []).map((action) => (
                                <button
                                  key={action.key}
                                  className="ac-btn"
                                  disabled={busyAction === `${po.id}:${action.key}`}
                                  onClick={() => runTransition(po.id, action.key)}
                                >
                                  {action.label}
                                </button>
                              ))}
                              {RECEIVABLE_STATUSES.has(po.status) && (
                                <button
                                  className="ac-btn ac-btn-primary"
                                  disabled={busyAction === `${po.id}:receive`}
                                  onClick={() => runReceive(po)}
                                >
                                  Receive
                                </button>
                              )}
                              {actionMessage && actionMessage.poId === po.id && (
                                <span className="ac-text-sm" style={{ color: actionMessage.isError ? "var(--ac-status-review)" : "var(--ac-status-compliant)" }}>
                                  {actionMessage.text}
                                </span>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <p className="ac-eyebrow" style={{ marginBottom: 8 }}>{isRealModeSession ? "Demo Dataset View (below)" : "Purchase Orders"}</p>
      <div className="ac-card" style={{ padding: 0 }}>
        {purchaseOrders.length === 0 ? (
          <p className="ac-text-sm ac-text-muted" style={{ padding: 12 }}>Insufficient source data. No purchase order has been generated yet — approve a procurement request first.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="ac-table">
              <thead><tr><th>PO Number</th><th>Vendor</th><th>Total</th><th>Required By</th><th>Status</th></tr></thead>
              <tbody>
                {purchaseOrders.map((po) => {
                  const vendor = procurementRepository.getVendorById(po.vendorId);
                  return (
                    <tr key={po.id}>
                      <td><Link href={`/procurement/purchase-orders/${po.id}`} className="ac-mono">{po.poNumber}</Link></td>
                      <td>{vendor?.name ?? "Insufficient source data."}</td>
                      <td>{po.currency} {po.total.toLocaleString()}</td>
                      <td>{po.requiredBy ?? "Insufficient source data."}</td>
                      <td><StatusBadge {...poStatusBadge(po.status)} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
