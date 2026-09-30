"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge, assetStatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { SuiteGuard } from "@/components/auth/SuiteGuard";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { airframesApi, type AirframeResponse } from "@/lib/api/airframes";
import { FAMILY_CONFIG, buildDetailPayload, humanizeEnum, type AirframeFamily } from "@/lib/airframes/helpers";

export function AirframeFleet({ family }: { family: AirframeFamily }) {
  const cfg = FAMILY_CONFIG[family];
  const api = useMemo(() => airframesApi(cfg.apiPath), [cfg.apiPath]);
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [rows, setRows] = useState<AirframeResponse[]>([]);
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [registration, setRegistration] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [model, setModel] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    if (isDemo || !isAuthenticated || !accessToken) return;
    setLoading(true);
    setError(null);
    try {
      setRows(await api.list(accessToken));
    } catch (e) {
      setError(normalizeApiError(e));
    } finally {
      setLoading(false);
    }
  }, [accessToken, api, isAuthenticated, isDemo]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create() {
    if (!accessToken) return;
    const { detail, errors } = buildDetailPayload(cfg.fields, values);
    const firstError = Object.values(errors)[0];
    if (firstError) {
      setFormError(firstError);
      return;
    }
    setCreating(true);
    setFormError(null);
    try {
      await api.create(accessToken, {
        registration: registration.trim(),
        manufacturer: manufacturer.trim() || null,
        model: model.trim() || null,
        detail,
      });
      setRegistration("");
      setManufacturer("");
      setModel("");
      setValues({});
      await load();
    } catch (e) {
      setFormError(normalizeApiError(e).message);
    } finally {
      setCreating(false);
    }
  }

  return (
    <SuiteGuard requiredSuite={cfg.suite}>
      <PageHeader
        breadcrumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: cfg.title }]}
        title={`${cfg.title} Fleet`}
        subtitle={`Registered ${cfg.singular.toLowerCase()} airframes with utilization, components, maintenance and HUMS setup.`}
      />
      {isDemo ? (
        <div className="ac-card" style={{ padding: 16 }}>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            {cfg.title} fleet management is available with a live organization session only.
          </p>
        </div>
      ) : (
        <>
          <div className="ac-card" style={{ padding: 16, marginBottom: 16 }}>
            <h3 className="ac-h3" style={{ marginTop: 0 }}>Register {cfg.singular}</h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
              <input aria-label="Registration" placeholder="Registration *" maxLength={16} value={registration} onChange={(e) => setRegistration(e.target.value)} />
              <input aria-label="Manufacturer" placeholder="Manufacturer" value={manufacturer} onChange={(e) => setManufacturer(e.target.value)} />
              <input aria-label="Model" placeholder="Model" value={model} onChange={(e) => setModel(e.target.value)} />
              {cfg.fields.map((f) =>
                f.kind === "enum" ? (
                  <select key={f.key} aria-label={f.label} value={values[f.key] ?? ""} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}>
                    <option value="">{f.label} (select)</option>
                    {f.options?.map((o) => (
                      <option key={o} value={o}>{humanizeEnum(o)}</option>
                    ))}
                  </select>
                ) : (
                  <input key={f.key} aria-label={f.label} placeholder={f.label} inputMode="decimal" value={values[f.key] ?? ""} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
                )
              )}
            </div>
            <div style={{ marginTop: 12 }}>
              <button className="ac-btn" onClick={create} disabled={creating || !registration.trim()}>
                {creating ? "Creating…" : `Create ${cfg.singular}`}
              </button>
              {formError && (
                <p role="alert" className="ac-text-sm" style={{ color: "var(--ac-status-non-compliant)", margin: "8px 0 0" }}>{formError}</p>
              )}
            </div>
          </div>

          <RealDataPanel loading={loading} error={error} isEmpty={rows.length === 0} emptyMessage={`No ${cfg.title.toLowerCase()} registered yet.`}>
            <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
              <table className="ac-table" style={{ width: "100%" }}>
                <thead>
                  <tr>
                    <th>Registration</th>
                    <th>Manufacturer / Model</th>
                    <th>Status</th>
                    {cfg.fields.slice(0, 2).map((f) => (<th key={f.key}>{f.label}</th>))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id}>
                      <td><Link href={`${cfg.basePath}/${r.id}`} className="ac-link" style={{ fontWeight: 600 }}>{r.registration}</Link></td>
                      <td>{[r.manufacturer, r.model].filter(Boolean).join(" ") || "—"}</td>
                      <td><StatusBadge {...assetStatusBadge(r.status)} /></td>
                      {cfg.fields.slice(0, 2).map((f) => (
                        <td key={f.key}>{f.kind === "enum" ? humanizeEnum(String(r.detail?.[f.key] ?? "")) : (r.detail?.[f.key] ?? "—")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </RealDataPanel>
        </>
      )}
    </SuiteGuard>
  );
}
