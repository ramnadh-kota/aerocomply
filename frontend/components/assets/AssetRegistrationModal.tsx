"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/auth/SessionContext";
import { useMyEntitlements } from "@/lib/entitlements/useMyEntitlements";
import { assetsApi, type AssetResponse, type AssetCreateRequest } from "@/lib/api/assets";
import { aircraftApi } from "@/lib/api/aircraft";
import { demoStore } from "@/lib/demo/demoStore";
import { normalizeApiError } from "@/lib/apiClient";

export interface AssetRegistrationModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultType?: string;
  lockedType?: string;
  onCreated?: (asset: AssetResponse) => void;
  destinationRoute?: "assets" | "drones";
}

const ASSET_TYPES = [
  { value: "AIRCRAFT", label: "✈ Fixed-Wing Aircraft", placeholderMfr: "Boeing, Airbus, ATR", placeholderMdl: "737-800, A320-200" },
  { value: "DRONE", label: "◆ Unmanned Drone (sUAS)", placeholderMfr: "DJI, SkyRanger, Autel", placeholderMdl: "Matrice 350 RTK, X4 Enterprise" },
  { value: "HELICOPTER", label: "🚁 Rotorcraft / Helicopter", placeholderMfr: "Bell, Sikorsky, Airbus Helicopters", placeholderMdl: "429 GlobalRanger, H145" },
  { value: "EVTOL", label: "⚡ eVTOL / Advanced Air Mobility", placeholderMfr: "Joby Aviation, Archer, Volocopter", placeholderMdl: "S4, Midnight" },
];

