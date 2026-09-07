"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { componentInstances, componentInstallations, componentForInstance } from "@/lib/mock/components";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { getEngineById } from "@/lib/mock/engines";
import type { ComponentInstance } from "@/lib/mock/types";

interface Row {
  instance: ComponentInstance;
  partNumber: string;
  description: string;
  parentLabel: string;
  parentHref: string | null;
  position: string;
  installedAt: string;
  removedAt: string | null;
}

function buildRows(): Row[] {
  return componentInstances.map((ci) => {
    const component = componentForInstance(ci.id);
    const install = componentInstallations.find((i) => i.componentInstanceId === ci.id && i.removedAt === null) ?? componentInstallations.find((i) => i.componentInstanceId === ci.id);
    let parentLabel = "Not installed";
    let parentHref: string | null = null;
    if (install?.parentAssetType === "AIRCRAFT" && install.aircraftParentId) {
      const a = getAircraftById(install.aircraftParentId);
      if (a) {
        parentLabel = currentRegistration(a);
        parentHref = `/aircraft/${a.id}`;
      }
    } else if (install?.parentAssetType === "ENGINE" && install.engineParentId) {
      const e = getEngineById(install.engineParentId);
      if (e) {
        parentLabel = e.serialNumber;
        parentHref = `/engines/${e.id}`;
      }
    }
    return {
      instance: ci,
      partNumber: component?.partNumber ?? "—",
      description: component?.description ?? "—",
      parentLabel,
      parentHref,
      position: install?.position ?? "—",
      installedAt: install?.installedAt ?? "—",
      removedAt: install?.removedAt ?? null,
    };
  });
}

export default function ComponentsListPage() {
  const rows = buildRows();

  const columns: Column<Row>[] = [
    { key: "pn", header: "Part Number", render: (r) => <span className="ac-mono">{r.partNumber}</span>, sortValue: (r) => r.partNumber },
    { key: "desc", header: "Component Type", render: (r) => r.description, sortValue: (r) => r.description },
    { key: "sn", header: "Serial Number", render: (r) => <span className="ac-mono">{r.instance.serialNumber}</span>, sortValue: (r) => r.instance.serialNumber },
    { key: "parent", header: "Aircraft / Engine", render: (r) => (r.parentHref ? <Link href={r.parentHref} className="ac-mono">{r.parentLabel}</Link> : <span className="ac-text-muted">{r.parentLabel}</span>) },
    { key: "position", header: "Position", render: (r) => r.position },
    { key: "installed", header: "Installation Date", render: (r) => r.installedAt, sortValue: (r) => r.installedAt },
    { key: "removed", header: "Removal Date", render: (r) => r.removedAt ?? "—" },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.removedAt ? "STORED" : "ACTIVE"} label={r.removedAt ? "Removed" : "Installed"} /> },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Components" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Components</h1>
          <p className="ac-subtitle">Serialized component instances tracked for compliance configuration context — not a parts inventory system</p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={rows} getRowHref={(r) => `/components/${r.instance.id}`} />
      </div>
    </div>
  );
}
