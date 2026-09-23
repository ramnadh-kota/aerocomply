"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { StatusBadge } from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { facilitiesApi, FACILITY_TYPES, type FacilityResponse } from "@/lib/api/facilities";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";

const DEMO_FACILITIES: FacilityResponse[] = [
  {
    id: "00000000-0000-0000-0000-000000000051",
    organization_id: "00000000-0000-0000-0000-000000000001",
    code: "BOM-H1",
    name: "Main Maintenance Hangar",
    facility_type: "HANGAR",
    status: "ACTIVE",
    description: "Primary fixed-wing maintenance base with heavy inspection bays.",
    created_at: "2026-01-15T08:00:00Z",
    updated_at: "2026-01-15T08:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000052",
    organization_id: "00000000-0000-0000-0000-000000000001",
    code: "DEL-V1",
    name: "Drone Vertiport Alpha",
    facility_type: "STATION",
    status: "ACTIVE",
    description: "Autonomous drone launch, recovery, and battery recharge hub.",
    created_at: "2026-02-01T10:00:00Z",
    updated_at: "2026-02-01T10:00:00Z",
  },
  {
    id: "00000000-0000-0000-0000-000000000053",
    organization_id: "00000000-0000-0000-0000-000000000001",
    code: "BLR-W2",
    name: "Avionics & Component Workshop",
    facility_type: "WORKSHOP",
    status: "ACTIVE",
    description: "Component bench testing, sensor calibration, and repair shop.",
    created_at: "2026-02-15T12:00:00Z",
    updated_at: "2026-02-15T12:00:00Z",
  },
];

