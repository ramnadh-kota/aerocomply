"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { maintenanceEvents } from "@/lib/mock/maintenance";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import type { MaintenanceEvent } from "@/lib/mock/types";

export default function MaintenanceRecordsPage() {
  const columns: Column<MaintenanceEvent>[] = [
    { key: "date", header: "Date", render: (m) => m.date, sortValue: (m) => m.date },
    {
      key: "aircraft",
      header: "Aircraft",
      render: (m) => {
        const a = getAircraftById(m.aircraftId);
        return a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : m.aircraftId;
      },
    },
    { key: "type", header: "Type", render: (m) => m.eventType.replace(/_/g, " ") },
    { key: "description", header: "Description", render: (m) => m.description },
    {
      key: "status",
      header: "Status",
      render: (m) => (
        <StatusBadge
          status={m.status === "OVERDUE" ? "NON_COMPLIANT" : m.status === "COMPLETED" ? "COMPLIANT" : m.status === "IN_PROGRESS" ? "REVIEW_REQUIRED" : "PENDING"}
          label={m.status.replace(/_/g, " ")}
        />
      ),
    },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Maintenance Records" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Maintenance Records</h1>
          <p className="ac-subtitle">{maintenanceEvents.length} compliance-oriented maintenance events across the fleet</p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={maintenanceEvents} />
      </div>
    </div>
  );
}
