"use client";

// Platform Admin — Audit & Governance UI (M12).
// REAL-mode only, strictly READ-ONLY: this page consumes
// GET /api/v1/platform/audit (backend/app/api/v1/platform.py, M12.0) and
// renders it. It never creates, edits, or deletes an audit_events row —
// the audit trail is append-only by backend design, and this UI has no
// mutation affordances at all.
//
// Backend enforces PLATFORM_MANAGE on every call — this page hiding itself
// from non-platform-admin users (see Sidebar.tsx) is a UX convenience only,
// never the security boundary. A 403 here renders a distinct "Permission
// Denied" state, never an empty list.
//
// All filtering and pagination happen server-side via real query params
// (organization_id/action/entity_type/date_from/date_to/limit/offset) —
// this page never loads more than one page of results and filters client-side.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { auditApi, type AuditEventResponse } from "@/lib/api/audit";
import { platformApi, type BackendPlatformOrganization } from "@/lib/api/platform";

const PAGE_SIZE = 50;

// Entity types with a real, safe existing frontend route to navigate to.
// Deliberately NOT a backend catalog — just the subset of entity_type
// values this frontend knows how to link, per M8/M9/M11 routes. Anything
// else (or a null entity_id) renders as plain text, never a guessed link.
function entityHref(event: AuditEventResponse): string | null {
  if (!event.entity_id && event.entity_type !== "TenantFeatureOverride" && event.entity_type !== "TenantUsageLimit") {
    return null;
  }
  switch (event.entity_type) {
    case "Organization":
      return event.entity_id ? `/platform/organizations/${event.entity_id}` : null;
    case "Plan":
      return event.entity_id ? `/platform/plans/${event.entity_id}` : null;
    case "Subscription":
      // Subscriptions are managed within the owning organization's page —
      // there is no standalone /platform/subscriptions/{id} route.
      return `/platform/organizations/${event.organization_id}/subscriptions`;
    case "TenantFeatureOverride":
    case "TenantUsageLimit":
      // Both are managed inline on the organization detail page (M11) —
      // there is no dedicated per-override/per-limit route.
      return `/platform/organizations/${event.organization_id}`;
    default:
      return null;
  }
}

function actorLabel(event: AuditEventResponse): string {
  // user_id is nullable on AuditEvent (see AuditEventResponse schema) —
  // a null value is real backend semantics (e.g. system-initiated events),
  // not missing data, so it gets a neutral, non-invented label.
  return event.user_id ?? "System / Unattributed";
}

