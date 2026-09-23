"use client";

// Platform Admin — Organization Management.
// Supports both REAL-mode (backend-enforced PLATFORM_MANAGE) and DEMO-mode (deterministic synthetic data).
// Backend enforces PLATFORM_MANAGE on every call here (app/api/v1/platform.py).

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type BackendPlatformOrganization } from "@/lib/api/platform";
import { DEMO_PLATFORM_ORGANIZATIONS } from "@/lib/demo/demoPlatform";

function CreateAdminForm({ orgId, onDone }: { orgId: string; onDone: () => void }) {
  const { accessToken } = useSession();
  const { mode } = useDataMode();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [done, setDone] = useState(false);

  const submit = () => {
    if (mode === "DEMO") {
      setDone(true);
      setTimeout(onDone, 500);
      return;
    }
    if (!accessToken || !email.trim() || !fullName.trim() || password.length < 8) return;
    setBusy(true);
    setError(null);
    platformApi
      .createOrganizationAdmin(accessToken, orgId, {
        email: email.trim(),
        full_name: fullName.trim(),
        password,
      })
      .then(() => {
        setDone(true);
        onDone();
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setBusy(false));
  };

  if (done) {
    return <p className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>Admin created successfully.</p>;
  }

  return (
    <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
      <input
        className="ac-input"
        style={{ width: 220 }}
        placeholder="admin@customer.com"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        aria-label="Admin email"
      />
      <input
        className="ac-input"
        style={{ width: 180 }}
        placeholder="Full name"
        value={fullName}
        onChange={(e) => setFullName(e.target.value)}
        aria-label="Admin full name"
      />
      <input
        className="ac-input"
        style={{ width: 180 }}
        placeholder="Password (8+ chars)"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        aria-label="Admin password"
      />
      <button className="ac-btn" onClick={submit} disabled={busy || !email.trim() || !fullName.trim()}>
        {busy ? "Creating…" : "Create Admin"}
      </button>
      {error && <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>{error.message}</span>}
    </div>
  );
}

export default function PlatformOrganizationsPage() {
  const { accessToken, isAuthenticated, user } = useSession();
  const { mode } = useDataMode();

  const [orgs, setOrgs] = useState<BackendPlatformOrganization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "ACTIVE" | "SUSPENDED">("ALL");
  const [industryFilter, setIndustryFilter] = useState<string>("ALL");

  // Creation State
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [confirmSuspendOrg, setConfirmSuspendOrg] = useState<BackendPlatformOrganization | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  const load = () => {
    if (mode === "DEMO") {
      setOrgs(DEMO_PLATFORM_ORGANIZATIONS);
      setLoading(false);
      setError(null);
      return;
    }

    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    platformApi
      .listOrganizations(accessToken)
      .then(setOrgs)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, accessToken, isAuthenticated]);

  const filteredOrgs = useMemo(() => {
    return orgs.filter((o) => {
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = o.name.toLowerCase().includes(q);
        const matchesId = o.id.toLowerCase().includes(q);
        if (!matchesName && !matchesId) return false;
      }
      if (statusFilter !== "ALL" && o.status !== statusFilter) return false;
      if (industryFilter !== "ALL" && o.industry !== industryFilter) return false;
      return true;
    });
  }, [orgs, searchQuery, statusFilter, industryFilter]);

  const createOrg = () => {
    if (!newName.trim()) return;
    if (mode === "DEMO") {
      const syntheticOrg: BackendPlatformOrganization = {
        id: `00000000-0000-0000-0000-${String(Date.now()).slice(-12)}`,
        name: newName.trim(),
        status: "ACTIVE",
        industry: "DRONE_UAV",
        created_at: new Date().toISOString(),
        user_count: 0,
        aircraft_count: 0,
        drone_count: 0,
      };
      setOrgs([syntheticOrg, ...orgs]);
      setNewName("");
      setExpandedId(syntheticOrg.id);
      return;
    }
    if (!accessToken) return;
    setCreating(true);
    setError(null);
    platformApi
      .createOrganization(accessToken, newName.trim())
      .then((created) => {
        setNewName("");
        load();
        setExpandedId(created.id);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setCreating(false));
  };

  const toggleStatus = (org: BackendPlatformOrganization) => {
    if (mode === "DEMO") {
      setOrgs((prev) =>
        prev.map((o) =>
          o.id === org.id
            ? { ...o, status: o.status === "ACTIVE" ? "SUSPENDED" : "ACTIVE" }
            : o
        )
      );
      return;
    }

    if (!accessToken) return;
    if (org.status === "ACTIVE") {
      setConfirmSuspendOrg(org);
      return;
    }
    platformApi.activateOrganization(accessToken, org.id).then(load).catch((err) => setError(normalizeApiError(err)));
  };

  const confirmSuspend = () => {
    if (!confirmSuspendOrg) return;
    if (mode === "DEMO") {
      setOrgs((prev) =>
        prev.map((o) => (o.id === confirmSuspendOrg.id ? { ...o, status: "SUSPENDED" } : o))
      );
      setConfirmSuspendOrg(null);
      return;
    }
    if (!accessToken) return;
    setActionBusy(true);
    platformApi
      .suspendOrganization(accessToken, confirmSuspendOrg.id)
      .then(() => {
        setConfirmSuspendOrg(null);
        load();
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setActionBusy(false));
  };

  const columns: Column<BackendPlatformOrganization>[] = [
    {
      key: "name",
      header: "Organization",
      render: (o) => (
        <div>
          <Link href={`/platform/organizations/${o.id}`} style={{ fontWeight: 600 }}>
            {o.name}
          </Link>
          <div className="ac-text-sm ac-text-muted" style={{ fontSize: 11 }}>
            ID: {o.id}
          </div>
        </div>
      ),
      sortValue: (o) => o.name,
    },
    {
      key: "status",
      header: "Status",
      render: (o) => <StatusBadge {...genericStatusBadge(o.status)} />,
      sortValue: (o) => o.status,
    },
    {
      key: "industry",
      header: "Industry",
      render: (o) => (
        <span className="ac-badge" style={{ fontSize: 11 }}>
          {o.industry ? o.industry.replace(/_/g, " ") : "UNSET"}
        </span>
      ),
    },
    { key: "users", header: "Users", render: (o) => o.user_count, sortValue: (o) => o.user_count },
    {
      key: "fleet",
      header: "Fleet",
      render: (o) => (
        <span style={{ fontSize: 12 }}>
          {o.aircraft_count > 0 && <span>✈ {o.aircraft_count} </span>}
          {(o.drone_count ?? 0) > 0 && <span>◆ {o.drone_count}</span>}
          {o.aircraft_count === 0 && (o.drone_count ?? 0) === 0 && <span className="ac-text-muted">—</span>}
        </span>
      ),
      sortValue: (o) => o.aircraft_count + (o.drone_count ?? 0),
    },
    {
      key: "created",
      header: "Created",
      render: (o) => new Date(o.created_at).toLocaleDateString(),
      sortValue: (o) => o.created_at,
    },
    {
      key: "actions",
      header: "Actions",
      render: (o) => (
        <div className="ac-flex ac-gap-2">
          <button className="ac-btn" style={{ fontSize: 12, padding: "2px 8px" }} onClick={() => toggleStatus(o)}>
            {o.status === "ACTIVE" ? "Suspend" : "Activate"}
          </button>
          <button
            className="ac-btn"
            style={{ fontSize: 12, padding: "2px 8px" }}
            onClick={() => setExpandedId(expandedId === o.id ? null : o.id)}
          >
            {expandedId === o.id ? "Close" : "Admin"}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
      <Breadcrumbs items={[{ label: "Platform Admin", href: "/platform/dashboard" }, { label: "Organizations" }]} />

      <div className="ac-section-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h1 className="ac-h1" style={{ margin: 0 }}>Platform — Organizations</h1>
          <p className="ac-subtitle" style={{ margin: "4px 0 0" }}>
            Customer tenants control plane. Direct metadata inspection and tenant lifecycle management.
          </p>
        </div>
        <Link className="ac-btn" href="/platform/organizations/provision">
          + Provision Organization
        </Link>
      </div>

      {mode === "REAL" && !isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : mode === "REAL" && !isPlatformUser ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)", borderLeft: "4px solid var(--ac-status-non-compliant)" }}>
          <h3 className="ac-h3" style={{ margin: "0 0 6px" }}>Platform Access Denied</h3>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Your account does not possess the <code>PLATFORM_MANAGE</code> authority required to view or administer tenant control planes.
          </p>
        </div>
      ) : (
        <>
          {/* Quick Create Bar */}
          <div className="ac-card" style={{ padding: "var(--ac-space-3)" }}>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", alignItems: "center" }}>
              <input
                className="ac-input"
                style={{ width: 320 }}
                placeholder="New customer organization name…"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                aria-label="New organization name"
              />
              <button className="ac-btn" onClick={createOrg} disabled={creating || !newName.trim()}>
                {creating ? "Creating…" : "+ Fast Create"}
              </button>
              <span className="ac-text-sm ac-text-muted" style={{ marginLeft: "auto" }}>
                Need full onboarding? Use <Link href="/platform/organizations/provision">Guided Provisioning →</Link>
              </span>
            </div>
          </div>

          {/* Search & Filters */}
          <div
            className="ac-card"
            style={{
              padding: "var(--ac-space-3)",
              display: "flex",
              flexWrap: "wrap",
              gap: 12,
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center", flex: 1 }}>
              <input
                className="ac-input"
                style={{ minWidth: 260, flex: "1 1 260px" }}
                placeholder="Search by organization name or UUID…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search organizations"
              />

              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="ac-text-sm ac-text-muted">Status:</span>
                <select
                  className="ac-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as any)}
                  aria-label="Filter by status"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="SUSPENDED">SUSPENDED</option>
                </select>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="ac-text-sm ac-text-muted">Industry:</span>
                <select
                  className="ac-select"
                  value={industryFilter}
                  onChange={(e) => setIndustryFilter(e.target.value)}
                  aria-label="Filter by industry"
                >
                  <option value="ALL">All Industries</option>
                  <option value="DRONE_UAV">Drone / UAV</option>
                  <option value="AIRCRAFT">Aircraft</option>
                  <option value="HELICOPTER">Helicopter</option>
                  <option value="EVTOL_AAM">eVTOL / AAM</option>
                </select>
              </div>
            </div>

            <div className="ac-text-sm ac-text-muted">
              Showing {filteredOrgs.length} of {orgs.length} organizations
            </div>
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={filteredOrgs.length === 0}
            emptyMessage={
              searchQuery || statusFilter !== "ALL" || industryFilter !== "ALL"
                ? "No organizations match your active search or filter criteria."
                : "No customer organizations exist yet. Use '+ Provision Organization' above to onboard one."
            }
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <div className="ac-table-desktop">
                <DataTable columns={columns} rows={filteredOrgs} getRowHref={(o) => `/platform/organizations/${o.id}`} />
              </div>

              <div className="ac-row-cards">
                {filteredOrgs.map((o) => (
                  <div className="ac-row-card" key={o.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Organization</span>
                      <strong>
                        <Link href={`/platform/organizations/${o.id}`}>{o.name}</Link>
                      </strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Status</span>
                      <StatusBadge {...genericStatusBadge(o.status)} />
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Industry</span>
                      <span className="ac-badge" style={{ fontSize: 11 }}>{o.industry ?? "UNSET"}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Users / Fleet</span>
                      <span>
                        {o.user_count} users · {o.aircraft_count} aircraft · {o.drone_count ?? 0} drones
                      </span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Created</span>
                      <span>{new Date(o.created_at).toLocaleDateString()}</span>
                    </div>
                    <div className="ac-row-card-actions">
                      <button className="ac-btn" onClick={() => toggleStatus(o)}>
                        {o.status === "ACTIVE" ? "Suspend" : "Activate"}
                      </button>
                      <button className="ac-btn" onClick={() => setExpandedId(expandedId === o.id ? null : o.id)}>
                        {expandedId === o.id ? "Close" : "Create Admin"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {expandedId && (
              <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
                <strong className="ac-text-sm">Create first admin for this organization</strong>
                <CreateAdminForm orgId={expandedId} onDone={load} />
              </div>
            )}
          </RealDataPanel>
        </>
      )}

      <ConfirmDialog
        open={confirmSuspendOrg !== null}
        title={`Suspend ${confirmSuspendOrg?.name ?? "organization"}?`}
        body={`This immediately suspends "${confirmSuspendOrg?.name ?? ""}". Every user in this tenant loses normal operational access until the organization is reactivated. This is reversible at any time via Activate.`}
        confirmLabel="Suspend Organization"
        cancelLabel="Cancel"
        busy={actionBusy}
        onConfirm={confirmSuspend}
        onCancel={() => setConfirmSuspendOrg(null)}
      />
    </div>
  );
}
