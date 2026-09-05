"use client";

import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { engines, engineInstallations, getEngineType, currentAircraftForEngine } from "@/lib/mock/engines";
import { getAircraftById, currentRegistration } from "@/lib/mock/aircraft";
import { assessmentsForEngine } from "@/lib/mock/assessments";
import type { Engine } from "@/lib/mock/types";

interface Row {
  engine: Engine;
  typeLabel: string;
  manufacturer: string;
  aircraftLabel: string;
  aircraftHref: string | null;
  position: string;
  installedSince: string;
  isCurrent: boolean;
  assessmentCount: number;
}

function buildRows(): Row[] {
  return engines.map((e) => {
    const install = engineInstallations.find((i) => i.engineId === e.id && i.removedAt === null) ?? engineInstallations.find((i) => i.engineId === e.id);
    const type = getEngineType(e.engineTypeId)!;
    const aircraftId = currentAircraftForEngine(e.id);
    const aircraft = aircraftId ? getAircraftById(aircraftId) : undefined;
    return {
      engine: e,
      typeLabel: type.modelDesignation,
      manufacturer: type.manufacturer,
      aircraftLabel: aircraft ? currentRegistration(aircraft) : "Not installed",
      aircraftHref: aircraft ? `/aircraft/${aircraft.id}` : null,
      position: install?.position ?? "—",
      installedSince: install?.installedAt ?? "—",
      isCurrent: install?.removedAt === null,
      assessmentCount: assessmentsForEngine(e.id).length,
    };
  });
}

export default function EnginesListPage() {
  const rows = buildRows();

  const columns: Column<Row>[] = [
    { key: "sn", header: "Engine Serial Number", render: (r) => <span className="ac-mono">{r.engine.serialNumber}</span>, sortValue: (r) => r.engine.serialNumber },
    { key: "type", header: "Engine Type", render: (r) => r.typeLabel, sortValue: (r) => r.typeLabel },
    { key: "manufacturer", header: "Manufacturer", render: (r) => r.manufacturer },
    {
      key: "aircraft",
      header: "Aircraft",
      render: (r) => (r.aircraftHref ? <Link href={r.aircraftHref} className="ac-mono">{r.aircraftLabel}</Link> : <span className="ac-text-muted">{r.aircraftLabel}</span>),
    },
    { key: "position", header: "Position", render: (r) => r.position.replace("_", " ") },
    { key: "since", header: "Installed Since", render: (r) => r.installedSince, sortValue: (r) => r.installedSince },
    { key: "status", header: "Status", render: (r) => <StatusBadge status={r.isCurrent ? "ACTIVE" : "STORED"} label={r.isCurrent ? "Installed" : "Removed"} /> },
    { key: "assessments", header: "Assessments", render: (r) => r.assessmentCount },
  ];

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Engines" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Engine Fleet</h1>
          <p className="ac-subtitle">{rows.length} engines tracked · Engine is a first-class assessment subject, not merely a component</p>
        </div>
      </div>
      <div className="ac-card" style={{ padding: 0 }}>
        <DataTable columns={columns} rows={rows} getRowHref={(r) => `/engines/${r.engine.id}`} />
      </div>
    </div>
  );
}
