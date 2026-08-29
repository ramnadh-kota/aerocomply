"use client";

import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge, partStatusBadge } from "@/components/status/StatusBadge";
import { parts } from "@/lib/mock/parts";
import type { Part } from "@/lib/mock/types";

export default function PartsInventoryPage() {
  const columns: Column<Part>[] = [
    { key: "pn", header: "Part Number", render: (p) => <span className="ac-mono">{p.partNumber}</span>, sortValue: (p) => p.partNumber },
    { key: "desc", header: "Description", render: (p) => p.description },
    { key: "qty", header: "Quantity", render: (p) => p.quantity, sortValue: (p) => p.quantity },
    { key: "status", header: "Status", render: (p) => <StatusBadge {...partStatusBadge(p.status)} /> },
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
