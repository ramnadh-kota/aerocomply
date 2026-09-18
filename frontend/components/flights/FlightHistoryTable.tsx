"use client";

// M17.3C — paginated flight-history table for one asset. Uses the
// existing generic DataTable (with its built-in responsive card
// fallback below 640px) rather than a new table primitive. Ordering
// comes entirely from the backend (flown_at DESC, id DESC) -- no
// sortValue is passed to DataTable's columns, so the backend's
// deterministic order is never re-sorted client-side.

import { useEffect, useState } from "react";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { dronesApi, type FlightResponse } from "@/lib/api/drones";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function FlightDetailPanel({
  flightId,
  accessToken,
  onClose,
}: {
  flightId: string;
  accessToken: string;
  onClose: () => void;
}) {
  const [flight, setFlight] = useState<FlightResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    dronesApi
      .getFlight(accessToken, flightId)
      .then(setFlight)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  }, [accessToken, flightId]);

  return (
    <div className="ac-card" style={{ padding: "var(--ac-space-4)", marginTop: "var(--ac-space-3)" }}>
      <div className="ac-flex ac-justify-between" style={{ alignItems: "center" }}>
        <strong className="ac-text-sm">Flight Detail</strong>
        <button className="ac-btn" onClick={onClose} aria-label="Close flight detail">
          Close
        </button>
      </div>
      {loading && (
        <p className="ac-text-sm ac-text-muted" style={{ marginTop: 8 }}>
          Loading flight detail…
        </p>
      )}
      {error && (
        <p className="ac-text-sm" style={{ marginTop: 8, color: "var(--ac-status-non-compliant)" }}>
          {error.message}
        </p>
      )}
      {flight && (
        <dl style={{ margin: "8px 0 0", display: "grid", gridTemplateColumns: "auto 1fr", gap: "4px 12px", fontSize: 13 }}>
          <dt className="ac-text-muted">Flight ID</dt>
          <dd className="ac-mono" style={{ margin: 0, wordBreak: "break-all" }}>{flight.id}</dd>
          <dt className="ac-text-muted">Flown At</dt>
          <dd style={{ margin: 0 }}>{formatTimestamp(flight.flown_at)}</dd>
          <dt className="ac-text-muted">Duration</dt>
          <dd style={{ margin: 0 }}>{flight.duration_minutes} minutes</dd>
          <dt className="ac-text-muted">Cycles</dt>
          <dd style={{ margin: 0 }}>{flight.cycles}</dd>
          <dt className="ac-text-muted">Notes</dt>
          <dd style={{ margin: 0 }}>{flight.notes ?? "Not recorded."}</dd>
        </dl>
      )}
    </div>
  );
}

export function FlightHistoryTable({
  flights,
  total,
  limit,
  offset,
  loading,
  accessToken,
  onPageChange,
}: {
  flights: FlightResponse[];
  total: number;
  limit: number;
  offset: number;
  loading: boolean;
  accessToken: string;
  onPageChange: (offset: number) => void;
}) {
  const [selectedFlightId, setSelectedFlightId] = useState<string | null>(null);

  const columns: Column<FlightResponse>[] = [
    { key: "flown_at", header: "Date", render: (f) => formatTimestamp(f.flown_at) },
    { key: "duration_minutes", header: "Duration", render: (f) => `${f.duration_minutes} min` },
    { key: "hours", header: "Hours", render: (f) => (f.duration_minutes / 60).toFixed(2) },
    { key: "cycles", header: "Cycles", render: (f) => String(f.cycles) },
  ];

  if (flights.length === 0 && !loading) {
    return (
      <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
        No flight records yet. Record the first completed flight to begin tracking operational
        hours and cycles.
      </p>
    );
  }

  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  const hasPrevious = offset > 0;
  const hasNext = offset + limit < total;

  return (
    <div>
      <div className="ac-table-desktop">
        <DataTable
          columns={columns}
          rows={flights}
          onRowClick={(f) => setSelectedFlightId(f.id)}
          emptyMessage="No flight records yet."
        />
      </div>
      <div className="ac-row-cards">
        {flights.map((f) => (
          <div
            className="ac-row-card"
            key={f.id}
            role="button"
            tabIndex={0}
            onClick={() => setSelectedFlightId(f.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setSelectedFlightId(f.id);
              }
            }}
          >
            <div className="ac-row-card-field">
              <span className="ac-row-card-field-label">Date</span>
              <strong>{formatTimestamp(f.flown_at)}</strong>
            </div>
            <div className="ac-row-card-field">
              <span className="ac-row-card-field-label">Duration</span>
              <span>{f.duration_minutes} min</span>
            </div>
            <div className="ac-row-card-field">
              <span className="ac-row-card-field-label">Cycles</span>
              <span>{f.cycles}</span>
            </div>
          </div>
        ))}
      </div>

      <div className="ac-flex ac-justify-between" style={{ alignItems: "center", marginTop: "var(--ac-space-3)", flexWrap: "wrap", gap: 8 }}>
        <span className="ac-text-sm ac-text-muted">
          {total === 0 ? "0 flights" : `${from}–${to} of ${total} flights`}
        </span>
        <div className="ac-flex ac-gap-2">
          <button
            className="ac-btn"
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            disabled={!hasPrevious || loading}
          >
            Previous
          </button>
          <button
            className="ac-btn"
            onClick={() => onPageChange(offset + limit)}
            disabled={!hasNext || loading}
          >
            Next
          </button>
        </div>
      </div>

      {selectedFlightId && (
        <FlightDetailPanel
          flightId={selectedFlightId}
          accessToken={accessToken}
          onClose={() => setSelectedFlightId(null)}
        />
      )}
    </div>
  );
}
