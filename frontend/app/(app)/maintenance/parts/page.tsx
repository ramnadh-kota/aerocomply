"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, partStatusBadge } from "@/components/status/StatusBadge";
import { parts } from "@/lib/mock/parts";
import { getWorkOrderById } from "@/lib/mock/workOrders";
import { useMroState } from "@/lib/mro-state/MroStateContext";
import type { Part } from "@/lib/mock/types";

export default function PartsInventoryPage() {
  const { submissions } = useMroState();
  const columns: Column<Part>[] = [
    { key: "pn", header: "Part Number", render: (p) => <span className="ac-mono">{p.partNumber}</span>, sortValue: (p) => p.partNumber },
    { key: "desc", header: "Description", render: (p) => p.description },
    { key: "qty", header: "Quantity", render: (p) => p.quantity, sortValue: (p) => p.quantity },
    { key: "status", header: "Status", render: (p) => <StatusBadge {...partStatusBadge(p.status)} /> },
    {
      key: "workOrder",
      header: "Work Order",
      render: (p) => {
        const wo = p.workOrderId ? getWorkOrderById(p.workOrderId) : undefined;
        if (!wo) return "—";
        const record = submissions[wo.id];
        return (
          <span className="ac-flex ac-items-center ac-gap-2">
            <Link href={`/maintenance/work-orders/${wo.id}`} className="ac-mono">{wo.workOrderNumber}</Link>
            {record && <span className="ac-text-sm ac-text-muted">({record.submissionStatus === "SUBMITTED" ? "submitted" : "in progress"})</span>}
          </span>
        );
      },
    },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Maintenance", href: "/maintenance/projects" }, { label: "Parts & Inventory" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Parts &amp; Inventory</h1>
          <p className="ac-subtitle">{parts.length} parts tracked in support of active work orders</p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={parts} />
      </div>
    </div>
  );
}
