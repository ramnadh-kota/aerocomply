"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { technicians, isOnShiftNow } from "@/lib/mock/technicians";
import { workOrdersForTechnician } from "@/lib/mock/workOrders";
import type { Technician } from "@/lib/mock/types";
import { useDataMode } from "@/lib/data-mode/DataModeContext";
import { useSession } from "@/lib/auth/SessionContext";
import { usersApi, technicianQualificationsApi, type BackendOrganizationUser } from "@/lib/api/technicians";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";

interface RealRow {
  user: BackendOrganizationUser;
  qualificationCount: number;
  activeQualificationCount: number;
}

function RealTechniciansList() {
  const { apiBaseUrl } = useDataMode();
  const { accessToken, isAuthenticated } = useSession();
  const [rows, setRows] = useState<RealRow[]>([]);
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
    Promise.all([usersApi.list(accessToken), technicianQualificationsApi.list(accessToken)])
      .then(([users, qualifications]) => {
        if (cancelled) return;
        const built = users.map((user) => {
          const own = qualifications.filter((q) => q.user_id === user.id);
          return {
            user,
            qualificationCount: own.length,
            activeQualificationCount: own.filter((q) => !q.revoked).length,
          };
        });
        setRows(built);
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

  const columns: Column<RealRow>[] = [
    { key: "name", header: "Person", render: (r) => r.user.full_name, sortValue: (r) => r.user.full_name },
    { key: "email", header: "Email", render: (r) => r.user.email },
    { key: "roles", header: "Roles", render: (r) => r.user.roles.join(", ") || "None" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.user.is_active ? "ACTIVE" : "STORED"} label={r.user.is_active ? "Active" : "Inactive"} /> },
    {
      key: "qualifications",
      header: "Qualifications",
      render: (r) =>
        r.qualificationCount === 0
          ? "None on record"
          : `${r.activeQualificationCount} active / ${r.qualificationCount} total`,
    },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Technicians" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Technicians</h1>
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
          emptyMessage="No users are registered in this organization yet."
        >
          <div className="ac-card" style={{ padding: 0 }}>
            <DataTable columns={columns} rows={rows} getRowHref={(r) => `/maintenance/technicians/${r.user.id}`} />
          </div>
        </RealDataPanel>
      )}
    </div>
  );
}

function DemoTechniciansList() {
  const columns: Column<Technician>[] = [
    { key: "name", header: "Technician", render: (t) => t.name, sortValue: (t) => t.name },
    { key: "role", header: "Role", render: (t) => t.role },
    { key: "shift", header: "Shift", render: (t) => `${t.shiftStart}–${t.shiftEnd}` },
    { key: "onShift", header: "On Shift Now", render: (t) => <StatusBadge status={isOnShiftNow(t) ? "ACTIVE" : "STORED"} label={isOnShiftNow(t) ? "On Shift" : "Off Shift"} /> },
    { key: "tasks", header: "Assigned Work Orders", render: (t) => workOrdersForTechnician(t.id).length },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Technician Workbench" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Technician Workbench</h1>
          <p className="ac-subtitle">Select a technician to view their shift workbench</p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={technicians} getRowHref={(t) => `/maintenance/technicians/${t.id}`} />
      </div>
    </div>
  );
}

export default function TechniciansPage() {
  const { isReal, hydrated } = useDataMode();
  if (!hydrated) return null;
  return isReal ? <RealTechniciansList /> : <DemoTechniciansList />;
}
