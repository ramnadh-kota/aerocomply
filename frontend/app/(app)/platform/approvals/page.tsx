"use client";

// Platform Admin — Approvals & Governance (M14).
// REAL-mode only. Consumes GET/POST /api/v1/platform/approvals* (backend
// M14). This page never decides whether a change is "expansive" — that
// classification lives entirely on the backend (see
// app/services/tenant_entitlement_admin_service.py) — and it never claims a
// governance guarantee the backend does not actually provide.
//
// UI HONESTY: this page uses only neutral terms -- Requested, Pending
// review, Approved, Rejected, Canceled, Reviewed by. It never says
// "Approved by security team", "Two-person approval", or "Compliance
// approved" anywhere, because none of those exist. PLATFORM_ADMIN is
// currently the only platform role, so the same admin can both request and
// review a change -- when that happens this page shows both fields plainly
// (Requested by / Reviewed by) rather than hiding or dressing it up.
//
// Backend enforces PLATFORM_MANAGE on every route and additionally
// PLATFORM_ENTITLEMENT_OVERRIDE on approve -- this page hiding itself from
// non-platform-admin users (see Sidebar.tsx) is a UX convenience only,
// never the security boundary. A 403 renders a distinct "Permission
// Denied" state, never an empty list.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import type { BadgeKind } from "@/components/status/StatusBadge";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  approvalsApi,
  type ApprovalRequestResponse,
  type ApprovalStatus,
} from "@/lib/api/approvals";
import { platformApi, type BackendPlatformOrganization } from "@/lib/api/platform";

const PAGE_SIZE = 50;
const TABS: { value: ApprovalStatus; label: string }[] = [
  { value: "PENDING", label: "Pending review" },
  { value: "APPROVED", label: "Approved" },
  { value: "REJECTED", label: "Rejected" },
  { value: "CANCELED", label: "Canceled" },
];

function statusBadgeStatus(status: ApprovalStatus): BadgeKind {
  switch (status) {
    case "APPROVED":
      return "COMPLIANT";
    case "REJECTED":
    case "CANCELED":
      return "NON_COMPLIANT";
    default:
      return "PENDING";
  }
}

function describeChange(item: ApprovalRequestResponse): string {
  if (item.request_type === "feature_override_expansion") {
    return `Enable feature "${item.feature_key}"`;
  }
  if (item.requested_is_unlimited) {
    return `Set "${item.feature_key} / ${item.limit_key}" to unlimited`;
  }
  return `Raise "${item.feature_key} / ${item.limit_key}" limit to ${item.requested_limit_value ?? "?"}`;
}

