"use client";

// Phase 18.4: Facility detail/edit. REAL-mode tenant page.

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Breadcrumbs } from "@/components/layout/Breadcrumbs";
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

function RealFacilityDetail({ facilityId }: { facilityId: string }) {
  const { accessToken, isAuthenticated } = useSession();
  const [facility, setFacility] = useState<FacilityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  const [name, setName] = useState("");
  const [facilityType, setFacilityType] = useState("");
  const [description, setDescription] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<NormalizedApiError | null>(null);

  const load = () => {
    if (!isAuthenticated || !accessToken) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    facilitiesApi
      .getFacility(accessToken, facilityId)
      .then((f) => {
        setFacility(f);
        setName(f.name);
        setFacilityType(f.facility_type);
        setDescription(f.description ?? "");
      })
      .catch((err) => setError(normalizeApiError(err)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, isAuthenticated, facilityId]);

  const save = () => {
    if (!accessToken || !facility) return;
    setSaving(true);
    setSaveError(null);
    facilitiesApi
      .updateFacility(accessToken, facility.id, {
        name: name.trim(),
        facility_type: facilityType,
        description: description.trim() || null,
      })
      .then(setFacility)
      .catch((err) => setSaveError(normalizeApiError(err)))
      .finally(() => setSaving(false));
  };

  const toggleStatus = () => {
    if (!accessToken || !facility) return;
    setSaving(true);
    setSaveError(null);
    facilitiesApi
      .updateFacility(accessToken, facility.id, {
        status: facility.status === "ACTIVE" ? "INACTIVE" : "ACTIVE",
      })
      .then(setFacility)
      .catch((err) => setSaveError(normalizeApiError(err)))
      .finally(() => setSaving(false));
  };

  return (
    <div>
      <Breadcrumbs
        items={[
          { label: "Dashboard", href: "/dashboard" },
          { label: "Facilities", href: "/facilities" },
          { label: facility?.name ?? "Facility" },
        ]}
      />
      <div className="ac-section-header">
        <div>
          <h1 className="ac-h1">{facility?.name ?? "Facility"}</h1>
          <p className="ac-subtitle">{facility?.code}</p>
        </div>
      </div>

      {!isAuthenticated ? (
        <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
          <p className="ac-text-sm" style={{ margin: 0 }}>
            Sign in to view this facility. <Link href="/login">Sign in →</Link>
          </p>
        </div>
      ) : (
        <RealDataPanel loading={loading} error={error} isEmpty={false} emptyMessage="Facility not found.">
          {facility && (
            <div className="ac-card" style={{ padding: "var(--ac-space-4)" }}>
              <div className="ac-flex" style={{ justifyContent: "space-between", marginBottom: 12 }}>
                <StatusBadge {...statusBadge(facility.status)} />
                <button className="ac-btn" onClick={toggleStatus} disabled={saving}>
                  {facility.status === "ACTIVE" ? "Mark Inactive" : "Mark Active"}
                </button>
              </div>

              <label className="ac-text-sm" style={{ display: "block", marginBottom: 8 }}>
                Name
                <input
                  className="ac-input"
                  style={{ display: "block", width: "100%", maxWidth: 360, marginTop: 4 }}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>

              <label className="ac-text-sm" style={{ display: "block", marginBottom: 8 }}>
                Type
                <select
                  className="ac-input"
                  style={{ display: "block", width: 200, marginTop: 4 }}
                  value={facilityType}
                  onChange={(e) => setFacilityType(e.target.value)}
                >
                  {FACILITY_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>

              <label className="ac-text-sm" style={{ display: "block", marginBottom: 12 }}>
                Description
                <textarea
                  className="ac-input"
                  style={{ display: "block", width: "100%", maxWidth: 480, marginTop: 4, minHeight: 80 }}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>

              {saveError && (
                <p className="ac-text-sm" style={{ margin: "0 0 8px", color: "var(--ac-status-non-compliant)" }}>
                  {saveError.message}
                </p>
              )}

              <button className="ac-btn" onClick={save} disabled={saving || !name.trim()}>
                {saving ? "Saving…" : "Save Changes"}
              </button>
            </div>
          )}
        </RealDataPanel>
      )}
    </div>
  );
}

export default function FacilityDetailPage() {
  const params = useParams<{ id: string }>();
  return <RealFacilityDetail facilityId={params.id} />;
}
