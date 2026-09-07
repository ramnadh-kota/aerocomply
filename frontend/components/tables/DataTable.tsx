"use client";

import { useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number;
  width?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  getRowHref?: (row: T) => string | undefined;
  onRowClick?: (row: T) => void;
  emptyMessage?: string;
  caption?: string;
}

export function DataTable<T>({ columns, rows, getRowHref, onRowClick, emptyMessage, caption }: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const router = useRouter();

  const sortedRows = useMemo(() => {
    if (!sortKey) return rows;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortValue) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = col.sortValue!(a);
      const bv = col.sortValue!(b);
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return copy;
  }, [rows, sortKey, sortDir, columns]);

  function handleSort(col: Column<T>) {
    if (!col.sortValue) return;
    if (sortKey === col.key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(col.key);
      setSortDir("asc");
    }
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="ac-table">
        {caption && <caption className="ac-text-sm ac-text-muted" style={{ textAlign: "left", padding: "0 0 8px" }}>{caption}</caption>}
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{ width: col.width }}
                className={col.sortValue ? "ac-th-sortable" : undefined}
                onClick={() => handleSort(col)}
                aria-sort={sortKey === col.key ? (sortDir === "asc" ? "ascending" : "descending") : undefined}
              >
                {col.header}
                {col.sortValue && sortKey === col.key ? (sortDir === "asc" ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="ac-text-sm ac-text-muted" style={{ textAlign: "center", padding: 24 }}>
                {emptyMessage ?? "No records found."}
              </td>
            </tr>
          )}
          {sortedRows.map((row, idx) => {
            const href = getRowHref?.(row);
            const clickable = Boolean(href || onRowClick);
            return (
              <tr
                key={idx}
                className={clickable ? "ac-row-clickable" : undefined}
                tabIndex={clickable ? 0 : undefined}
                role={clickable ? "link" : undefined}
                onClick={() => {
                  if (href) router.push(href);
                  else onRowClick?.(row);
                }}
                onKeyDown={(e) => {
                  if (!clickable) return;
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    if (href) router.push(href);
                    else onRowClick?.(row);
                  }
                }}
              >
                {columns.map((col) => (
                  <td key={col.key}>{col.render(row)}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