function ReviewDialog({
  approval,
  orgName,
  onClose,
  onDecided,
}: {
  approval: ApprovalRequestResponse | null;
  orgName: string;
  onClose: () => void;
  onDecided: (updated: ApprovalRequestResponse) => void;
}) {
  const { accessToken } = useSession();
  const [decisionReason, setDecisionReason] = useState("");
  const [confirmAction, setConfirmAction] = useState<"approve" | "reject" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDecisionReason("");
    setConfirmAction(null);
    setError(null);
  }, [approval?.id]);

  if (!approval) return null;

  const runDecision = async (action: "approve" | "reject") => {
    if (!accessToken) return;
    setBusy(true);
    setError(null);
    try {
      const updated =
        action === "approve"
          ? await approvalsApi.approve(accessToken, approval.id, decisionReason || undefined)
          : await approvalsApi.reject(accessToken, approval.id, decisionReason || undefined);
      onDecided(updated);
      setConfirmAction(null);
    } catch (err) {
      setError(normalizeApiError(err).message);
    } finally {
      setBusy(false);
    }
  };

  const selfReviewPossible = Boolean(approval.requested_by_user_id);

  return (
    <div
      className="ac-modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="ac-modal"
        role="dialog"
        aria-modal="true"
        style={{ maxWidth: 560, width: "100%", maxHeight: "85vh", overflowY: "auto" }}
      >
        <h2 className="ac-modal-title">Review Approval Request</h2>
        <div className="ac-modal-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <span className="ac-text-sm ac-text-muted">Organization</span>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              <Link href={`/platform/organizations/${approval.organization_id}`}>{orgName}</Link>
            </p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Requested change</span>
            <p className="ac-text-sm" style={{ margin: 0 }}>{describeChange(approval)}</p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Reason given by requester</span>
            <p className="ac-text-sm" style={{ margin: 0 }}>{approval.reason || "—"}</p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Requested by</span>
            <p className="ac-text-sm" style={{ margin: 0, wordBreak: "break-all" }}>
              {approval.requested_by_user_id ?? "—"}
            </p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Status</span>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              <StatusBadge status={statusBadgeStatus(approval.status)} label={approval.status} />
            </p>
          </div>
          {approval.status !== "PENDING" && (
            <>
              <div>
                <span className="ac-text-sm ac-text-muted">Reviewed by</span>
                <p className="ac-text-sm" style={{ margin: 0, wordBreak: "break-all" }}>
                  {approval.reviewed_by_user_id ?? "—"}
                </p>
              </div>
              <div>
                <span className="ac-text-sm ac-text-muted">Decision reason</span>
                <p className="ac-text-sm" style={{ margin: 0 }}>{approval.decision_reason || "—"}</p>
              </div>
            </>
          )}

          {approval.status === "PENDING" && (
            <>
              {selfReviewPossible && (
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                  Note: platform administration currently has a single role, so the same admin may
                  both request and review a change. This is recorded plainly (requested by / reviewed
                  by) rather than presented as independent review.
                </p>
              )}
              <div>
                <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }} htmlFor="decision-reason">
                  Decision reason (optional)
                </label>
                <textarea
                  id="decision-reason"
                  className="ac-input"
                  style={{ width: "100%", minHeight: 60 }}
                  value={decisionReason}
                  onChange={(e) => setDecisionReason(e.target.value)}
                />
              </div>
              {error && (
                <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
                  {error}
                </p>
              )}
            </>
          )}
        </div>
        <div className="ac-modal-actions">
          <button className="ac-btn" onClick={onClose} disabled={busy}>
            Close
          </button>
          {approval.status === "PENDING" && (
            <>
              <button
                className="ac-btn"
                style={{ borderColor: "var(--ac-status-non-compliant)", color: "var(--ac-status-non-compliant)" }}
                onClick={() => setConfirmAction("reject")}
                disabled={busy}
              >
                Reject
              </button>
              <button className="ac-btn" onClick={() => setConfirmAction("approve")} disabled={busy}>
                Approve
              </button>
            </>
          )}
        </div>
      </div>

      <ConfirmDialog
        open={confirmAction !== null}
        title={confirmAction === "approve" ? "Approve this request?" : "Reject this request?"}
        body={
          confirmAction === "approve"
            ? `This will ${describeChange(approval).toLowerCase()} for this organization immediately.`
            : "This request will be marked rejected and no entitlement change will be made."
        }
        confirmLabel={confirmAction === "approve" ? "Approve" : "Reject"}
        busy={busy}
        onConfirm={() => confirmAction && runDecision(confirmAction)}
        onCancel={() => setConfirmAction(null)}
      />
    </div>
  );
}

