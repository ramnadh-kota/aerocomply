"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, projectStatusBadge } from "@/components/status/StatusBadge";
import { maintenanceProjects } from "@/lib/mock/maintenanceProjects";
import { workOrdersForProject } from "@/lib/mock/workOrders";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import type { MaintenanceProject } from "@/lib/mock/types";

export default function MaintenanceProjectsPage() {
  const columns: Column<MaintenanceProject>[] = [
    { key: "title", header: "Project", render: (p) => <span className="ac-mono">{p.title}</span>, sortValue: (p) => p.title },
    {
      key: "aircraft",
      header: "Aircraft",
      render: (p) => {
        const a = getAircraftById(p.aircraftId);
        return a ? <Link href={`/aircraft/${a.id}`} className="ac-mono">{currentRegistration(a)}</Link> : p.aircraftId;
      },
    },
    { key: "type", header: "Type", render: (p) => p.projectType.replace(/_/g, " ") },
    { key: "manager", header: "Project Manager", render: (p) => p.projectManager },
    { key: "start", header: "Start Date", render: (p) => p.startDate, sortValue: (p) => p.startDate },
    { key: "target", header: "Target Completion", render: (p) => p.targetCompletionDate, sortValue: (p) => p.targetCompletionDate },
    {
      key: "progress",
      header: "Progress",
      render: (p) => (
        <div className="ac-flex ac-items-center ac-gap-2">
          <div style={{ width: 80, height: 6, borderRadius: 4, background: "var(--ac-border)", overflow: "hidden" }}>
            <div style={{ width: `${p.progressPercent}%`, height: "100%", background: "var(--ac-accent)" }} />
          </div>
          <span className="ac-text-sm">{p.progressPercent}%</span>
        </div>
      ),
      sortValue: (p) => p.progressPercent,
    },
    { key: "workOrders", header: "Work Orders", render: (p) => workOrdersForProject(p.id).length },
    { key: "status", header: "Status", render: (p) => <StatusBadge {...projectStatusBadge(p.status)} /> },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance" }, { label: "Projects" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Maintenance Projects</h1>
          <p className="ac-subtitle">{maintenanceProjects.length} projects · compliance-connected via linked work orders</p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={maintenanceProjects} getRowHref={(p) => `/maintenance/projects/${p.id}`} />
      </div>
    </div>
  );
}