export default function TenantFacilitiesPage() {
  const { accessToken, isAuthenticated, isDemo } = useSession();
  const [facilities, setFacilities] = useState<FacilityResponse[]>(
    isDemo ? DEMO_FACILITIES : []
  );
  const [loading, setLoading] = useState(!isDemo);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  // New facility modal
  const [showModal, setShowModal] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [facilityType, setFacilityType] = useState<string>(FACILITY_TYPES[0]);
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadFacilities = () => {
    if (isDemo) {
      setFacilities(DEMO_FACILITIES);
      setLoading(false);
      return;
    }

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
    loadFacilities();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDemo, isAuthenticated, accessToken]);

  const handleCreateFacility = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (!code.trim() || !name.trim()) {
      setFormError("Facility code and name are required.");
      return;
    }

    setSubmitting(true);
    if (isDemo) {
      const syntheticNew: FacilityResponse = {
        id: `demo-fac-${Date.now()}`,
        organization_id: "00000000-0000-0000-0000-000000000001",
        code: code.trim().toUpperCase(),
        name: name.trim(),
        facility_type: facilityType,
        status: "ACTIVE",
        description: description.trim() || null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setFacilities((prev) => [syntheticNew, ...prev]);
      setSubmitting(false);
      setShowModal(false);
      setCode("");
      setName("");
      setDescription("");
      return;
    }

    if (!accessToken) return;
    try {
      const created = await facilitiesApi.createFacility(accessToken, {
        code: code.trim().toUpperCase(),
        name: name.trim(),
        facility_type: facilityType,
        description: description.trim() || undefined,
      });
      setFacilities((prev) => [created, ...prev]);
      setShowModal(false);
      setCode("");
      setName("");
      setDescription("");
    } catch (err) {
      setFormError(normalizeApiError(err).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Administration" },
          { label: "Tenant Dashboard", href: "/tenant/dashboard" },
          { label: "Facilities & Sites" },
        ]}
        eyebrow="OPERATIONAL BASES"
        title="Facilities &amp; Operational Sites"
        subtitle="Manage maintenance hangars, workshops, vertiports, and stations where fleet assets are stationed."
        actions={
          <div className="ac-flex ac-gap-2">
            <Link href="/facilities" className="ac-btn">
              Operational Floor View →
            </Link>
            <button
              type="button"
              className="ac-btn ac-btn-primary"
              onClick={() => {
                setShowModal(true);
                setFormError(null);
              }}
            >
              + Register Facility
            </button>
          </div>
        }
      />

      <div style={{ marginBottom: 16 }}>
        {isDemo ? (
          <div
            style={{
              padding: "10px 16px",
              background: "rgba(59, 130, 246, 0.08)",
              border: "1px solid rgba(59, 130, 246, 0.25)",
              borderRadius: 6,
              fontSize: 13,
            }}
          >
            <strong>DEMO MODE</strong> · Showing synthetic operational sites for KOTA Aerospace Demo Operations.
          </div>
        ) : (
          <RealDataPanel
            loading={loading}
            error={error}
            isEmpty={facilities.length === 0}
            emptyMessage="No facilities registered."
          >
            {null}
          </RealDataPanel>
        )}
      </div>

      <div className="ac-card" style={{ padding: 0 }}>
        <div style={{ overflowX: "auto" }}>
          <table className="ac-table">
            <thead>
              <tr>
                <th>Code</th>
                <th>Facility Name</th>
                <th>Type</th>
                <th>Status</th>
                <th>Description</th>
                <th>Registered</th>
              </tr>
            </thead>
            <tbody>
              {facilities.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "32px 16px", opacity: 0.7 }}>
                    No operational facilities configured for this tenant.
                  </td>
                </tr>
              ) : (
                facilities.map((f) => (
                  <tr key={f.id}>
                    <td>
                      <Link href={`/facilities/${f.id}`} className="ac-mono" style={{ fontWeight: 600 }}>
                        {f.code}
                      </Link>
                    </td>
                    <td>
                      <div style={{ fontWeight: 600 }}>{f.name}</div>
                    </td>
                    <td>
                      <span
                        className="ac-mono"
                        style={{
                          fontSize: 11,
                          padding: "2px 6px",
                          borderRadius: 4,
                          background: "var(--bg-subtle, rgba(255, 255, 255, 0.06))",
                          border: "1px solid var(--border-color, #27272a)",
                        }}
                      >
                        {f.facility_type}
                      </span>
                    </td>
                    <td>
                      <StatusBadge
                        status={f.status === "ACTIVE" ? "ACTIVE" : "STORED"}
                        label={f.status}
                      />
                    </td>
                    <td className="ac-text-sm" style={{ opacity: 0.8, maxWidth: 300 }}>
                      {f.description ?? "—"}
                    </td>
                    <td className="ac-mono" style={{ fontSize: 12 }}>
                      {new Date(f.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Register Facility Modal */}
      {showModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.65)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 9999,
          }}
        >
          <div className="ac-card" style={{ maxWidth: 460, width: "90%", padding: 24 }}>
            <h3 className="ac-h3" style={{ marginBottom: 4 }}>
              Register Operational Facility
            </h3>
            <p className="ac-text-sm" style={{ opacity: 0.7, marginBottom: 16 }}>
              Add a physical site, hangar, workshop, or launch station to your organization.
            </p>

            <form onSubmit={handleCreateFacility}>
              <div style={{ marginBottom: 14 }}>
                <label className="ac-label" style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>
                  Facility Code *
                </label>
                <input
                  type="text"
                  className="ac-input ac-mono"
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="e.g. BOM-H1"
                  style={{ width: "100%" }}
                  required
                />
              </div>

              <div style={{ marginBottom: 14 }}>
                <label className="ac-label" style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>
                  Facility Name *
                </label>
                <input
                  type="text"
                  className="ac-input"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Mumbai Base Hangar 1"
                  style={{ width: "100%" }}
                  required
                />
              </div>

              <div style={{ marginBottom: 14 }}>
                <label className="ac-label" style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>
                  Facility Type *
                </label>
                <select
                  className="ac-input"
                  value={facilityType}
                  onChange={(e) => setFacilityType(e.target.value)}
                  style={{ width: "100%" }}
                >
                  {FACILITY_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ marginBottom: 20 }}>
                <label className="ac-label" style={{ display: "block", marginBottom: 4, fontWeight: 600 }}>
                  Description / Operational Scope
                </label>
                <textarea
                  className="ac-input"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Location details, bay capacity, or avionics tooling available..."
                  rows={3}
                  style={{ width: "100%" }}
                />
              </div>

              {formError && (
                <div
                  style={{
                    padding: "8px 12px",
                    background: "rgba(239, 68, 68, 0.15)",
                    color: "var(--danger, #ef4444)",
                    borderRadius: 4,
                    marginBottom: 16,
                    fontSize: 13,
                  }}
                >
                  ⚠ {formError}
                </div>
              )}

              <div className="ac-flex ac-gap-2" style={{ justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="ac-btn"
                  onClick={() => setShowModal(false)}
                  disabled={submitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="ac-btn ac-btn-primary"
                  disabled={submitting}
                >
                  {submitting ? "Registering..." : "Register Facility"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