function RealApprovalsFeed() {
  const { accessToken, isAuthenticated } = useSession();
  const [status, setStatus] = useState<ApprovalStatus>("PENDING");
  const [items, setItems] = useState<ApprovalRequestResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [orgs, setOrgs] = useState<BackendPlatformOrganization[]>([]);
  const [selected, setSelected] = useState<ApprovalRequestResponse | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    platformApi.listOrganizations(accessToken).then(setOrgs).catch(() => setOrgs([]));
  }, [accessToken]);

  const load = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    approvalsApi
      .listApprovals(accessToken, { status, limit: PAGE_SIZE, offset })
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

  useEffect(load, [accessToken, isAuthenticated, status, offset]);

  const orgName = (id: string) => orgs.find((o) => o.id === id)?.name ?? id;

  const columns: Column<ApprovalRequestResponse>[] = [
    {
      key: "requested",
      header: "Requested",
      render: (a) => <span className="ac-text-sm">{new Date(a.created_at).toLocaleString()}</span>,
      sortValue: (a) => a.created_at,
    },
    {
      key: "organization",
      header: "Organization",
      render: (a) => (
        <Link href={`/platform/organizations/${a.organization_id}`} className="ac-text-sm">
          {orgName(a.organization_id)}
        </Link>
      ),
    },
    {
      key: "change",
      header: "Requested change",
      render: (a) => <span className="ac-text-sm" style={{ wordBreak: "break-word" }}>{describeChange(a)}</span>,
    },
    {
      key: "requested_by",
      header: "Requested by",
      render: (a) => (
        <span className="ac-text-sm" style={{ wordBreak: "break-all" }}>{a.requested_by_user_id ?? "—"}</span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (a) => <StatusBadge status={statusBadgeStatus(a.status)} label={a.status} />,
    },
    {
      key: "actions",
      header: "Actions",
      render: (a) => (
        <button className="ac-btn" style={{ fontSize: 12, padding: "2px 8px" }} onClick={() => setSelected(a)}>
          {a.status === "PENDING" ? "Review" : "View"}
        </button>
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
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Approvals" },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Platform — Approvals</h1>
          <p className="ac-subtitle">
            Governance requests for entitlement changes that expand a tenant beyond its plan.
            Requesting and reviewing both use the same platform-administrator authority today — see
            the note in each request&apos;s detail view.
          </p>
        </div>
      </div>

      <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginBottom: "var(--ac-space-3)" }}>
        {TABS.map((tab) => (
          <button
            key={tab.value}
            className="ac-btn"
            style={
              status === tab.value
                ? { borderColor: "var(--ac-accent)", fontWeight: 600 }
                : undefined
            }
            onClick={() => {
              setStatus(tab.value);
              setOffset(0);
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to view platform governance requests.
          </p>
        </div>
      ) : (
        <>
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!error && items.length === 0}
            emptyMessage={`No ${TABS.find((t) => t.value === status)?.label.toLowerCase()} requests.`}
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <div className="ac-table-desktop">
                <DataTable columns={columns} rows={items} caption="Governance approval requests" />
              </div>
              <div className="ac-row-cards">
                {items.map((a) => (
                  <div className="ac-row-card" key={a.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Requested</span>
                      <span>{new Date(a.created_at).toLocaleString()}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Organization</span>
                      <Link href={`/platform/organizations/${a.organization_id}`}>{orgName(a.organization_id)}</Link>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Change</span>
                      <span style={{ wordBreak: "break-word" }}>{describeChange(a)}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Status</span>
                      <StatusBadge status={statusBadgeStatus(a.status)} label={a.status} />
                    </div>
                    <div className="ac-row-card-actions">
                      <button className="ac-btn" onClick={() => setSelected(a)}>
                        {a.status === "PENDING" ? "Review" : "View"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </RealDataPanel>

          {!loading && !error && total > 0 && (
            <div
              className="ac-flex ac-gap-2"
              style={{ justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", marginTop: "var(--ac-space-3)" }}
            >
              <span className="ac-text-sm ac-text-muted">
                Showing {rangeStart}–{rangeEnd} of {total}
              </span>
              <div className="ac-flex ac-gap-2">
                <button className="ac-btn" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0}>
                  ← Previous
                </button>
                <button
                  className="ac-btn"
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  disabled={offset + PAGE_SIZE >= total}
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </>
      )}

      <ReviewDialog
        approval={selected}
        orgName={selected ? orgName(selected.organization_id) : ""}
        onClose={() => setSelected(null)}
        onDecided={(updated) => {
          setSelected(updated);
          load();
        }}
      />
    </div>
  );
}

export default function PlatformApprovalsPage() {
  return <RealApprovalsFeed />;
}
