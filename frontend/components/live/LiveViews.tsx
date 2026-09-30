"use client";

// Generic, data-driven list and detail views for modules whose backend API exists but whose original page only
// contained sample data. Real (non-demo) sessions render these; Demo sessions keep the sample-data page (withLive).

import { useCallback, useEffect, useState, type ComponentType, type ReactNode } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { humanizeKey, scalarEntries, formatScalar } from "@/lib/live/format";

export interface LiveColumn<T> {
  header: string;
  render: (row: T) => ReactNode;
}

/** Picks the live component for real sessions and the sample-data component for Demo sessions. */
export function withLive<P extends object>(Demo: ComponentType<P>, Live: ComponentType<P>): ComponentType<P> {
  return function LivePicker(props: P) {
    const { isDemo } = useSession();
    return isDemo ? <Demo {...props} /> : <Live {...props} />;
  };
}

interface ListProps<T extends { id: string }> {
  title: string;
  subtitle?: string;
  breadcrumbs: { label: string; href?: string }[];
  load: (accessToken: string) => Promise<T[] | { items: T[] }>;
  columns: LiveColumn<T>[];
  rowHref?: (row: T) => string;
  emptyMessage: string;
  searchText?: (row: T) => string;
}

export function LiveList<T extends { id: string }>({ title, subtitle, breadcrumbs, load, columns, rowHref, emptyMessage, searchText }: ListProps<T>) {
  const { accessToken, isAuthenticated } = useSession();
  const [rows, setRows] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);
  const [q, setQ] = useState("");

  const refresh = useCallback(async () => {
    if (!isAuthenticated || !accessToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await load(accessToken);
      setRows(Array.isArray(res) ? res : res.items);
    } catch (e) {
      setError(normalizeApiError(e));
    } finally {
      setLoading(false);
    }
  }, [accessToken, isAuthenticated, load]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const shown = q.trim() && searchText ? rows.filter((r) => searchText(r).toLowerCase().includes(q.trim().toLowerCase())) : rows;

  return (
    <div>
      <PageHeader breadcrumbs={breadcrumbs} title={title} subtitle={subtitle} />
      <RealDataPanel loading={loading} error={error} isEmpty={rows.length === 0} emptyMessage={emptyMessage}>
        {searchText && (
          <input aria-label="Filter" placeholder="Filter…" value={q} onChange={(e) => setQ(e.target.value)} style={{ marginBottom: 12, maxWidth: 320 }} />
        )}
        <div className="ac-card" style={{ padding: 0, overflowX: "auto" }}>
          <table className="ac-table" style={{ width: "100%" }}>
            <thead>
              <tr>{columns.map((c) => (<th key={c.header}>{c.header}</th>))}</tr>
            </thead>
            <tbody>
              {shown.map((row) => (
                <tr key={row.id}>
                  {columns.map((c, ci) => (
                    <td key={c.header}>
                      {ci === 0 && rowHref ? <Link href={rowHref(row)} className="ac-link" style={{ fontWeight: 600 }}>{c.render(row)}</Link> : c.render(row)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length === 0 && <p className="ac-text-sm ac-text-muted" style={{ padding: 16, margin: 0 }}>No matching records.</p>}
        </div>
      </RealDataPanel>
    </div>
  );
}

interface DetailProps<T extends object> {
  breadcrumbs: (item: T | null) => { label: string; href?: string }[];
  title: (item: T) => string;
  load: (accessToken: string, id: string) => Promise<T>;
  notFound: string;
  extra?: (item: T) => ReactNode;
}

export function LiveDetail<T extends object>({ breadcrumbs, title, load, notFound, extra }: DetailProps<T>) {
  const { id } = useParams<{ id: string }>();
  const { accessToken, isAuthenticated } = useSession();
  const [item, setItem] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    if (!isAuthenticated || !accessToken || !id) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    load(accessToken, id)
      .then((r) => { if (!cancelled) setItem(r); })
      .catch((e) => { if (!cancelled) setError(normalizeApiError(e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [accessToken, id, isAuthenticated, load]);

  return (
    <div>
      <PageHeader breadcrumbs={breadcrumbs(item)} title={item ? title(item) : "…"} />
      <RealDataPanel loading={loading} error={error} isEmpty={!item} emptyMessage={notFound}>
        {item && (
          <>
            <div className="ac-card" style={{ padding: 16, marginBottom: 16 }}>
              <dl style={{ display: "grid", gridTemplateColumns: "minmax(140px, 220px) 1fr", gap: "8px 16px", margin: 0 }}>
                {scalarEntries(item as Record<string, unknown>).map(([k, v]) => (
                  <div key={k} style={{ display: "contents" }}>
                    <dt className="ac-text-sm ac-text-muted">{humanizeKey(k)}</dt>
                    <dd style={{ margin: 0, wordBreak: "break-word" }}>{formatScalar(k, v)}</dd>
                  </div>
                ))}
              </dl>
            </div>
            {extra?.(item)}
          </>
        )}
      </RealDataPanel>
    </div>
  );
}
