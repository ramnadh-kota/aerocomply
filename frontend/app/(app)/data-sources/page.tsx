"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  dataSourcesApi,
  type AcquisitionReport,
  type DataSource,
  type SourceHealth,
} from "@/lib/api/dataSources";
import {
  CONNECTOR_LABELS,
  HEALTH_BADGE,
  acceptanceRate,
  canDelete,
  canIngest,
  formatAge,
  formatLatency,
  lifecycleActions,
  parseConnectionConfig,
} from "@/lib/data-sources/helpers";

const CONNECTOR_TYPES = Object.keys(CONNECTOR_LABELS);

const CONFIG_HINTS: Record<string, string> = {
  MAVLINK: '{"system_id_map": {"1": "<asset id>"}, "expected_interval_seconds": 10}',
  MQTT: '{"topic_filter": "kota/telemetry/#", "expected_interval_seconds": 30}',
  CSV_BATCH: "{}",
  JSON_BATCH: "{}",
  GENERIC_WEBHOOK: "{}",
};

function healthBadge(status: keyof typeof HEALTH_BADGE) {
  const b = HEALTH_BADGE[status] ?? HEALTH_BADGE.INACTIVE;
  return <StatusBadge status={b.kind} label={b.label} />;
}

export default function DataSourcesPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [sources, setSources] = useState<DataSource[]>([]);
  const [healthById, setHealthById] = useState<Record<string, SourceHealth>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // create form
  const [name, setName] = useState("");
  const [connectorType, setConnectorType] = useState("MAVLINK");
  const [description, setDescription] = useState("");
  const [configText, setConfigText] = useState("");
  const [secretRef, setSecretRef] = useState("");

  // ingest panel
  const [payload, setPayload] = useState("");
  const [topic, setTopic] = useState("");
  const [report, setReport] = useState<AcquisitionReport | null>(null);

  const load = useCallback(async () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await dataSourcesApi.list(accessToken);
      setSources(list.items);
      const entries = await Promise.all(
        list.items.map(async (s) => {
          try {
            return [s.id, await dataSourcesApi.health(accessToken, s.id)] as const;
          } catch {
            return null; // a single failing health lookup must not hide the list
          }
        })
      );
      setHealthById(Object.fromEntries(entries.filter((e): e is [string, SourceHealth] => e !== null)));
    } catch (err) {
      setError(normalizeApiError(err));
    } finally {
      setLoading(false);
    }
  }, [accessToken, isAuthenticated]);

  useEffect(() => {
    if (isDemo) return; // demo mode has no backend; the page renders an explanatory card
    void load();
  }, [isDemo, load]);

  const selected = useMemo(() => sources.find((s) => s.id === selectedId) ?? null, [sources, selectedId]);
  const selectedHealth = selected ? healthById[selected.id] : undefined;

  const run = useCallback(
    async (fn: () => Promise<unknown>) => {
      setBusy(true);
      setActionError(null);
      try {
        await fn();
        await load();
      } catch (err) {
        setActionError(normalizeApiError(err).message);
      } finally {
        setBusy(false);
      }
    },
    [load]
  );

  const onCreate = (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = parseConnectionConfig(configText);
    if (!parsed.ok) {
      setActionError(parsed.error);
      return;
    }
    if (!accessToken) return;
    void run(async () => {
      const created = await dataSourcesApi.create(accessToken, {
        name: name.trim(),
        connector_type: connectorType,
        description: description.trim() || null,
        connection_config: parsed.value,
        secret_reference: secretRef.trim() || null,
      });
      setName("");
      setDescription("");
      setConfigText("");
      setSecretRef("");
      setSelectedId(created.id);
    });
  };

  const onSend = (body: BodyInit) => {
    if (!accessToken || !selected) return;
    setReport(null);
    void run(async () => {
      setReport(await dataSourcesApi.ingest(accessToken, selected.id, body, topic.trim() || undefined));
    });
  };

  if (isDemo) {
    return (
      <div>
        <PageHeader eyebrow="ACQUISITION" title="Data Sources" />
        <div className="ac-card" style={{ padding: 24 }}>
          <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
            Data sources are configured against a live organization. Sign in to a real organization to manage them;
            demo mode has no backend to receive data.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Assets", href: "/assets" }, { label: "Data Sources" }]}
        eyebrow="ACQUISITION"
        title="Data Sources"
        subtitle="Connect aircraft and drone telemetry. Health below is derived from real ingestion evidence — never assumed."
      />

      {actionError && (
        <div className="ac-card" role="alert" style={{ padding: 12, marginBottom: 12, borderLeft: "3px solid var(--ac-danger, #c0392b)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>{actionError}</p>
        </div>
      )}

      <RealDataPanel
        loading={loading}
        error={error}
        isEmpty={sources.length === 0}
        emptyMessage="No data sources yet. Register one below, activate it, then send data."
      >
        <div className="ac-card" style={{ padding: 0, overflowX: "auto", marginBottom: 20 }}>
          <table className="ac-table" style={{ width: "100%" }}>
            <thead>
              <tr>
                <th>Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Health</th>
                <th>Last data</th>
                <th style={{ textAlign: "right" }}>Accepted</th>
                <th style={{ textAlign: "right" }}>Rejected</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => {
                const h = healthById[s.id];
                return (
                  <tr key={s.id} style={{ background: s.id === selectedId ? "var(--ac-surface-2)" : undefined }}>
                    <td>
                      <button type="button" className="ac-link" onClick={() => { setSelectedId(s.id); setReport(null); }}>
                        {s.name}
                      </button>
                    </td>
                    <td>{CONNECTOR_LABELS[s.connector_type] ?? s.connector_type}</td>
                    <td>{s.status}</td>
                    <td>{h ? healthBadge(h.status) : "—"}</td>
                    <td>{formatAge(h?.last_success_at ?? s.last_acquisition_at)}</td>
                    <td style={{ textAlign: "right" }}>{s.total_events_ingested}</td>
                    <td style={{ textAlign: "right" }}>{s.total_events_rejected}</td>
                    <td>
                      <div className="ac-flex ac-gap-2" style={{ justifyContent: "flex-end" }}>
                        {lifecycleActions(s.status).map((a) => (
                          <button
                            key={a.to}
                            type="button"
                            className="ac-btn"
                            disabled={busy}
                            onClick={() => accessToken && void run(() => dataSourcesApi.update(accessToken, s.id, { status: a.to }))}
                          >
                            {a.label}
                          </button>
                        ))}
                        {canDelete(s.status) && (
                          <button
                            type="button"
                            className="ac-btn"
                            disabled={busy}
                            onClick={() => {
                              if (accessToken && window.confirm(`Delete data source "${s.name}"?`)) {
                                void run(() => dataSourcesApi.remove(accessToken, s.id));
                                if (selectedId === s.id) setSelectedId(null);
                              }
                            }}
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </RealDataPanel>

      {selected && (
        <div className="ac-card" style={{ padding: 16, marginBottom: 20 }} aria-label={`Details for ${selected.name}`}>
          <h2 className="ac-h2" style={{ marginTop: 0 }}>{selected.name}</h2>
          {selectedHealth ? (
            <>
              <p className="ac-text-sm" style={{ marginTop: 0 }}>
                {healthBadge(selectedHealth.status)} <span className="ac-text-muted">{selectedHealth.reason}</span>
              </p>
              <dl className="ac-grid" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
                <div><dt className="ac-text-muted">Last seen</dt><dd>{formatAge(selectedHealth.last_seen_at)}</dd></div>
                <div><dt className="ac-text-muted">Last success</dt><dd>{formatAge(selectedHealth.last_success_at)}</dd></div>
                <div><dt className="ac-text-muted">Last failure</dt><dd>{formatAge(selectedHealth.last_failure_at)}</dd></div>
                <div><dt className="ac-text-muted">Events accepted</dt><dd>{selectedHealth.event_count}</dd></div>
                <div><dt className="ac-text-muted">Rejected / errors</dt><dd>{selectedHealth.error_count}</dd></div>
                <div><dt className="ac-text-muted">Duplicates</dt><dd>{selectedHealth.duplicate_count}</dd></div>
                <div><dt className="ac-text-muted">Quarantined</dt><dd>{selectedHealth.quarantined_count}</dd></div>
                <div><dt className="ac-text-muted">Packets lost</dt><dd>{selectedHealth.loss_count}</dd></div>
                <div><dt className="ac-text-muted">Avg latency</dt><dd>{formatLatency(selectedHealth.latency_ms)}</dd></div>
                <div>
                  <dt className="ac-text-muted">Acceptance</dt>
                  <dd>
                    {(() => {
                      const r = acceptanceRate(selectedHealth);
                      return r === null ? "no data yet" : `${Math.round(r * 100)}%`;
                    })()}
                  </dd>
                </div>
              </dl>
              {selectedHealth.last_error && (
                <p className="ac-text-sm" style={{ marginBottom: 0 }}>Last error: {selectedHealth.last_error}</p>
              )}
            </>
          ) : (
            <p className="ac-text-sm ac-text-muted">Health evidence is unavailable.</p>
          )}

          {canIngest(selected) ? (
            <div style={{ marginTop: 16 }}>
              <h3 className="ac-h3">Send data</h3>
              {(selected.connector_type === "CSV_BATCH" || selected.connector_type === "JSON_BATCH") && (
                <input
                  type="file"
                  aria-label="File to ingest"
                  accept={selected.connector_type === "CSV_BATCH" ? ".csv,text/csv" : ".json,application/json"}
                  disabled={busy}
                  onChange={(e) => {
                    const f = e.target.files?.[0];
                    if (f) onSend(f);
                    e.target.value = "";
                  }}
                />
              )}
              {selected.connector_type === "MQTT" && (
                <input
                  className="ac-input"
                  placeholder="MQTT topic (e.g. kota/telemetry/DRONE-1)"
                  value={topic}
                  onChange={(e) => setTopic(e.target.value)}
                  style={{ display: "block", marginBottom: 8, width: "100%" }}
                />
              )}
              {(selected.connector_type === "MQTT" || selected.connector_type === "GENERIC_WEBHOOK") && (
                <>
                  <textarea
                    className="ac-input"
                    rows={4}
                    placeholder="JSON payload"
                    value={payload}
                    onChange={(e) => setPayload(e.target.value)}
                    style={{ width: "100%", fontFamily: "monospace" }}
                  />
                  <button type="button" className="ac-btn ac-btn-primary" disabled={busy || !payload.trim()} onClick={() => onSend(payload)}>
                    Send payload
                  </button>
                </>
              )}
              {selected.connector_type === "MAVLINK" && (
                <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
                  MAVLink frames are delivered by your gateway to <code>POST /api/v1/data-sources/{selected.id}/ingest</code>{" "}
                  (raw bytes). Map each vehicle&apos;s system id to an asset with <code>system_id_map</code> in the connection config.
                </p>
              )}
              {report && (
                <div className="ac-card" role="status" style={{ marginTop: 12, padding: 12 }}>
                  <p className="ac-text-sm" style={{ margin: 0 }}>
                    Received {report.received}: accepted {report.accepted}, duplicates {report.duplicates}, quarantined{" "}
                    {report.quarantined}, rejected {report.rejected}, failed {report.failed}
                    {report.packets_lost ? `, packets lost ${report.packets_lost}` : ""}.
                  </p>
                  {[...report.errors, ...report.warnings].slice(0, 5).map((m, i) => (
                    <p key={i} className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>{m}</p>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="ac-text-sm ac-text-muted" style={{ marginBottom: 0 }}>
              {selected.status !== "ACTIVE"
                ? "Activate this source to accept data."
                : "This connector type does not accept pushed data through this page."}
            </p>
          )}
        </div>
      )}

      <form className="ac-card" style={{ padding: 16 }} onSubmit={onCreate}>
        <h2 className="ac-h2" style={{ marginTop: 0 }}>Register a data source</h2>
        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))" }}>
          <label>
            <span className="ac-text-sm">Name</span>
            <input className="ac-input" required maxLength={128} value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%" }} />
          </label>
          <label>
            <span className="ac-text-sm">Connector</span>
            <select className="ac-input" value={connectorType} onChange={(e) => setConnectorType(e.target.value)} style={{ width: "100%" }}>
              {CONNECTOR_TYPES.map((t) => (
                <option key={t} value={t}>{CONNECTOR_LABELS[t]}</option>
              ))}
            </select>
          </label>
          <label>
            <span className="ac-text-sm">Secret reference (credentials live in the secrets store)</span>
            <input className="ac-input" maxLength={255} value={secretRef} onChange={(e) => setSecretRef(e.target.value)} style={{ width: "100%" }} />
          </label>
        </div>
        <label style={{ display: "block", marginTop: 10 }}>
          <span className="ac-text-sm">Description</span>
          <input className="ac-input" maxLength={512} value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: "100%" }} />
        </label>
        <label style={{ display: "block", marginTop: 10 }}>
          <span className="ac-text-sm">Connection config (JSON)</span>
          <textarea
            className="ac-input"
            rows={3}
            placeholder={CONFIG_HINTS[connectorType] ?? "{}"}
            value={configText}
            onChange={(e) => setConfigText(e.target.value)}
            style={{ width: "100%", fontFamily: "monospace" }}
          />
        </label>
        <div style={{ marginTop: 12 }}>
          <button type="submit" className="ac-btn ac-btn-primary" disabled={busy || !name.trim()}>
            Register
          </button>
        </div>
      </form>
    </div>
  );
}