export function AssetRegistrationModal({
  isOpen,
  onClose,
  defaultType = "AIRCRAFT",
  lockedType,
  onCreated,
  destinationRoute = "assets",
}: AssetRegistrationModalProps) {
  const router = useRouter();
  const { accessToken, isDemo } = useSession();
  const { effectiveFeatures } = useMyEntitlements();

  const [assetType, setAssetType] = useState(lockedType || defaultType);
  const [registration, setRegistration] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [model, setModel] = useState("");
  const [serialNumber, setSerialNumber] = useState("");
  const [status, setStatus] = useState("ACTIVE");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (lockedType) {
      setAssetType(lockedType);
    } else if (defaultType) {
      setAssetType(defaultType);
    }
  }, [lockedType, defaultType, isOpen]);

  // Keyboard Escape listener
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape" && isOpen && !submitting) {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, submitting, onClose]);

  if (!isOpen) return null;

  // Filter available types based on entitlements (if drone-only tenant, limit to DRONE)
  const isDroneGatedOnly = effectiveFeatures && effectiveFeatures.drone_fleet_management === true && !isDemo;
  const availableTypes = ASSET_TYPES.filter((t) => {
    if (lockedType) return t.value === lockedType;
    return true;
  });

  const currentTypeConfig = ASSET_TYPES.find((t) => t.value === assetType) || ASSET_TYPES[0];

  const modalTitle = lockedType === "DRONE" || assetType === "DRONE"
    ? "Register Unmanned Drone"
    : lockedType === "AIRCRAFT" || assetType === "AIRCRAFT"
    ? "Register Fixed-Wing Aircraft"
    : lockedType === "HELICOPTER" || assetType === "HELICOPTER"
    ? "Register Rotorcraft / Helicopter"
    : "Register Aerospace Asset";

  async function handleFormSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!registration.trim()) {
      setFormError("Tail number / registration is required.");
      return;
    }

    // AIRCRAFT records are created via the canonical POST /aircraft path
    // (which dual-writes Asset + AircraftDetail), not the generic asset
    // endpoint -- that path requires an MSN and a type designation, so the
    // form's existing Serial Number / Model fields double as those here.
    const isRealAircraft = assetType === "AIRCRAFT" && !isDemo && !!accessToken;
    if (isRealAircraft && !serialNumber.trim()) {
      setFormError("Serial Number (MSN) is required for aircraft.");
      return;
    }
    if (isRealAircraft && !model.trim()) {
      setFormError("Model / Aircraft Type designation (e.g. A320, B737-800) is required for aircraft.");
      return;
    }

    setSubmitting(true);
    setFormError(null);

    try {
      let createdAsset: AssetResponse;
      let navigateTo: string;

      if (isRealAircraft) {
        const created = await aircraftApi.create(accessToken!, {
          registration: registration.trim().toUpperCase(),
          msn: serialNumber.trim(),
          aircraft_type: model.trim(),
          status,
          manufacturer: manufacturer.trim() || undefined,
        });
        // Best-effort AssetResponse shape for onCreated callers -- every
        // current caller ignores the argument and just refetches its own
        // list, but the prop's declared type still expects this shape.
        createdAsset = {
          id: created.id,
          organization_id: created.organization_id,
          asset_type: "AIRCRAFT",
          manufacturer: manufacturer.trim() || null,
          model: created.aircraft_type,
          serial_number: created.msn,
          registration: created.registration,
          status: created.status,
          acquired_at: null,
          retired_at: null,
          facility_id: null,
          created_at: created.created_at,
        };
        navigateTo = `/aircraft/${created.id}`;
      } else {
        const payload: AssetCreateRequest = {
          asset_type: assetType.toUpperCase(),
          registration: registration.trim().toUpperCase(),
          manufacturer: manufacturer.trim() || undefined,
          model: model.trim() || undefined,
          serial_number: serialNumber.trim() || undefined,
          status,
        };

        if (isDemo || !accessToken) {
          // Create in interactive Demo Store
          createdAsset = demoStore.addAsset(payload);
        } else {
          // Create in Real Neon DB via Render API
          createdAsset = await assetsApi.createAsset(accessToken, payload);
        }

        navigateTo =
          destinationRoute === "drones" && createdAsset.asset_type === "DRONE"
            ? `/drones/${createdAsset.id}`
            : `/assets/${createdAsset.id}`;
      }

      onCreated?.(createdAsset);
      onClose();
      router.push(navigateTo);
    } catch (err: any) {
      const norm = normalizeApiError(err);
      setFormError(norm.message || "Failed to register asset.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="asset-modal-title"
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.7)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        className="ac-card"
        style={{
          width: "100%",
          maxWidth: 540,
          background: "var(--ac-card-bg, #111827)",
          padding: 24,
          borderRadius: 12,
          border: "1px solid var(--ac-border, #374151)",
          boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <h2 id="asset-modal-title" style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>
              {modalTitle}
            </h2>
            <p className="ac-text-sm ac-text-muted" style={{ margin: "4px 0 0" }}>
              {isDemo ? "DEMO SESSION · Instant synthetic registration" : "Creates tenant-scoped asset record"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ac-button-secondary"
            aria-label="Close registration dialog"
            style={{ padding: "4px 8px", cursor: "pointer", background: "transparent", border: "none", fontSize: 18 }}
          >
            ✕
          </button>
        </div>

        {formError && (
          <div
            style={{
              padding: "10px 14px",
              background: "rgba(239, 68, 68, 0.15)",
              border: "1px solid #ef4444",
              borderRadius: 6,
              color: "#fca5a5",
              marginBottom: 16,
              fontSize: "0.875rem",
            }}
          >
            {formError}
          </div>
        )}

        <form onSubmit={handleFormSubmit}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {/* Asset Type Selector */}
            {!lockedType ? (
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: 4 }}>
                  Asset Class / Type *
                </label>
                <select
                  value={assetType}
                  onChange={(e) => setAssetType(e.target.value)}
                  className="ac-input"
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6 }}
                >
                  {availableTypes.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div style={{ padding: "6px 12px", background: "var(--ac-surface-2)", borderRadius: 6, fontSize: 13 }}>
                Asset Class: <strong>{currentTypeConfig.label}</strong>
              </div>
            )}

            {/* Registration */}
            <div>
              <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: 4 }}>
                Registration / Tail Number *
              </label>
              <input
                type="text"
                placeholder={assetType === "DRONE" ? "e.g. DRN-M350-01, KOTA-D005" : "e.g. N737AA, VT-XYZ"}
                value={registration}
                onChange={(e) => setRegistration(e.target.value)}
                required
                className="ac-input"
                style={{ width: "100%", padding: "8px 10px", borderRadius: 6 }}
              />
            </div>

            {/* Manufacturer & Model */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: 4 }}>
                  Manufacturer
                </label>
                <input
                  type="text"
                  placeholder={currentTypeConfig.placeholderMfr}
                  value={manufacturer}
                  onChange={(e) => setManufacturer(e.target.value)}
                  className="ac-input"
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6 }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: 4 }}>
                  Model{assetType === "AIRCRAFT" ? " / Aircraft Type *" : ""}
                </label>
                <input
                  type="text"
                  placeholder={currentTypeConfig.placeholderMdl}
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="ac-input"
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6 }}
                />
              </div>
            </div>

            {/* Serial Number & Initial Status */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: 4 }}>
                  Serial Number (MSN/S/N){assetType === "AIRCRAFT" ? " *" : ""}
                </label>
                <input
                  type="text"
                  placeholder="e.g. MSN-45124, SN-1029"
                  value={serialNumber}
                  onChange={(e) => setSerialNumber(e.target.value)}
                  className="ac-input"
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6 }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: 4 }}>
                  Initial Status
                </label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  className="ac-input"
                  style={{ width: "100%", padding: "8px 10px", borderRadius: 6 }}
                >
                  <option value="ACTIVE">ACTIVE</option>
                  <option value="IN_SERVICE">IN_SERVICE</option>
                  <option value="MAINTENANCE">MAINTENANCE</option>
                  <option value="PLANNED">PLANNED</option>
                </select>
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 12 }}>
              <button
                type="button"
                onClick={onClose}
                className="ac-btn"
                disabled={submitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="ac-btn"
                disabled={submitting}
                style={{ background: "var(--ac-primary, #38bdf8)", color: "#000", fontWeight: 600 }}
              >
                {submitting ? "Registering..." : `Save ${assetType === "DRONE" ? "Drone" : "Asset"}`}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
