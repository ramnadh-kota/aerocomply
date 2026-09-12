"use client";

// Platform Admin — Organization Management. REAL-mode only: this is
// cross-tenant platform staff tooling, not a customer-facing feature, so
// there is no demo dataset for it. Backend enforces PLATFORM_MANAGE on
// every call here (app/api/v1/platform.py) — this page hiding itself from
// non-platform-admin users is a UX convenience, never the security boundary.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, genericStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { platformApi, type BackendPlatformOrganization } from "@/lib/api/platform";

function CreateAdminForm({ orgId, onDone }: { orgId: string; onDone: () => void }) {
  const { accessToken } = useSession();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [done, setDone] = useState(false);

  const submit = () => {
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
    return <p className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>Admin created.</p>;
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
        placeholder="Temporary password (8+ chars)"
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        aria-label="Admin password"
      />
      <button className="ac-btn" onClick={submit} disabled={busy}>
        {busy ? "Creating…" : "Create First Admin"}
      </button>
      {error && <span className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>{error.message}</span>}
    </div>
  );
}

function RealPlatformOrganizations() {
  const { accessToken, isAuthenticated } = useSession();
  const [orgs, setOrgs] = useState<BackendPlatformOrganization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = () => {
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
  }, [accessToken, isAuthenticated]);

  const createOrg = () => {
    if (!accessToken || !newName.trim()) return;
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
    if (!accessToken) return;
    const action = org.status === "ACTIVE" ? platformApi.suspendOrganization : platformApi.activateOrganization;
    action(accessToken, org.id).then(load).catch((err) => setError(normalizeApiError(err)));
  };

  const columns: Column<BackendPlatformOrganization>[] = [
    { key: "name", header: "Organization", render: (o) => o.name },
    { key: "status", header: "Status", render: (o) => <StatusBadge {...genericStatusBadge(o.status)} /> },
    { key: "users", header: "Users", render: (o) => o.user_count },
    { key: "aircraft", header: "Aircraft", render: (o) => o.aircraft_count },
    { key: "created", header: "Created", render: (o) => new Date(o.created_at).toLocaleDateString(), sortValue: (o) => o.created_at },
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
            {expandedId === o.id ? "Close" : "Create Admin"}
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Platform Admin", href: "/platform/organizations" }, { label: "Organizations" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Platform — Organizations</h1>
          <p className="ac-subtitle">Cross-tenant administration. Not visible to customer users.</p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <>
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap" }}>
              <input
                className="ac-input"
                style={{ width: 280 }}
                placeholder="New customer organization name…"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                aria-label="New organization name"
              />
              <button className="ac-btn" onClick={createOrg} disabled={creating || !newName.trim()}>
                {creating ? "Creating…" : "Create Organization"}
              </button>
            </div>
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={orgs.length === 0}
            emptyMessage="No customer organizations exist yet. Create one above to begin onboarding."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <DataTable columns={columns} rows={orgs} />
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
    </div>
  );
}

export default function PlatformOrganizationsPage() {
  return <RealPlatformOrganizations />;
}
