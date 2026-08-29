"use client";

import { useMemo, useState } from "react";
import { notFound } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { Timeline, type TimelineEntry } from "@/components/timeline/Timeline";
import {
  getAircraftById,
  getAircraftVariant,
  currentRegistration,
} from "@/lib/mock/aircraft";
import { installationsForAircraft as engineHistoryForAircraft, getEngineById, getEngineType, engineAsOf } from "@/lib/mock/engines";
import { componentInstallationsForAircraft, componentForInstance } from "@/lib/mock/components";

function fmt(date: string): string {
  return new Date(date).toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
}

export default function ConfigurationTimelinePage({ params }: { params: { id: string } }) {
  const aircraft = getAircraftById(params.id);
  if (!aircraft) notFound();

  const variant = getAircraftVariant(aircraft.aircraftVariantId)!;
  const registration = currentRegistration(aircraft);
  const engineHistory = engineHistoryForAircraft(aircraft.id);
  const componentHistory = componentInstallationsForAircraft(aircraft.id).sort((a, b) => a.installedAt.localeCompare(b.installedAt));

  const [asOfDate, setAsOfDate] = useState<string>("2026-03-12");

  const positions = useMemo(() => Array.from(new Set(engineHistory.map((e) => e.position))), [engineHistory]);

  const events: TimelineEntry[] = useMemo(() => {
    const entries: TimelineEntry[] = [
      { id: "eis", date: fmt(aircraft.entryIntoServiceDate), title: "Aircraft entered service", accent: "default" },
    ];
    for (const reg of aircraft.registrationHistory) {
      if (reg.effectiveFrom !== aircraft.entryIntoServiceDate) {
        entries.push({ id: `reg-${reg.id}`, date: fmt(reg.effectiveFrom), title: `Re-registered as ${reg.registrationMark}`, accent: "default" });
      }
    }
    for (const ei of engineHistory) {
      const engine = getEngineById(ei.engineId)!;
      const type = getEngineType(engine.engineTypeId)!;
      entries.push({
        id: `ei-install-${ei.id}`,
        date: fmt(ei.installedAt),
        title: `${ei.position.replace("_", " ")} ${type.modelDesignation} ${engine.serialNumber} installed`,
      });
      if (ei.removedAt) {
        entries.push({ id: `ei-remove-${ei.id}`, date: fmt(ei.removedAt), title: `${ei.position.replace("_", " ")} removed` });
      }
    }
    for (const ci of componentHistory) {
      const component = componentForInstance(ci.componentInstanceId);
      entries.push({
        id: `ci-install-${ci.id}`,
        date: fmt(ci.installedAt),
        title: `${component?.description ?? "Component"} ${component?.partNumber ?? ""} installed`,
        detail: `Position ${ci.position}`,
      });
      if (ci.removedAt) {
        entries.push({ id: `ci-remove-${ci.id}`, date: fmt(ci.removedAt), title: `${component?.partNumber ?? "Component"} removed`, detail: `Position ${ci.position}` });
      }
    }
    entries.sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
    entries.push({ id: "now", date: "Present", title: "Current configuration", accent: "highlight" });
    return entries;
  }, [aircraft, engineHistory, componentHistory]);

  const snapshotEngines = positions.map((pos) => {
    const install = engineAsOf(aircraft.id, pos, asOfDate);
    if (!install) return { position: pos, label: "No engine on record for this date" };
    const engine = getEngineById(install.engineId)!;
    const type = getEngineType(engine.engineTypeId)!;
    return { position: pos, label: `${type.modelDesignation} ${engine.serialNumber}` };
  });

  const snapshotComponents = componentHistory.filter((ci) => ci.installedAt <= asOfDate && (ci.removedAt === null || ci.removedAt > asOfDate));

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Aircraft", href: "/aircraft" },
          { label: registration, href: `/aircraft/${aircraft.id}` },
          { label: "Configuration" },
        ]}
      />

      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Configuration Timeline</h1>
          <p className="ac-subtitle">
            {registration} · {variant.modelDesignation} · MSN {aircraft.msn}
          </p>
        </div>
      </div>

      <div className="ac-grid-2">
        <section>
          <h2 className="ac-h2" style={{ marginBottom: 12 }}>Configuration History</h2>
          <div className="ac-card">
            <Timeline entries={events} />
          </div>
        </section>

        <section>
          <h2 className="ac-h2" style={{ marginBottom: 12 }}>As-Of Reconstruction</h2>
          <div className="ac-card">
            <label className="ac-flex ac-items-center ac-gap-3" style={{ marginBottom: 16 }}>
              <span className="ac-text-sm ac-text-secondary">As of:</span>
              <input
                type="date"
                className="ac-input"
                style={{ maxWidth: 200 }}
                value={asOfDate}
                min={aircraft.entryIntoServiceDate}
                max="2026-03-12"
                onChange={(e) => setAsOfDate(e.target.value)}
                aria-label="Reconstruct configuration as of date"
              />
            </label>

            <p className="ac-eyebrow" style={{ marginBottom: 8 }}>
              Configuration Snapshot — {fmt(asOfDate)}
            </p>

            <div className="ac-flex ac-flex-col ac-gap-2" style={{ fontSize: 13 }}>
              <div>
                <span className="ac-text-muted">Aircraft: </span>
                {variant.modelDesignation} · MSN {aircraft.msn}
              </div>
              {snapshotEngines.map((s) => (
                <div key={s.position}>
                  <span className="ac-text-muted">{s.position.replace("_", " ")}: </span>
                  {s.label}
                </div>
              ))}
              {snapshotComponents.map((ci) => {
                const component = componentForInstance(ci.componentInstanceId);
                return (
                  <div key={ci.id}>
                    <span className="ac-text-muted">Component ({ci.position}): </span>
                    {component?.partNumber} — {ci.componentInstanceId}
                  </div>
                );
              })}
            </div>

            <hr className="ac-divider" />
            <p className="ac-text-sm" style={{ color: "var(--ac-text-muted)" }}>
              This snapshot is reconstructed live from installation-interval history — it is not a
              stored "current state" record. Reconstruction logic is illustrative for this
              prototype (see <span className="ac-mono">docs/ontology/TEMPORAL_MODEL.md</span>).
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
