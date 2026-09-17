"use client";

// Phase 18.4: Facilities Foundation. REAL-mode tenant page — talks to the
// real backend (backend/app/api/v1/facilities.py), scoped to the signed-in
// user's own organization server-side. Backend enforces
// FACILITY_READ/FACILITY_WRITE on every call — this page hiding controls
// from an unauthorized role is a UX convenience, never the security
// boundary.

import { useEffect, useState } from "react";
import Link from "next/link";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
import { DataTable, type Column } from "@/components/tables/DataTable";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { facilitiesApi, FACILITY_TYPES, type FacilityResponse } from "@/lib/api/facilities";

function statusBadge(status: string) {
  return status === "ACTIVE"
    ? { status: "COMPLIANT" as const, label: "Active" }
    : { status: "UNKNOWN" as const, label: "Inactive" };
}

function RealFacilities() {
  const { accessToken, isAuthenticated } = useSession();
  const [facilities, setFacilities] = useState<FacilityResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [facilityType, setFacilityType] = useState<string>(FACILITY_TYPES[0]);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<NormalizedApiError | null>(null);

  const load = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    facilitiesApi
      .listFacilities(accessToken)
      .then(setFacilities)
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated]);

  const createFacility = () => {
    if (!accessToken || !code.trim() || !name.trim()) return;
    setCreating(true);
    setCreateError(null);
    facilitiesApi
      .createFacility(accessToken, { code: code.trim(), name: name.trim(), facility_type: facilityType })
      .then(() => {
        setCode("");
        setName("");
        load();
      })
      .catch((err) => setCreateError(normalizeApiError(err)))
      .finally(() => setCreating(false));
  };

  const columns: Column<FacilityResponse>[] = [
    {
      key: "name",
      header: "Name",
      render: (f) => <Link href={`/facilities/${f.id}`}>{f.name}</Link>,
    },
    { key: "code", header: "Code", render: (f) => f.code },
    { key: "type", header: "Type", render: (f) => f.facility_type },
    { key: "status", header: "Status", render: (f) => <StatusBadge {...statusBadge(f.status)} /> },
    {
      key: "actions",
      header: "Actions",
      render: (f) => (
        <Link className="ac-btn" style={{ fontSize: 12, padding: "2px 8px" }} href={`/facilities/${f.id}`}>
          View
        </Link>
      ),
    },
  ];

  const forbidden = error?.kind === "forbidden";

  return (
    <div>
      <Breadcrumbs items={[{ label: "Dashboard", href: "/dashboard" }, { label: "Facilities" }]} />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">Facilities</h1>
          <p className="ac-subtitle">Hangars, workshops, warehouses, stations, offices, and stores.</p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Sign in to view facilities. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : forbidden ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <StatusBadge status="NON_COMPLIANT" label="Permission Denied" />
          <p className="ac-text-sm" style={{ margin: "8px 0 0" }}>
            You do not have permission to view facilities.
          </p>
        </div>
      ) : (
        <>
          <div className="ac-card ac-section" style={{ padding: "var(--ac-space-4)" }}>
            <strong className="ac-text-sm">Create a facility</strong>
            <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
              <input
                className="ac-input"
                style={{ width: 220 }}
                placeholder="Facility name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-label="Facility name"
              />
              <input
                className="ac-input"
                style={{ width: 140 }}
                placeholder="Code (e.g. HGR-01)"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                aria-label="Facility code"
              />
              <select
                className="ac-input"
                style={{ width: 160 }}
                value={facilityType}
                onChange={(e) => setFacilityType(e.target.value)}
                aria-label="Facility type"
              >
                {FACILITY_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <button className="ac-btn" onClick={createFacility} disabled={creating || !code.trim() || !name.trim()}>
                {creating ? "Creating…" : "Create Facility"}
              </button>
            </div>
            {createError && (
              <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
                {createError.message}
              </p>
            )}
          </div>

          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={facilities.length === 0}
            emptyMessage="No facilities have been created yet."
          >
            <div className="ac-card" style={{ padding: 0 }}>
              <div className="ac-table-desktop">
                <DataTable columns={columns} rows={facilities} getRowHref={(f) => `/facilities/${f.id}`} />
              </div>
              <div className="ac-row-cards">
                {facilities.map((f) => (
                  <div className="ac-row-card" key={f.id}>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Name</span>
                      <strong>
                        <Link href={`/facilities/${f.id}`}>{f.name}</Link>
                      </strong>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Code</span>
                      <span>{f.code}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Type</span>
                      <span>{f.facility_type}</span>
                    </div>
                    <div className="ac-row-card-field">
                      <span className="ac-row-card-field-label">Status</span>
                      <StatusBadge {...statusBadge(f.status)} />
                    </div>
                    <div className="ac-row-card-actions">
                      <Link className="ac-btn" href={`/facilities/${f.id}`}>
                        View
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </RealDataPanel>
        </>
      )}
    </div>
  );
}

export default function FacilitiesPage() {
  return <RealFacilities />;
}
