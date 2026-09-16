"use client";

// Platform Admin — Plan Catalog. REAL-mode only, same pattern as
// /platform/organizations: this is cross-tenant platform staff tooling, not
// a customer-facing feature, so there is no demo dataset. Backend enforces
// PLATFORM_MANAGE on every call here (app/api/v1/platform.py, M5) — this
// page hiding itself from non-platform-admin users (and rendering a
// permission-denied state on 403) is a UX convenience, never the security
// boundary.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { planApi, type PlanResponse } from "@/lib/api/plan";

function planStatusBadge(isActive: boolean) {
  return isActive
    ? { status: "COMPLIANT" as const, label: "Active" }
    : { status: "UNKNOWN" as const, label: "Inactive" };
}

function RealPlatformPlans() {
  const { accessToken, isAuthenticated } = useSession();
  const [plans, setPlans] = useState<PlanResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<NormalizedApiError | null>(null);

  const load = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    planApi
      .listPlans(accessToken)
      .then(setPlans)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated]);

  const createPlan = () => {
    if (!accessToken || !name.trim() || !code.trim()) return;
    setCreating(true);
    setCreateError(null);
    planApi
      .createPlan(accessToken, {
        name: name.trim(),
        code: code.trim(),
        description: description.trim() || null,
      })
      .then(() => {
        setName("");
        setCode("");
        setDescription("");
        load();
      })
      .catch((err) => setCreateError(normalizeApiError(err)))
      .finally(() => setCreating(false));
  };

  const columns: Column<PlanResponse>[] = [
    {
      key: "name",
      header: "Name",
      render: (p) => (
        <Link href={`/platform/plans/${p.id}`} style={{ wordBreak: "break-word" }}>
          {p.name}
        </Link>
      ),
    },
    { key: "code", header: "Code", render: (p) => <span style={{ wordBreak: "break-word" }}>{p.code}</span> },
    {
      key: "description",
      header: "Description",
      render: (p) => <span style={{ wordBreak: "break-word" }}>{p.description ?? "—"}</span>,
    },
    { key: "status", header: "Status", render: (p) => <StatusBadge {...planStatusBadge(p.is_active)} /> },
    {
      key: "actions",
      header: "Actions",
      render: (p) => (
        <Link className="ac-btn" style={{ fontSize: 12, padding: "2px 8px" }} href={`/platform/plans/${p.id}`}>
          View
        </Link>
      ),
    },
  ];

  const forbidden = error?.kind === "forbidden";

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Platform Admin", href: "/platform/organizations" },
          { label: "Plans" },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Platform — Plan Catalog</h1>
          <p className="ac-subtitle">Global plan catalog administration. Not visible to customer users.</p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Platform administration requires signing in as a platform admin. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to administer plans.
          </p>
        </div>
      ) : (
        <>
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Create a plan</strong>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
              <input
                className="ac-input"
                style={{ width: 220 }}
                placeholder="Plan name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-label="Plan name"
              />
              <input
                className="ac-input"
                style={{ width: 160 }}
                placeholder="Plan code"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                aria-label="Plan code"
              />
              <input
                className="ac-input"
                style={{ width: 280 }}
                placeholder="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                aria-label="Plan description"
              />
              <button className="ac-btn" onClick={createPlan} disabled={creating || !name.trim() || !code.trim()}>
                {creating ? "Creating…" : "Create Plan"}
              </button>
            </div>
            {createError && (
              <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                {createError.message}
              </p>
            )}
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={plans.length === 0}
            emptyMessage="No plans have been configured yet."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <div className="ac-table-desktop">
                <DataTable columns={columns} rows={plans} getRowHref={(p) => `/platform/plans/${p.id}`} />
              </div>
              <div className="ac-row-cards">
                {plans.map((p) => (
                  <div className="ac-row-card" key={p.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Name</span>
                      <strong style={{ wordBreak: "break-word" }}>
                        <Link href={`/platform/plans/${p.id}`}>{p.name}</Link>
                      </strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Code</span>
                      <span style={{ wordBreak: "break-word" }}>{p.code}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Description</span>
                      <span style={{ wordBreak: "break-word" }}>{p.description ?? "—"}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Status</span>
                      <StatusBadge {...planStatusBadge(p.is_active)} />
                    </div>
                    <div className="ac-row-card-actions">
                      <Link className="ac-btn" href={`/platform/plans/${p.id}`}>
                        View
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </RealDataPanel>
        </>
      )}
    </div>
  );
}

export default function PlatformPlansPage() {
  return <RealPlatformPlans />;
}
