"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge, assetStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { SuiteGuard } from "@/components/auth/SuiteGuard";
import { useSession } from "@/lib/auth/SessionContext";
import { useEntitlements } from "@/lib/entitlements/EntitlementContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  airframesApi,
  type AirframeBattery,
  type AirframeComponent,
  type AirframeResponse,
  type AirframeUtilization,
  type MaintenanceDue,
} from "@/lib/api/airframes";
import { FAMILY_CONFIG, buildDetailPayload, detailToForm, formatHours, humanizeEnum, type AirframeFamily } from "@/lib/airframes/helpers";

const COMPONENT_TYPES: Record<AirframeFamily, string[]> = {
  helicopter: ["ROTOR", "TRANSMISSION", "ENGINE", "AVIONICS", "ACTUATOR", "HYDRAULIC", "LANDING_GEAR", "SENSOR", "OTHER"],
  evtol: ["MOTOR", "PROPELLER", "BATTERY", "FLIGHT_CONTROLLER", "AVIONICS", "ACTUATOR", "SENSOR", "OTHER"],
};

export function AirframeDetail({ family }: { family: AirframeFamily }) {
  const cfg = FAMILY_CONFIG[family];
  const api = useMemo(() => airframesApi(cfg.apiPath), [cfg.apiPath]);
  const { id } = useParams<{ id: string }>();
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const { hasFeature } = useEntitlements();
  const canHums = hasFeature("hums");
  const canBatteries = family === "evtol" && hasFeature("battery_analytics");

  const [asset, setAsset] = useState<AirframeResponse | null>(null);
  const [util, setUtil] = useState<AirframeUtilization | null>(null);
  const [components, setComponents] = useState<AirframeComponent[]>([]);
  const [due, setDue] = useState<MaintenanceDue[]>([]);
  const [batteries, setBatteries] = useState<AirframeBattery[]>([]);
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [edit, setEdit] = useState<Record<string, string>>({});
  const [compType, setCompType] = useState(COMPONENT_TYPES[family][0]);
  const [compName, setCompName] = useState("");
  const [minutes, setMinutes] = useState("");
  const [cycles, setCycles] = useState("1");
  const [battSerial, setBattSerial] = useState("");

  const load = useCallback(async () => {
    if (isDemo || !isAuthenticated || !accessToken || !id) return;
    setLoading(true);
    setError(null);
    try {
      const a = await api.get(accessToken, id);
      setAsset(a);
      setEdit(detailToForm(cfg.fields, a.detail));
      const [u, c, d] = await Promise.all([
        api.utilization(accessToken, id),
        api.components(accessToken, id),
        api.maintenanceDue(accessToken, id),
      ]);
      setUtil(u);
      setComponents(c);
      setDue(d);
      if (canBatteries) setBatteries(await api.batteries(accessToken, id));
    } catch (e) {
      setError(normalizeApiError(e));
    } finally {
      setLoading(false);
    }
  }, [accessToken, api, canBatteries, cfg.fields, id, isAuthenticated, isDemo]);

  useEffect(() => {
    void load();
  }, [load]);

  async function act<T>(fn: () => Promise<T>, done: string | ((result: T) => string)) {
    setActionError(null);
    setNotice(null);
    try {
      const result = await fn();
      setNotice(typeof done === "function" ? done(result) : done);
      await load();
    } catch (e) {
      setActionError(normalizeApiError(e).message);
    }
  }

  const saveDetails = () => {
    const { detail, errors } = buildDetailPayload(cfg.fields, edit);
    const first = Object.values(errors)[0];
    if (first) {
      setActionError(first);
      return;
    }
    void act(() => api.update(accessToken!, id, { detail }), "Details saved.");
  };

  const recordFlight = () => {
    const m = Number(minutes);
    const c = Number(cycles);
    if (!Number.isInteger(m) || m <= 0 || !Number.isInteger(c) || c <= 0) {
      setActionError("Duration (minutes) and cycles must be positive whole numbers.");
      return;
    }
    void act(
      () => api.recordFlight(accessToken!, id, { flown_at: new Date().toISOString(), duration_minutes: m, cycles: c }),
      "Flight recorded."
    );
    setMinutes("");
  };

  return (
    <SuiteGuard requiredSuite={cfg.suite}>
      <PageHeader
        breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: cfg.title, href: cfg.basePath }, { label: asset?.registration ?? "…" }]}
        title={asset?.registration ?? cfg.singular}
        subtitle={asset ? [asset.manufacturer, asset.model].filter(Boolean).join(" ") || undefined : undefined}
        actions={asset ? <StatusBadge {...assetStatusBadge(asset.status)} /> : undefined}
      />
      {isDemo ? (
        <div className="ac-card" style={{ padding: 16 }}>Available with a live organization session only.</div>
      ) : (
        <RealDataPanel loading={loading} error={error} isEmpty={!asset} emptyMessage={`${cfg.singular} not found.`}>
          {notice && <p role="status" className="ac-text-sm" style={{ color: "var(--ac-status-compliant)" }}>{notice}</p>}
          {actionError && <p role="alert" className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)" }}>{actionError}</p>}

          <div className="ac-card" style={{ padding: 16, marginBottom: 16 }}>
            <h3 className="ac-h3" style={{ marginTop: 0 }}>Utilization</h3>
            <p className="ac-text-sm" style={{ margin: 0 }}>
              {util ? `${util.total_flights} flights · ${formatHours(util.total_minutes)} · ${util.total_cycles} cycles` : "No utilization data"}
            </p>
            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              <input aria-label="Flight minutes" placeholder="Minutes" inputMode="numeric" value={minutes} onChange={(e) => setMinutes(e.target.value)} />
              <input aria-label="Cycles" placeholder="Cycles" inputMode="numeric" value={cycles} onChange={(e) => setCycles(e.target.value)} />
              <button className="ac-btn" onClick={recordFlight}>Record flight</button>
            </div>
          </div>

          <div className="ac-card" style={{ padding: 16, marginBottom: 16 }}>
            <h3 className="ac-h3" style={{ marginTop: 0 }}>Airframe details</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
              {cfg.fields.map((f) => (
                <label key={f.key} className="ac-text-sm" style={{ display: "grid", gap: 4 }}>
                  {f.label}
                  {f.kind === "enum" ? (
                    <select value={edit[f.key] ?? ""} onChange={(e) => setEdit({ ...edit, [f.key]: e.target.value })}>
                      <option value="">—</option>
                      {f.options?.map((o) => (<option key={o} value={o}>{humanizeEnum(o)}</option>))}
                    </select>
                  ) : (
                    <input inputMode="decimal" value={edit[f.key] ?? ""} onChange={(e) => setEdit({ ...edit, [f.key]: e.target.value })} />
                  )}
                </label>
              ))}
            </div>
            <button className="ac-btn" style={{ marginTop: 12 }} onClick={saveDetails}>Save details</button>
          </div>

          <div className="ac-card" style={{ padding: 16, marginBottom: 16 }}>
            <h3 className="ac-h3" style={{ marginTop: 0 }}>Components</h3>
            {components.length === 0 ? (
              <p className="ac-text-sm ac-text-muted">No components installed.</p>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {components.map((c) => (
                  <li key={c.id} className="ac-text-sm">{c.name} · {humanizeEnum(c.component_type)}{c.serial_number ? ` · S/N ${c.serial_number}` : ""}</li>
                ))}
              </ul>
            )}
            <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
              <select aria-label="Component type" value={compType} onChange={(e) => setCompType(e.target.value)}>
                {COMPONENT_TYPES[family].map((t) => (<option key={t} value={t}>{humanizeEnum(t)}</option>))}
              </select>
              <input aria-label="Component name" placeholder="Name" value={compName} onChange={(e) => setCompName(e.target.value)} />
              <button className="ac-btn" disabled={!compName.trim()} onClick={() => { void act(() => api.addComponent(accessToken!, id, { component_type: compType, name: compName.trim() }), "Component added."); setCompName(""); }}>Add component</button>
            </div>
          </div>

          {canBatteries && (
            <div className="ac-card" style={{ padding: 16, marginBottom: 16 }}>
              <h3 className="ac-h3" style={{ marginTop: 0 }}>Battery packs</h3>
              {batteries.length === 0 ? <p className="ac-text-sm ac-text-muted">No battery packs attached.</p> : (
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {batteries.map((b) => (<li key={b.id} className="ac-text-sm">{b.serial_number} · {b.status}</li>))}
                </ul>
              )}
              <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                <input aria-label="Battery serial" placeholder="Serial number" value={battSerial} onChange={(e) => setBattSerial(e.target.value)} />
                <button className="ac-btn" disabled={!battSerial.trim()} onClick={() => { void act(() => api.attachBattery(accessToken!, id, { serial_number: battSerial.trim() }), "Battery attached."); setBattSerial(""); }}>Attach</button>
              </div>
            </div>
          )}

          <div className="ac-card" style={{ padding: 16, marginBottom: 16 }}>
            <h3 className="ac-h3" style={{ marginTop: 0 }}>Maintenance due</h3>
            {due.length === 0 ? <p className="ac-text-sm ac-text-muted">Nothing due or no requirements applied.</p> : (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {due.map((d, i) => (<li key={i} className="ac-text-sm">{String(d.title ?? d.name ?? d.requirement_id ?? "Requirement")} — {String(d.due_status ?? d.status ?? "")}</li>))}
              </ul>
            )}
          </div>

          {canHums && (
            <div className="ac-card" style={{ padding: 16 }}>
              <h3 className="ac-h3" style={{ marginTop: 0 }}>HUMS sensors</h3>
              <p className="ac-text-sm ac-text-muted" style={{ marginTop: 0 }}>
                Creates the starter sensor set for this airframe. No thresholds are assumed; baselines are learned from your data.
              </p>
              <button className="ac-btn" onClick={() => void act(
                () => api.applyHumsTemplate(accessToken!, id),
                (r) => `HUMS template applied: ${r.created.length} created, ${r.skipped.length} already present.`
              )}>Apply HUMS starter template</button>
            </div>
          )}
        </RealDataPanel>
      )}
    </SuiteGuard>
  );
}
