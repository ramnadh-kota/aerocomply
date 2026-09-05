"use client";

import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { technicians, isOnShiftNow } from "@/lib/mock/technicians";
import { workOrdersForTechnician } from "@/lib/mock/workOrders";
import type { Technician } from "@/lib/mock/types";

export default function TechniciansPage() {
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
