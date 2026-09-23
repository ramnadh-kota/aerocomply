"use client";

// Platform Admin — Cross-Tenant Subscriptions Management.
// Uses existing Subscription model (backend/app/models/subscription.py).
// Billing engine is clearly labeled as PLATFORM-MANAGED / MANUAL.

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  platformApi,
  type BackendPlatformOrganization,
} from "@/lib/api/platform";
import { subscriptionApi, type SubscriptionResponse } from "@/lib/api/subscription";
import { planApi, type PlanResponse } from "@/lib/api/plan";
import {
  DEMO_PLATFORM_ORGANIZATIONS,
  DEMO_PLATFORM_SUBSCRIPTIONS,
  DEMO_PLATFORM_PLANS,
} from "@/lib/demo/demoPlatform";

interface SubscriptionWithDetails {
  subscription: SubscriptionResponse;
  orgName: string;
  planName: string;
}

function subscriptionStatusBadge(status: string) {
  const map: Record<string, Parameters<typeof StatusBadge>[0]["status"]> = {
    TRIALING: "REVIEW_REQUIRED",
    ACTIVE: "COMPLIANT",
    PAST_DUE: "REVIEW_REQUIRED",
    CANCELED: "UNKNOWN",
    SCHEDULED: "INSUFFICIENT_DATA",
  };
  return { status: map[status] ?? "UNKNOWN", label: status.replace(/_/g, " ") };
}

export default function PlatformSubscriptionsPage() {
  const { accessToken, isAuthenticated, user } = useSession();
  const { mode } = useDataMode();

  const [subscriptions, setSubscriptions] = useState<SubscriptionWithDetails[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [statusFilter, setStatusFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState("");

  const isPlatformUser =
    user?.roles?.some((r) => r === "PLATFORM_ADMIN" || r === "PLATFORM_STAFF") ?? false;

  useEffect(() => {
    if (mode === "DEMO") {
      const orgMap = new Map(DEMO_PLATFORM_ORGANIZATIONS.map((o) => [o.id, o.name]));
      const planMap = new Map(DEMO_PLATFORM_PLANS.map((p) => [p.id, p.name]));

      const combined: SubscriptionWithDetails[] = DEMO_PLATFORM_SUBSCRIPTIONS.map((s) => ({
        subscription: s,
        orgName: orgMap.get(s.organization_id) ?? s.organization_id,
        planName: planMap.get(s.plan_id) ?? s.plan_id,
      }));
      setSubscriptions(combined);
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

    Promise.all([
      platformApi.listOrganizations(accessToken),
      planApi.listPlans(accessToken),
    ])
      .then(async ([orgs, plans]) => {
        const orgMap = new Map(orgs.map((o) => [o.id, o.name]));
        const planMap = new Map(plans.map((p) => [p.id, p.name]));

        // Fetch subscriptions across orgs in parallel
        const subResults = await Promise.allSettled(
          orgs.map((o) => subscriptionApi.listForOrganization(accessToken, o.id))
        );

        const allSubs: SubscriptionWithDetails[] = [];
        subResults.forEach((res, idx) => {
          if (res.status === "fulfilled") {
            const orgId = orgs[idx].id;
            res.value.forEach((s) => {
              allSubs.push({
                subscription: s,
                orgName: orgMap.get(orgId) ?? orgId,
                planName: planMap.get(s.plan_id) ?? s.plan_id,
              });
            });
          }
        });

        setSubscriptions(allSubs);
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [mode, accessToken, isAuthenticated]);

  const filteredSubs = useMemo(() => {
    return subscriptions.filter((s) => {
      if (statusFilter !== "ALL" && s.subscription.status !== statusFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesOrg = s.orgName.toLowerCase().includes(q) || s.subscription.organization_id.toLowerCase().includes(q);
        const matchesPlan = s.planName.toLowerCase().includes(q);
        if (!matchesOrg && !matchesPlan) return false;
      }
      return true;
    });
  }, [subscriptions, statusFilter, searchQuery]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--ac-space-4, 20px)" }}>
      <Breadcrumbs items={[{ label: "Platform Admin", href: "/platform/dashboard" }, { label: "Subscriptions" }]} />

      <div
        className="ac-section-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <div>
          <h1 className="ac-h1" style={{ margin: 0 }}>Platform — Subscriptions</h1>
          <p className="ac-subtitle" style={{ margin: "4px 0 0" }}>
            Cross-tenant subscription ledger. Commercial billing engine state is <strong>PLATFORM-MANAGED / MANUAL</strong>.
          </p>
        </div>
        <Link className="ac-btn" href="/platform/plans">
          Plan Catalog →
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
            Your account does not possess the <code>PLATFORM_MANAGE</code> authority required to view subscriptions across tenants.
          </p>
        </div>
      ) : (
        <>
          {/* Filters & Search */}
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
                placeholder="Search by organization name, ID, or plan…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                aria-label="Search subscriptions"
              />

              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="ac-text-sm ac-text-muted">Status:</span>
                <select
                  className="ac-select"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  aria-label="Filter by subscription status"
                >
                  <option value="ALL">All Statuses</option>
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="TRIALING">TRIALING</option>
                  <option value="PAST_DUE">PAST_DUE</option>
                  <option value="CANCELED">CANCELED</option>
                  <option value="SCHEDULED">SCHEDULED</option>
                </select>
              </div>
            </div>

            <div className="ac-text-sm ac-text-muted">
              Showing {filteredSubs.length} of {subscriptions.length} subscriptions
            </div>
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={filteredSubs.length === 0}
            emptyMessage="No subscription records match the active criteria."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <table className="ac-table" style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th>Customer Organization</th>
                    <th>Subscribed Plan</th>
                    <th>Status</th>
                    <th>Billing Engine</th>
                    <th>Active Window</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredSubs.map(({ subscription: s, orgName, planName }) => (
                    <tr key={s.id}>
                      <td>
                        <strong>
                          <Link href={`/platform/organizations/${s.organization_id}`}>
                            {orgName}
                          </Link>
                        </strong>
                        <div className="ac-text-sm ac-text-muted" style={{ fontSize: 11 }}>
                          <code>{s.organization_id}</code>
                        </div>
                      </td>
                      <td>
                        <strong>{planName}</strong>
                      </td>
                      <td>
                        <StatusBadge {...subscriptionStatusBadge(s.status)} />
                      </td>
                      <td>
                        <span className="ac-badge" style={{ fontSize: 11 }}>
                          MANUAL (PLATFORM)
                        </span>
                      </td>
                      <td style={{ fontSize: 13 }}>
                        <div>From: {new Date(s.starts_at).toLocaleDateString()}</div>
                        <div className="ac-text-muted" style={{ fontSize: 11 }}>
                          To: {s.ends_at ? new Date(s.ends_at).toLocaleDateString() : "Open-ended (No expiry)"}
                        </div>
                      </td>
                      <td>
                        <Link
                          className="ac-btn"
                          style={{ fontSize: 11, padding: "3px 8px" }}
                          href={`/platform/organizations/${s.organization_id}/subscriptions`}
                        >
                          Manage Subscriptions →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </RealDataPanel>
        </>
      )}
    </div>
  );
}