function MetadataView({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata ?? {});
  if (entries.length === 0) {
    return <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>No additional metadata recorded.</p>;
  }
  return (
    <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px" }}>
      {entries.map(([key, value]) => (
        <div key={key} style={{ display: "contents" }}>
          <dt className="ac-text-sm ac-text-muted" style={{ fontWeight: 600, wordBreak: "break-word" }}>{key}</dt>
          <dd className="ac-text-sm" style={{ margin: 0, wordBreak: "break-word", whiteSpace: "pre-wrap" }}>
            {renderMetadataValue(value)}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function renderMetadataValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  // Nested objects/arrays: pretty-print as JSON rather than "[object Object]".
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function EventDetailsDialog({ event, onClose }: { event: AuditEventResponse | null; onClose: () => void }) {
  useEffect(() => {
    if (!event) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [event, onClose]);

  if (!event) return null;
  const href = entityHref(event);

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
        aria-labelledby="audit-event-dialog-title"
        style={{ maxWidth: 560, width: "100%" }}
      >
        <h2 id="audit-event-dialog-title" className="ac-modal-title">
          Audit Event Details
        </h2>
        <div className="ac-modal-body" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <span className="ac-text-sm ac-text-muted">Event ID</span>
            <p className="ac-text-sm" style={{ margin: 0, wordBreak: "break-all" }}>{event.id}</p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Timestamp</span>
            <p className="ac-text-sm" style={{ margin: 0 }}>{new Date(event.created_at).toLocaleString()}</p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Organization ID</span>
            <p className="ac-text-sm" style={{ margin: 0, wordBreak: "break-all" }}>
              <Link href={`/platform/organizations/${event.organization_id}`}>{event.organization_id}</Link>
            </p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Actor</span>
            <p className="ac-text-sm" style={{ margin: 0, wordBreak: "break-all" }}>{actorLabel(event)}</p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Action</span>
            <p className="ac-text-sm" style={{ margin: 0, wordBreak: "break-word" }}>{event.action}</p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Entity Type</span>
            <p className="ac-text-sm" style={{ margin: 0 }}>{event.entity_type}</p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Entity ID</span>
            <p className="ac-text-sm" style={{ margin: 0, wordBreak: "break-all" }}>
              {event.entity_id ? (href ? <Link href={href}>{event.entity_id}</Link> : event.entity_id) : "—"}
            </p>
          </div>
          <div>
            <span className="ac-text-sm ac-text-muted">Metadata</span>
            <div className="ac-card" style={{ padding: "var(--ac-space-2)", marginTop: 4 }}>
              <MetadataView metadata={event.event_metadata} />
            </div>
          </div>
        </div>
        <div className="ac-modal-actions">
          <button className="ac-btn" onClick={onClose} autoFocus>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function RealAuditFeed() {
  const { accessToken, isAuthenticated } = useSession();
  const [events, setEvents] = useState<AuditEventResponse[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<AuditEventResponse | null>(null);

  const [orgs, setOrgs] = useState<BackendPlatformOrganization[]>([]);

  // Committed filter values (what's actually sent to the API). Text filters
  // are debounced from their input state below before landing here.
  const [organizationId, setOrganizationId] = useState("");
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // Raw input state for the debounced text filters.
  const [actionInput, setActionInput] = useState("");
  const [entityTypeInput, setEntityTypeInput] = useState("");

  const hasActiveFilters = Boolean(organizationId || action || entityType || dateFrom || dateTo);

  // Debounce free-text filters so we don't fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setAction(actionInput.trim());
      setOffset(0);
    }, 400);
    return () => clearTimeout(t);
  }, [actionInput]);

  useEffect(() => {
    const t = setTimeout(() => {
      setEntityType(entityTypeInput.trim());
      setOffset(0);
    }, 400);
    return () => clearTimeout(t);
  }, [entityTypeInput]);

  // Real organization list for the organization filter — never hardcoded.
  useEffect(() => {
    if (!accessToken) return;
    platformApi.listOrganizations(accessToken).then(setOrgs).catch(() => setOrgs([]));
  }, [accessToken]);

  useEffect(() => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    auditApi
      .listAuditEvents(accessToken, {
        organization_id: organizationId || undefined,
        action: action || undefined,
        entity_type: entityType || undefined,
        date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
        limit: PAGE_SIZE,
        offset,
      })
      .then((res) => {
        if (cancelled) return;
        setEvents(res.items);
        setTotal(res.total);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(normalizeApiError(err));
        setEvents([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, isAuthenticated, organizationId, action, entityType, dateFrom, dateTo, offset]);

  const clearFilters = () => {
    setOrganizationId("");
    setAction("");
    setEntityType("");
    setDateFrom("");
    setDateTo("");
    setActionInput("");
    setEntityTypeInput("");
    setOffset(0);
  };

  const orgName = (id: string) => orgs.find((o) => o.id === id)?.name ?? id;

  const columns: Column<AuditEventResponse>[] = [
    {
      key: "timestamp",
      header: "Timestamp",
      render: (e) => <span className="ac-text-sm">{new Date(e.created_at).toLocaleString()}</span>,
      sortValue: (e) => e.created_at,
    },
    {
      key: "organization",
      header: "Organization",
      render: (e) => (
        <Link href={`/platform/organizations/${e.organization_id}`} className="ac-text-sm">
          {orgName(e.organization_id)}
        </Link>
      ),
    },
    {
      key: "actor",
      header: "Actor",
      render: (e) => <span className="ac-text-sm" style={{ wordBreak: "break-all" }}>{actorLabel(e)}</span>,
    },
    { key: "action", header: "Action", render: (e) => <span className="ac-text-sm" style={{ wordBreak: "break-word" }}>{e.action}</span> },
    { key: "entity_type", header: "Entity Type", render: (e) => <span className="ac-text-sm">{e.entity_type}</span> },
    {
      key: "entity_id",
      header: "Entity ID",
      render: (e) => {
        const href = entityHref(e);
        if (!e.entity_id) return <span className="ac-text-sm ac-text-muted">—</span>;
        return href ? (
          <Link href={href} className="ac-text-sm" style={{ wordBreak: "break-all" }}>
            {e.entity_id}
          </Link>
        ) : (
          <span className="ac-text-sm" style={{ wordBreak: "break-all" }}>{e.entity_id}</span>
        );
      },
    },
    {
      key: "details",
      header: "Details",
      render: (e) => (
        <button className="ac-btn" style={{ fontSize: 12, padding: "2px 8px" }} onClick={() => setSelectedEvent(e)}>
          View Details
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
  const rangeEnd = Math.min(offset + events.length, total);

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Audit & Governance" },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Platform — Audit &amp; Governance</h1>
          <p className="ac-subtitle">
            Read-only, cross-tenant view of the append-only audit trail. Nothing on this page can create, edit, or delete
            audit records.
          </p>
        </div>
      </div>

      {/* Filters — all server-side, wired directly to GET /platform/audit query params. */}
      <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
        <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
          <div>
            <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }} htmlFor="audit-filter-org">
              Organization
            </label>
            <select
              id="audit-filter-org"
              className="ac-select"
              style={{ minWidth: 220 }}
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

          <div>
            <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }} htmlFor="audit-filter-action">
              Action
            </label>
            <input
              id="audit-filter-action"
              className="ac-input"
              style={{ minWidth: 200 }}
              placeholder="e.g. platform.plan.created"
              value={actionInput}
              onChange={(e) => setActionInput(e.target.value)}
            />
          </div>

          <div>
            <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }} htmlFor="audit-filter-entity-type">
              Entity Type
            </label>
            <input
              id="audit-filter-entity-type"
              className="ac-input"
              style={{ minWidth: 180 }}
              placeholder="e.g. Subscription"
              value={entityTypeInput}
              onChange={(e) => setEntityTypeInput(e.target.value)}
            />
          </div>

          <div>
            <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }} htmlFor="audit-filter-from">
              Date From
            </label>
            <input
              id="audit-filter-from"
              type="date"
              className="ac-input"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setOffset(0);
              }}
            />
          </div>

          <div>
            <label className="ac-text-sm" style={{ display: "block", marginBottom: 4 }} htmlFor="audit-filter-to">
              Date To
            </label>
            <input
              id="audit-filter-to"
              type="date"
              className="ac-input"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setOffset(0);
              }}
            />
          </div>

          {hasActiveFilters && (
            <button className="ac-btn" onClick={clearFilters}>
              Clear Filters
            </button>
          )}
        </div>
      </div>

      {forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to view the platform audit trail.
          </p>
        </div>
      ) : (
        <>
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={!error && events.length === 0}
            emptyMessage={
              hasActiveFilters ? "No events match the selected filters." : "No audit activity found."
            }
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <div className="ac-table-desktop">
                <DataTable columns={columns} rows={events} caption="Platform audit events" />
              </div>
              <div className="ac-row-cards">
                {events.map((e) => (
                  <div className="ac-row-card" key={e.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Timestamp</span>
                      <span>{new Date(e.created_at).toLocaleString()}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Organization</span>
                      <Link href={`/platform/organizations/${e.organization_id}`}>{orgName(e.organization_id)}</Link>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Actor</span>
                      <span style={{ wordBreak: "break-all" }}>{actorLabel(e)}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Action</span>
                      <span style={{ wordBreak: "break-word" }}>{e.action}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Entity</span>
                      <span style={{ wordBreak: "break-word" }}>
                        {e.entity_type}
                        {e.entity_id ? ` · ${e.entity_id}` : ""}
                      </span>
                    </div>
                    <div className="ac-row-card-actions">
                      <button className="ac-btn" onClick={() => setSelectedEvent(e)}>
                        View Details
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
                <button
                  className="ac-btn"
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  disabled={offset === 0}
                >
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

      <EventDetailsDialog event={selectedEvent} onClose={() => setSelectedEvent(null)} />
    </div>
  );
}

export default function PlatformAuditPage() {
  return <RealAuditFeed />;
}
