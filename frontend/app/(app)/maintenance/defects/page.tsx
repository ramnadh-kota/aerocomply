"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, defectStatusBadge, inspectorReviewStatusBadge } from "@/components/status/StatusBadge";
import { defects } from "@/lib/mock/defects";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import type { Defect } from "@/lib/mock/types";

export default function DefectsPage() {
  const { submissions } = useMroState();
  const columns: Column<Defect>[] = [
    {
      key: "aircraft",
      header: "Aircraft",
      render: (d) => {
        const a = getAircraftById(d.aircraftId);
        return a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : d.aircraftId;
      },
    },
    { key: "description", header: "Description", render: (d) => d.description },
    { key: "severity", header: "Severity", render: (d) => d.severity },
    { key: "reported", header: "Reported", render: (d) => d.reportedDate, sortValue: (d) => d.reportedDate },
    {
      key: "workOrder",
      header: "Work Order",
      render: (d) => (d.workOrderId ? <Link href={`/maintenance/work-orders/${d.workOrderId}`} className="ac-mono">{d.workOrderId}</Link> : "—"),
    },
    { key: "status", header: "Status", render: (d) => <StatusBadge {...defectStatusBadge(d.status)} /> },
    {
      key: "inspection",
      header: "Inspection Status",
      render: (d) => {
        // Live checklist/inspection state — see lib/mro-state/MroStateContext.
        const record = d.workOrderId ? submissions[d.workOrderId] : undefined;
        return record ? <StatusBadge {...inspectorReviewStatusBadge(record.inspectorDecisionStatus)} /> : "—";
      },
    },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Defects" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Defects</h1>
          <p className="ac-subtitle">{defects.length} defects tracked across the fleet</p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={defects} />
      </div>
    </div>
  );
}
