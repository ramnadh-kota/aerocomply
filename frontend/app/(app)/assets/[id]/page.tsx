"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import {
  StatusBadge,
  assetStatusBadge as statusBadge,
  operationalStateBadge,
  intelligenceReadinessBadge,
  intelligenceRiskLevelBadge,
  intelligenceDecisionBadge,
} from "@/components/status/StatusBadge";
import { RealDataPanel } from "@/components/data-mode/RealDataPanel";
import { useSession } from "@/lib/auth/SessionContext";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import {
  intelligenceApi,
  type AssetReadinessIntelligence,
  type AssetRiskIntelligence,
  type AssetPriorityIntelligence,
  type AssetDecision as AssetDecisionIntelligence,
  type AssetRecommendation,
  type ProactiveSignal,
} from "@/lib/api/intelligence";
import { ProactiveSignalsSection } from "@/components/intelligence/ProactiveSignalsSection";
import { humsApi, type HUMSAssetHealthSummary } from "@/lib/api/hums";
import { HUMSHealthPanel } from "@/components/intelligence/HUMSHealthPanel";
import { TelemetryPanel } from "@/components/intelligence/TelemetryPanel";
import { HUMSHealthIntelligencePanel } from "@/components/intelligence/HUMSHealthIntelligencePanel";
import { HUMSDiagnosticsPanel } from "@/components/intelligence/HUMSDiagnosticsPanel";
import { HUMSPrognosticsPanel } from "@/components/intelligence/HUMSPrognosticsPanel";
import { DigitalTwinPanel } from "@/components/intelligence/DigitalTwinPanel";
import { MROIntelligencePanel } from "@/components/intelligence/MROIntelligencePanel";
import { useEntitlements } from "@/lib/entitlements/EntitlementContext";

import {
  assetsApi,
  type AssetResponse,
  type AssetConfigurationResponse,
  type AssetComponentResponse,
  type AssetOperationsResponse,
  type AssetMaintenanceResponse,
  type AssetInspectionsResponse,
  type AssetEvidenceResponse,
  type AssetFindingsResponse,
  type AssetComplianceResponse,
  type AssetReadinessResponse,
  type AssetHistoryResponse,
  type AssetDomainContextResponse,
  type AssetInstallComponentRequest,
  type AssetFlightCreateRequest,
} from "@/lib/api/assets";
import {
  getDemoAssetDetail,
  getDemoConfiguration,
  getDemoOperations,
  getDemoMaintenance,
  getDemoInspections,
  getDemoEvidence,
  getDemoFindings,
  getDemoCompliance,
  getDemoReadiness,
  getDemoHistory,
  getDemoDomainContext,
} from "@/lib/demo/demoAssets";

type TabKey =
  | "OVERVIEW"
  | "CONFIGURATION"
  | "OPERATIONS"
  | "COMPONENTS"
  | "MAINTENANCE"
  | "INSPECTIONS"
  | "EVIDENCE"
  | "FINDINGS"
  | "COMPLIANCE"
  | "READINESS"
  | "HISTORY"
  | "INTELLIGENCE";

const TABS: { key: TabKey; label: string; icon: string }[] = [
  { key: "OVERVIEW", label: "Overview", icon: "◧" },
  { key: "CONFIGURATION", label: "Configuration", icon: "⛭" },
  { key: "OPERATIONS", label: "Operations", icon: "▶" },
  { key: "COMPONENTS", label: "Components", icon: "▤" },
  { key: "MAINTENANCE", label: "Maintenance", icon: "▦" },
  { key: "INSPECTIONS", label: "Inspections", icon: "🔍" },
  { key: "EVIDENCE", label: "Evidence", icon: "▣" },
  { key: "FINDINGS", label: "Findings", icon: "⚠" },
  { key: "COMPLIANCE", label: "Compliance", icon: "§" },
  { key: "READINESS", label: "Readiness", icon: "✓" },
  { key: "HISTORY", label: "History", icon: "≡" },
  { key: "INTELLIGENCE", label: "Intelligence", icon: "◈" },
];

function InstallComponentModal({
  isOpen,
  onClose,
  onSubmit,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: AssetInstallComponentRequest) => Promise<void>;
}) {
  const [componentType, setComponentType] = useState("ENGINE");
  const [name, setName] = useState("");
  const [serialNumber, setSerialNumber] = useState("");
  const [manufacturer, setManufacturer] = useState("");
  const [model, setModel] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("Component name is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        component_type: componentType,
        name: name.trim(),
        serial_number: serialNumber.trim() || undefined,
        manufacturer: manufacturer.trim() || undefined,
        model: model.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to install component");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.65)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        className="ac-card"
        style={{
          width: "100%",
          maxWidth: 480,
          background: "var(--ac-bg-elevated)",
          padding: "24px",
          borderRadius: "12px",
          border: "1px solid var(--ac-border)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: "1.15rem", fontWeight: 700 }}>Install Component</h3>
          <button type="button" onClick={onClose} className="ac-button-secondary">✕</button>
        </div>

        {error && <div style={{ color: "var(--ac-status-non-compliant)", marginBottom: 12, fontSize: "0.85rem" }}>{error}</div>}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div>
            <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>Component Type</label>
            <select
              value={componentType}
              onChange={(e) => setComponentType(e.target.value)}
              style={{ width: "100%", padding: "8px", background: "var(--ac-bg-surface-hover)", color: "var(--ac-text-primary)", borderRadius: 6, border: "1px solid var(--ac-border)" }}
            >
              <option value="ENGINE">Engine / Turboshaft / Turbofan</option>
              <option value="MOTOR">Electric Propulsion Motor</option>
              <option value="BATTERY">Battery / Power Pack</option>
              <option value="AVIONICS">Avionics System</option>
              <option value="FLIGHT_CONTROLLER">Flight Controller</option>
              <option value="TRANSMISSION">Transmission / Gearbox</option>
              <option value="ROTOR">Rotor System / Blades</option>
              <option value="PROPELLER">Propeller Assembly</option>
              <option value="CAMERA">Sensor / Camera Payload</option>
              <option value="APU">Auxiliary Power Unit (APU)</option>
              <option value="ACTUATOR">Flight Control Actuator</option>
            </select>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>Component Name *</label>
            <input
              type="text"
              placeholder="e.g. CFM56-7B26 Engine #1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              style={{ width: "100%", padding: "8px", background: "var(--ac-bg-surface-hover)", color: "var(--ac-text-primary)", borderRadius: 6, border: "1px solid var(--ac-border)" }}
            />
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>Serial Number</label>
              <input
                type="text"
                placeholder="e.g. SN-89104"
                value={serialNumber}
                onChange={(e) => setSerialNumber(e.target.value)}
                style={{ width: "100%", padding: "8px", background: "var(--ac-bg-surface-hover)", color: "var(--ac-text-primary)", borderRadius: 6, border: "1px solid var(--ac-border)" }}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>Manufacturer</label>
              <input
                type="text"
                placeholder="e.g. CFM, Pratt & Whitney"
                value={manufacturer}
                onChange={(e) => setManufacturer(e.target.value)}
                style={{ width: "100%", padding: "8px", background: "var(--ac-bg-surface-hover)", color: "var(--ac-text-primary)", borderRadius: 6, border: "1px solid var(--ac-border)" }}
              />
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>Model / Part Number</label>
            <input
              type="text"
              placeholder="e.g. PW207D1"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              style={{ width: "100%", padding: "8px", background: "var(--ac-bg-surface-hover)", color: "var(--ac-text-primary)", borderRadius: 6, border: "1px solid var(--ac-border)" }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>Installation Notes</label>
            <textarea
              placeholder="Mounting position, initial TSO, or traceability tags"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              style={{ width: "100%", padding: "8px", background: "var(--ac-bg-surface-hover)", color: "var(--ac-text-primary)", borderRadius: 6, border: "1px solid var(--ac-border)" }}
            />
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
            <button type="button" onClick={onClose} className="ac-button-secondary">Cancel</button>
            <button type="submit" className="ac-button-primary" disabled={submitting}>
              {submitting ? "Installing..." : "Install Component"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function LogFlightModal({
  isOpen,
  onClose,
  onSubmit,
}: {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: AssetFlightCreateRequest) => Promise<void>;
}) {
  const [durationMinutes, setDurationMinutes] = useState(60);
  const [cycles, setCycles] = useState(1);
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        flown_at: new Date().toISOString(),
        duration_minutes: Number(durationMinutes),
        cycles: Number(cycles),
        notes: notes.trim() || undefined,
      });
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to record flight");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.65)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        className="ac-card"
        style={{
          width: "100%",
          maxWidth: 440,
          background: "var(--ac-bg-elevated)",
          padding: "24px",
          borderRadius: "12px",
          border: "1px solid var(--ac-border)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
          <h3 style={{ margin: 0, fontSize: "1.15rem", fontWeight: 700 }}>Record Flight / Operation</h3>
          <button type="button" onClick={onClose} className="ac-button-secondary">✕</button>
        </div>

        {error && <div style={{ color: "var(--ac-status-non-compliant)", marginBottom: 12, fontSize: "0.85rem" }}>{error}</div>}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>Duration (Minutes) *</label>
              <input
                type="number"
                min="1"
                value={durationMinutes}
                onChange={(e) => setDurationMinutes(Number(e.target.value))}
                required
                style={{ width: "100%", padding: "8px", background: "var(--ac-bg-surface-hover)", color: "var(--ac-text-primary)", borderRadius: 6, border: "1px solid var(--ac-border)" }}
              />
            </div>
            <div>
              <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>Cycles *</label>
              <input
                type="number"
                min="1"
                value={cycles}
                onChange={(e) => setCycles(Number(e.target.value))}
                required
                style={{ width: "100%", padding: "8px", background: "var(--ac-bg-surface-hover)", color: "var(--ac-text-primary)", borderRadius: 6, border: "1px solid var(--ac-border)" }}
              />
            </div>
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.8rem", marginBottom: 4 }}>Flight Notes</label>
            <textarea
              placeholder="Route leg, flight mission profile, pilot in command notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              style={{ width: "100%", padding: "8px", background: "var(--ac-bg-surface-hover)", color: "var(--ac-text-primary)", borderRadius: 6, border: "1px solid var(--ac-border)" }}
            />
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
            <button type="button" onClick={onClose} className="ac-button-secondary">Cancel</button>
            <button type="submit" className="ac-button-primary" disabled={submitting}>
              {submitting ? "Logging..." : "Log Flight"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function AssetDetailPage() {
  const params = useParams();
  const assetId = (params?.id as string) || "";
  const searchParams = useSearchParams();
  const { accessToken, sessionType } = useSession();
  const { hasFeature } = useEntitlements();

  const requestedTab = searchParams?.get("tab") as TabKey | null;
  const initialTab: TabKey = TABS.some((t) => t.key === requestedTab) ? (requestedTab as TabKey) : "OVERVIEW";
  const [activeTab, setActiveTab] = useState<TabKey>(initialTab);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<NormalizedApiError | null>(null);

  // Domain state
  const [asset, setAsset] = useState<AssetResponse | null>(null);
  const [config, setConfig] = useState<AssetConfigurationResponse | null>(null);
  const [components, setComponents] = useState<AssetComponentResponse[]>([]);
  const [operations, setOperations] = useState<AssetOperationsResponse | null>(null);
  const [maintenance, setMaintenance] = useState<AssetMaintenanceResponse | null>(null);
  const [inspections, setInspections] = useState<AssetInspectionsResponse | null>(null);
  const [evidence, setEvidence] = useState<AssetEvidenceResponse | null>(null);
  const [findings, setFindings] = useState<AssetFindingsResponse | null>(null);
  const [compliance, setCompliance] = useState<AssetComplianceResponse | null>(null);
  const [readiness, setReadiness] = useState<AssetReadinessResponse | null>(null);
  const [history, setHistory] = useState<AssetHistoryResponse | null>(null);
  const [context, setContext] = useState<AssetDomainContextResponse | null>(null);

  // D2.2 Intelligence layer (M4.3 & M7) -- REAL mode only, see fetch effect below.
  const [intelReadiness, setIntelReadiness] = useState<AssetReadinessIntelligence | null>(null);
  const [intelRisk, setIntelRisk] = useState<AssetRiskIntelligence | null>(null);
  const [intelPriority, setIntelPriority] = useState<AssetPriorityIntelligence | null>(null);
  const [intelDecision, setIntelDecision] = useState<AssetDecisionIntelligence | null>(null);
  const [intelRecommendation, setIntelRecommendation] = useState<AssetRecommendation | null>(null);
  const [assetSignals, setAssetSignals] = useState<ProactiveSignal[]>([]);
  // H1: HUMS foundation -- REAL mode only, same fail-soft fetch pattern as the D2.2 intelligence fields above.
  const [humsHealth, setHumsHealth] = useState<HUMSAssetHealthSummary | null>(null);

  // Modals
  const [isInstallModalOpen, setIsInstallModalOpen] = useState(false);
  const [isLogFlightModalOpen, setIsLogFlightModalOpen] = useState(false);

  const refreshAssetSignals = () => {
    if (!accessToken || !assetId) return;
    intelligenceApi
      .getAssetSignals(accessToken, assetId)
      .then((sigs) => setAssetSignals(sigs))
      .catch(() => {});
  };

  useEffect(() => {
    if (sessionType === "DEMO") {
      const demoA = getDemoAssetDetail(assetId);
      if (demoA) {
        setAsset(demoA);
        setConfig(getDemoConfiguration(assetId));
        setOperations(getDemoOperations(assetId));
        setMaintenance(getDemoMaintenance(assetId));
        setInspections(getDemoInspections(assetId));
        setEvidence(getDemoEvidence(assetId));
        setFindings(getDemoFindings(assetId));
        setCompliance(getDemoCompliance(assetId));
        setReadiness(getDemoReadiness(assetId));
        setHistory(getDemoHistory(assetId));
        setContext(getDemoDomainContext(assetId));
      }
      setLoading(false);
      return;
    }

    if (!accessToken || !assetId) return;

    setLoading(true);
    setError(null);

    Promise.all([
      assetsApi.getAsset(accessToken, assetId),
      assetsApi.getConfiguration(accessToken, assetId).catch(() => null),
      assetsApi.getComponents(accessToken, assetId).catch(() => []),
      assetsApi.getOperations(accessToken, assetId).catch(() => null),
      assetsApi.getMaintenance(accessToken, assetId).catch(() => null),
      assetsApi.getInspections(accessToken, assetId).catch(() => null),
      assetsApi.getEvidence(accessToken, assetId).catch(() => null),
      assetsApi.getFindings(accessToken, assetId).catch(() => null),
      assetsApi.getCompliance(accessToken, assetId).catch(() => null),
      assetsApi.getReadiness(accessToken, assetId).catch(() => null),
      assetsApi.getHistory(accessToken, assetId).catch(() => null),
      assetsApi.getContext(accessToken, assetId).catch(() => null),
      intelligenceApi.getReadiness(accessToken, assetId).catch(() => null),
      intelligenceApi.getRisk(accessToken, assetId).catch(() => null),
      intelligenceApi.getPriority(accessToken, assetId).catch(() => null),
      intelligenceApi.getDecision(accessToken, assetId).catch(() => null),
      intelligenceApi.getRecommendations(accessToken, assetId).catch(() => null),
      intelligenceApi.getAssetSignals(accessToken, assetId).catch(() => []),
      humsApi.getAssetHealth(accessToken, assetId).catch(() => null),
    ])
      .then(
        ([
          a,
          cfg,
          comps,
          ops,
          maint,
          insps,
          ev,
          fnds,
          comp,
          rdy,
          hist,
          ctx,
          intelRdy,
          intelRsk,
          intelPri,
          intelDec,
          intelRec,
          sigs,
          humsHlth,
        ]) => {
          setAsset(a);
          setConfig(cfg);
          setComponents(comps);
          setOperations(ops);
          setMaintenance(maint);
          setInspections(insps);
          setEvidence(ev);
          setFindings(fnds);
          setCompliance(comp);
          setReadiness(rdy);
          setHistory(hist);
          setContext(ctx);
          setIntelReadiness(intelRdy);
          setIntelRisk(intelRsk);
          setIntelPriority(intelPri);
          setIntelDecision(intelDec);
          setIntelRecommendation(intelRec);
          setAssetSignals(sigs);
          setHumsHealth(humsHlth);
        }
      )
      .catch((err) => {
        setError(normalizeApiError(err));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [assetId, sessionType, accessToken]);


  async function handleInstallComponent(data: AssetInstallComponentRequest) {
    if (sessionType === "DEMO") {
      const newComp: AssetComponentResponse = {
        id: `demo-comp-${Date.now()}`,
        organization_id: "demo-org-id",
        asset_id: assetId,
        component_type: data.component_type,
        name: data.name,
        serial_number: data.serial_number || null,
        manufacturer: data.manufacturer || null,
        model: data.model || null,
        status: "INSTALLED",
        installed_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
      };
      setComponents((prev) => [newComp, ...prev]);
      return;
    }

    if (!accessToken) return;
    const created = await assetsApi.installComponent(accessToken, assetId, data);
    setComponents((prev) => [created, ...prev]);
    // Refresh configuration
    const refreshedConfig = await assetsApi.getConfiguration(accessToken, assetId);
    setConfig(refreshedConfig);
  }

  async function handleRemoveComponent(componentId: string) {
    if (sessionType === "DEMO") {
      setComponents((prev) => prev.filter((c) => c.id !== componentId));
      return;
    }

    if (!accessToken) return;
    await assetsApi.removeComponent(accessToken, assetId, componentId);
    setComponents((prev) => prev.filter((c) => c.id !== componentId));
    const refreshedConfig = await assetsApi.getConfiguration(accessToken, assetId);
    setConfig(refreshedConfig);
  }

  async function handleLogFlight(data: AssetFlightCreateRequest) {
    if (sessionType === "DEMO") {
      if (operations) {
        const hoursAdded = data.duration_minutes / 60;
        setOperations({
          ...operations,
          utilization: {
            ...operations.utilization,
            total_flight_hours: Number((operations.utilization.total_flight_hours + hoursAdded).toFixed(1)),
            total_cycles: operations.utilization.total_cycles + (data.cycles || 1),
            total_flights: operations.utilization.total_flights + 1,
          },
          recent_flights: [
            {
              id: `demo-flight-${Date.now()}`,
              organization_id: "demo-org-id",
              asset_id: assetId,
              mission_id: null,
              flown_at: data.flown_at,
              duration_minutes: data.duration_minutes,
              cycles: data.cycles || 1,
              pilot_user_id: null,
              notes: data.notes || null,
              created_at: new Date().toISOString(),
            },
            ...operations.recent_flights,
          ],
        });
      }
      return;
    }

    if (!accessToken) return;
    await assetsApi.recordFlight(accessToken, assetId, data);
    const refreshedOps = await assetsApi.getOperations(accessToken, assetId);
    setOperations(refreshedOps);
  }

  if (loading) {
    return (
      <div className="ac-page" style={{ padding: "40px", textAlign: "center" }}>
        <p style={{ color: "var(--ac-text-secondary)" }}>Loading unified asset context...</p>
      </div>
    );
  }

  if (error || !asset) {
    return (
      <div className="ac-page">
        <RealDataPanel
          loading={false}
          error={error}
          isEmpty={!asset}
          emptyMessage="Asset could not be found or access is unauthorized."
        >
          <div />
        </RealDataPanel>
      </div>
    );
  }

  const isGrounded = asset.status === "GROUNDED" || asset.status === "MAINTENANCE";
  // The backend's compute_operational_state (GET /assets/{id}/context) is
  // the one authoritative operational-state computation -- it accounts for
  // active missions, open work orders, and pending inspections, not just
  // the static lifecycle status column. Falling back to the coarser
  // asset.status-only heuristic only if the context call itself failed.
  const operationalStatus = context?.operational_status ?? (isGrounded ? "GROUNDED" : "AVAILABLE");
  const readinessStatus = readiness?.overall_status || (isGrounded ? "AT_RISK" : "READY");
  const complianceStatus = compliance?.overall_status || "COMPLIANT";

  return (
    <div className="ac-page">
      {/* Back link */}
      <div style={{ marginBottom: 12 }}>
        <Link href="/assets" className="ac-link" style={{ fontSize: "0.85rem" }}>
          ← Back to Fleet Registry
        </Link>
      </div>

      {/* Asset Header Shell */}
      <div
        className="ac-card"
        style={{
          padding: "20px 24px",
          marginBottom: 16,
          background: "linear-gradient(135deg, var(--ac-bg-elevated) 0%, var(--ac-bg-surface-hover) 100%)",
          border: "1px solid var(--ac-border)",
          borderRadius: 12,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span
                style={{
                  background: "rgba(56, 189, 248, 0.15)",
                  color: "var(--ac-accent)",
                  padding: "3px 10px",
                  borderRadius: 12,
                  fontSize: "0.8rem",
                  fontWeight: 700,
                  letterSpacing: "0.5px",
                }}
              >
                {asset.asset_type}
              </span>
              <h1 style={{ margin: 0, fontSize: "1.75rem", fontWeight: 800, color: "var(--ac-text-primary)" }}>
                {asset.registration}
              </h1>
            </div>
            <p style={{ margin: 0, color: "var(--ac-text-secondary)", fontSize: "0.95rem" }}>
              {asset.manufacturer || "Manufacturer Unspecified"} {asset.model ? `· ${asset.model}` : ""}{" "}
              {asset.serial_number ? `(S/N: ${asset.serial_number})` : ""}
            </p>
          </div>

          {/* 4 Status Dimensions */}
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <div style={{ background: "var(--ac-bg-surface-hover)", padding: "8px 12px", borderRadius: 8, border: "1px solid var(--ac-border)" }}>
              <div style={{ fontSize: "0.65rem", textTransform: "uppercase", color: "var(--ac-text-secondary)", marginBottom: 2 }}>
                Lifecycle
              </div>
              <StatusBadge {...statusBadge(asset.status)} />
            </div>

            <div style={{ background: "var(--ac-bg-surface-hover)", padding: "8px 12px", borderRadius: 8, border: "1px solid var(--ac-border)" }}>
              <div style={{ fontSize: "0.65rem", textTransform: "uppercase", color: "var(--ac-text-secondary)", marginBottom: 2 }}>
                Operational
              </div>
              <StatusBadge {...operationalStateBadge(operationalStatus)} />
            </div>

            <div style={{ background: "var(--ac-bg-surface-hover)", padding: "8px 12px", borderRadius: 8, border: "1px solid var(--ac-border)" }}>
              <div style={{ fontSize: "0.65rem", textTransform: "uppercase", color: "var(--ac-text-secondary)", marginBottom: 2 }}>
                Readiness
              </div>
              <StatusBadge
                status={readinessStatus === "READY" ? "COMPLIANT" : "NON_COMPLIANT"}
                label={readinessStatus}
              />
            </div>

            <div style={{ background: "var(--ac-bg-surface-hover)", padding: "8px 12px", borderRadius: 8, border: "1px solid var(--ac-border)" }}>
              <div style={{ fontSize: "0.65rem", textTransform: "uppercase", color: "var(--ac-text-secondary)", marginBottom: 2 }}>
                Compliance
              </div>
              <StatusBadge
                status={complianceStatus === "COMPLIANT" ? "COMPLIANT" : "REVIEW_REQUIRED"}
                label={complianceStatus}
              />
            </div>
          </div>
        </div>

        {/* Domain-specific link banner */}
        {asset.asset_type === "DRONE" && (
          <div
            style={{
              marginTop: 16,
              padding: "10px 14px",
              background: "rgba(168, 85, 247, 0.12)",
              border: "1px solid rgba(168, 85, 247, 0.4)",
              borderRadius: 8,
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              fontSize: "0.85rem",
            }}
          >
            <span>
              <strong>sUAS Domain Integration:</strong> This drone airframe is connected to the specialized Drone Operational Console.
            </span>
            <Link
              href={`/drones/${asset.id}`}
              className="ac-button-primary"
              style={{ fontSize: "0.75rem", padding: "4px 10px" }}
            >
              Open Drone Console →
            </Link>
          </div>
        )}
      </div>

      {/* 11 Tabs Navigation */}
      <div
        style={{
          display: "flex",
          gap: 4,
          borderBottom: "1px solid var(--ac-border)",
          marginBottom: 20,
          overflowX: "auto",
          paddingBottom: 4,
        }}
      >
        {TABS.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "8px 14px",
                borderRadius: "8px 8px 0 0",
                fontSize: "0.85rem",
                fontWeight: isActive ? 700 : 500,
                color: isActive ? "var(--ac-accent)" : "var(--ac-text-secondary)",
                background: isActive ? "rgba(56, 189, 248, 0.08)" : "transparent",
                border: "none",
                borderBottom: isActive ? "2px solid #38bdf8" : "2px solid transparent",
                cursor: "pointer",
                whiteSpace: "nowrap",
                transition: "all 0.15s ease",
              }}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* TAB 1: OVERVIEW */}
      {activeTab === "OVERVIEW" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
            <div className="ac-card" style={{ padding: 16 }}>
              <div style={{ fontSize: "0.75rem", color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>
                Total Flight Hours (TTAF)
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--ac-text-primary)", marginTop: 4 }}>
                {operations?.utilization.total_flight_hours ?? 0} hrs
              </div>
            </div>
            <div className="ac-card" style={{ padding: 16 }}>
              <div style={{ fontSize: "0.75rem", color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>
                Airframe Cycles
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--ac-text-primary)", marginTop: 4 }}>
                {operations?.utilization.total_cycles ?? 0}
              </div>
            </div>
            <div className="ac-card" style={{ padding: 16 }}>
              <div style={{ fontSize: "0.75rem", color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>
                Open Work Orders
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--ac-status-review)", marginTop: 4 }}>
                {maintenance?.open_work_orders.length ?? 0}
              </div>
            </div>
            <div className="ac-card" style={{ padding: 16 }}>
              <div style={{ fontSize: "0.75rem", color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>
                Active Findings
              </div>
              <div style={{ fontSize: "1.75rem", fontWeight: 700, color: findings?.open_count ? "var(--ac-status-non-compliant)" : "var(--ac-status-compliant)", marginTop: 4 }}>
                {findings?.open_count ?? 0}
              </div>
            </div>
          </div>

          <div className="ac-card" style={{ padding: 20 }}>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "1rem", fontWeight: 700 }}>Airframe Specifications</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: "0.875rem" }}>
              <div>
                <span style={{ color: "var(--ac-text-secondary)" }}>Registration: </span>
                <strong>{asset.registration}</strong>
              </div>
              <div>
                <span style={{ color: "var(--ac-text-secondary)" }}>Asset Class: </span>
                <strong>{asset.asset_type}</strong>
              </div>
              <div>
                <span style={{ color: "var(--ac-text-secondary)" }}>Manufacturer: </span>
                <strong>{asset.manufacturer || "—"}</strong>
              </div>
              <div>
                <span style={{ color: "var(--ac-text-secondary)" }}>Model: </span>
                <strong>{asset.model || "—"}</strong>
              </div>
              <div>
                <span style={{ color: "var(--ac-text-secondary)" }}>Serial / MSN: </span>
                <strong>{asset.serial_number || "—"}</strong>
              </div>
              <div>
                <span style={{ color: "var(--ac-text-secondary)" }}>Registered Date: </span>
                <strong>{new Date(asset.created_at).toLocaleDateString()}</strong>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: CONFIGURATION */}
      {activeTab === "CONFIGURATION" && (
        <div className="ac-card" style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Airframe Configuration Architecture</h3>
              <p style={{ margin: "4px 0 0 0", color: "var(--ac-text-secondary)", fontSize: "0.85rem" }}>
                Standardized slot positions and installed modules across the {asset.asset_type} domain.
              </p>
            </div>
            <button
              type="button"
              className="ac-button-primary"
              onClick={() => setIsInstallModalOpen(true)}
            >
              + Install into Slot
            </button>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {config?.slots && config.slots.length > 0 ? (
              config.slots.map((slot, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "14px 18px",
                    borderRadius: 8,
                    background: slot.is_occupied ? "var(--ac-bg-surface-hover)" : "var(--ac-bg-surface-hover)",
                    border: slot.is_occupied ? "1px solid var(--ac-border)" : "1px dashed #4b5563",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          background: slot.is_occupied ? "#10b981" : "#6b7280",
                        }}
                      />
                      <strong style={{ fontSize: "0.95rem" }}>{slot.slot_name}</strong>
                      <span style={{ fontSize: "0.75rem", color: "var(--ac-text-secondary)" }}>[{slot.component_type}]</span>
                    </div>
                    {slot.component ? (
                      <div style={{ marginTop: 6, fontSize: "0.85rem", color: "var(--ac-text-secondary)" }}>
                        Installed: <strong>{slot.component.name}</strong> · S/N: {slot.component.serial_number || "—"} · Mfr: {slot.component.manufacturer || "—"}
                      </div>
                    ) : (
                      <div style={{ marginTop: 4, fontSize: "0.8rem", color: "var(--ac-text-secondary)", fontStyle: "italic" }}>
                        Slot unoccupied
                      </div>
                    )}
                  </div>
                  <div>
                    {slot.component && (
                      <button
                        type="button"
                        onClick={() => handleRemoveComponent(slot.component!.id)}
                        className="ac-button-secondary"
                        style={{ fontSize: "0.75rem", color: "var(--ac-status-non-compliant)" }}
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No configuration slots mapped for this airframe.</p>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: OPERATIONS */}
      {activeTab === "OPERATIONS" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="ac-card" style={{ padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Operational Utilization & Logging</h3>
                <p style={{ margin: "4px 0 0 0", color: "var(--ac-text-secondary)", fontSize: "0.85rem" }}>
                  Flight legs, total time in service, and mission cycle metrics.
                </p>
              </div>
              <button
                type="button"
                className="ac-button-primary"
                onClick={() => setIsLogFlightModalOpen(true)}
              >
                + Log Flight
              </button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12, marginBottom: 20 }}>
              {operations?.utilization.metrics.map((m, idx) => (
                <div key={idx} style={{ background: "var(--ac-bg-surface-hover)", padding: "12px 16px", borderRadius: 8, border: "1px solid var(--ac-border)" }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>{m.metric_label}</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--ac-accent)", marginTop: 4 }}>
                    {m.value} <span style={{ fontSize: "0.85rem", fontWeight: 400 }}>{m.unit}</span>
                  </div>
                </div>
              ))}
            </div>

            <h4 style={{ margin: "0 0 10px 0", fontSize: "0.95rem", fontWeight: 700 }}>Recent Flight History</h4>
            {operations?.recent_flights && operations.recent_flights.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {operations.recent_flights.map((f, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "10px 14px",
                      background: "var(--ac-bg-surface-hover)",
                      borderRadius: 6,
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "0.85rem",
                    }}
                  >
                    <div>
                      <strong>{new Date(f.flown_at).toLocaleDateString()}</strong> · {f.duration_minutes} minutes ({f.cycles} cycle{f.cycles > 1 ? "s" : ""})
                      {f.notes && <div style={{ color: "var(--ac-text-secondary)", marginTop: 2 }}>{f.notes}</div>}
                    </div>
                    <div style={{ color: "var(--ac-accent)" }}>Completed</div>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No flight legs logged yet.</p>
            )}
          </div>
        </div>
      )}

      {/* TAB 4: COMPONENTS */}
      {activeTab === "COMPONENTS" && (
        <div className="ac-card" style={{ padding: 20 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Installed Aerospace Components</h3>
              <p style={{ margin: "4px 0 0 0", color: "var(--ac-text-secondary)", fontSize: "0.85rem" }}>
                Active component genealogy and serial tracking.
              </p>
            </div>
            <button
              type="button"
              className="ac-button-primary"
              onClick={() => setIsInstallModalOpen(true)}
            >
              + Install Component
            </button>
          </div>

          {components && components.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {components.map((c) => (
                <div
                  key={c.id}
                  style={{
                    padding: "12px 16px",
                    background: "var(--ac-bg-surface-hover)",
                    borderRadius: 8,
                    border: "1px solid var(--ac-border)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <strong style={{ fontSize: "0.95rem" }}>{c.name}</strong>
                      <span style={{ fontSize: "0.75rem", background: "var(--ac-border)", padding: "2px 6px", borderRadius: 4 }}>
                        {c.component_type}
                      </span>
                    </div>
                    <div style={{ fontSize: "0.8rem", color: "var(--ac-text-secondary)", marginTop: 4 }}>
                      S/N: {c.serial_number || "—"} · Mfr: {c.manufacturer || "—"} · Model: {c.model || "—"}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRemoveComponent(c.id)}
                    className="ac-button-secondary"
                    style={{ fontSize: "0.75rem", color: "var(--ac-status-non-compliant)" }}
                  >
                    Remove
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No components currently registered as installed.</p>
          )}
        </div>
      )}

      {/* TAB 5: MAINTENANCE */}
      {activeTab === "MAINTENANCE" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="ac-card" style={{ padding: 20 }}>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", fontWeight: 700 }}>Due Maintenance Requirements</h3>
            {maintenance?.due_items && maintenance.due_items.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {maintenance.due_items.map((item, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "10px 14px",
                      background: "var(--ac-bg-surface-hover)",
                      borderRadius: 6,
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "0.85rem",
                    }}
                  >
                    <div>
                      <strong>{item.title}</strong>
                      <div style={{ color: "var(--ac-text-secondary)", marginTop: 2 }}>
                        Interval: {item.interval_hours ? `${item.interval_hours} hrs` : "Calendar"} · Next Due: {item.next_due_hours ? `${item.next_due_hours} hrs` : "Scheduled"}
                      </div>
                    </div>
                    <span style={{ color: "var(--ac-accent)", fontWeight: 600 }}>{item.status || "UPCOMING"}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No maintenance items currently scheduled or due.</p>
            )}
          </div>

          <div className="ac-card" style={{ padding: 20 }}>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", fontWeight: 700 }}>Open Work Orders</h3>
            {maintenance?.open_work_orders && maintenance.open_work_orders.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {maintenance.open_work_orders.map((wo, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "10px 14px",
                      background: "var(--ac-bg-surface-hover)",
                      borderRadius: 6,
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: "0.85rem",
                    }}
                  >
                    <div>
                      <strong>{wo.title}</strong>
                      <div style={{ color: "var(--ac-text-secondary)", marginTop: 2 }}>
                        Priority: {wo.priority || "NORMAL"} · Status: {wo.status}
                      </div>
                    </div>
                    <Link href="/maintenance/work-orders" className="ac-link" style={{ fontSize: "0.8rem" }}>
                      View in MRO →
                    </Link>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No active work orders open for this airframe.</p>
            )}
          </div>
        </div>
      )}

      {/* TAB 6: INSPECTIONS */}
      {activeTab === "INSPECTIONS" && (
        <div className="ac-card" style={{ padding: 20 }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", fontWeight: 700 }}>Airframe Inspection History</h3>
          {inspections?.inspections && inspections.inspections.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {inspections.inspections.map((insp, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "12px 16px",
                    background: "var(--ac-bg-surface-hover)",
                    borderRadius: 8,
                    border: "1px solid var(--ac-border)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <strong style={{ fontSize: "0.95rem" }}>{insp.title}</strong>
                    <div style={{ color: "var(--ac-text-secondary)", fontSize: "0.8rem", marginTop: 2 }}>
                      Inspector: {insp.inspector || "Unassigned"} · Signed: {insp.signed_at ? new Date(insp.signed_at).toLocaleDateString() : "Pending"}
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      padding: "4px 8px",
                      borderRadius: 4,
                      background: insp.status === "COMPLETED" ? "rgba(16, 185, 129, 0.2)" : "rgba(245, 158, 11, 0.2)",
                      color: insp.status === "COMPLETED" ? "var(--ac-status-compliant)" : "var(--ac-status-review)",
                    }}
                  >
                    {insp.status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No inspection records recorded.</p>
          )}
        </div>
      )}

      {/* TAB 7: EVIDENCE */}
      {activeTab === "EVIDENCE" && (
        <div className="ac-card" style={{ padding: 20 }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", fontWeight: 700 }}>Authoritative Airframe Evidence Files</h3>
          <p style={{ color: "var(--ac-text-secondary)", fontSize: "0.85rem", marginBottom: 16 }}>
            Tenant-scoped regulatory certificates, weight and balance schedules, and non-destructive testing (NDT) logs.
          </p>
          {evidence?.evidence_items && evidence.evidence_items.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {evidence.evidence_items.map((ev, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "12px 16px",
                    background: "var(--ac-bg-surface-hover)",
                    borderRadius: 8,
                    border: "1px solid var(--ac-border)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <strong style={{ fontSize: "0.95rem" }}>{ev.title}</strong>
                    <div style={{ color: "var(--ac-text-secondary)", fontSize: "0.8rem", marginTop: 2 }}>
                      File: {ev.file_name} · Reviewed by: {ev.reviewed_by || "Pending Review"}
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      padding: "4px 8px",
                      borderRadius: 4,
                      background: ev.status === "ACCEPTED" ? "rgba(16, 185, 129, 0.2)" : "rgba(245, 158, 11, 0.2)",
                      color: ev.status === "ACCEPTED" ? "var(--ac-status-compliant)" : "var(--ac-status-review)",
                    }}
                  >
                    {ev.status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No evidence files attached.</p>
          )}
        </div>
      )}

      {/* TAB 8: FINDINGS */}
      {activeTab === "FINDINGS" && (
        <div className="ac-card" style={{ padding: 20 }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", fontWeight: 700 }}>Discrepancies & Findings</h3>
          {findings?.findings && findings.findings.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {findings.findings.map((f, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "12px 16px",
                    background: "var(--ac-bg-surface-hover)",
                    borderRadius: 8,
                    border: "1px solid var(--ac-border)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <strong style={{ fontSize: "0.95rem" }}>{f.title}</strong>
                      <span style={{ fontSize: "0.75rem", background: "var(--ac-border)", padding: "2px 6px", borderRadius: 4 }}>
                        Severity: {f.severity}
                      </span>
                    </div>
                    <div style={{ color: "var(--ac-text-secondary)", fontSize: "0.8rem", marginTop: 2 }}>
                      Discovered: {f.discovered_at ? new Date(f.discovered_at).toLocaleDateString() : "—"}
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      padding: "4px 8px",
                      borderRadius: 4,
                      background: f.status === "OPEN" ? "rgba(239, 68, 68, 0.2)" : "rgba(16, 185, 129, 0.2)",
                      color: f.status === "OPEN" ? "var(--ac-status-non-compliant)" : "var(--ac-status-compliant)",
                    }}
                  >
                    {f.status}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No discrepancies or findings recorded.</p>
          )}
        </div>
      )}

      {/* TAB 9: COMPLIANCE */}
      {activeTab === "COMPLIANCE" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div
            style={{
              padding: "12px 16px",
              background: "rgba(56, 189, 248, 0.08)",
              border: "1px solid rgba(56, 189, 248, 0.3)",
              borderRadius: 8,
              fontSize: "0.85rem",
              color: "var(--ac-accent)",
            }}
          >
            <strong>AeroComply Authority Disclosure:</strong> Regulatory determinations require human authority. AI intelligence engines provide advisory context and do NOT have write authority over authoritative compliance rules.
          </div>

          <div className="ac-card" style={{ padding: 20 }}>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", fontWeight: 700 }}>Regulatory Assessments</h3>
            {compliance?.assessments && compliance.assessments.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {compliance.assessments.map((c, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "12px 16px",
                      background: "var(--ac-bg-surface-hover)",
                      borderRadius: 8,
                      border: "1px solid var(--ac-border)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: "0.75rem", background: "var(--ac-border)", padding: "2px 6px", borderRadius: 4 }}>
                          {c.regulatory_code}
                        </span>
                        <strong style={{ fontSize: "0.95rem" }}>{c.title}</strong>
                      </div>
                      <div style={{ color: "var(--ac-text-secondary)", fontSize: "0.8rem", marginTop: 2 }}>
                        Assessed by: {c.assessed_by || "Qualified Inspector"} · Date: {c.assessed_at ? new Date(c.assessed_at).toLocaleDateString() : "—"}
                      </div>
                    </div>
                    <span
                      style={{
                        fontSize: "0.75rem",
                        fontWeight: 700,
                        padding: "4px 8px",
                        borderRadius: 4,
                        background: c.determination === "COMPLIANT" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                        color: c.determination === "COMPLIANT" ? "var(--ac-status-compliant)" : "var(--ac-status-non-compliant)",
                      }}
                    >
                      {c.determination}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No regulatory assessments recorded for this airframe.</p>
            )}
          </div>
        </div>
      )}

      {/* TAB 10: READINESS */}
      {activeTab === "READINESS" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div
            style={{
              padding: "12px 16px",
              background: "rgba(245, 158, 11, 0.08)",
              border: "1px solid rgba(245, 158, 11, 0.3)",
              borderRadius: 8,
              fontSize: "0.85rem",
              color: "var(--ac-status-review)",
            }}
          >
            <strong>Limitation of Scope:</strong> {readiness?.disclaimer || "Operational readiness evaluation only. Does not constitute an electronic Release to Service (RTS) signature."}
          </div>

          <div className="ac-card" style={{ padding: 20 }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: "1.1rem", fontWeight: 700 }}>5-Dimension Readiness Evaluation</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {readiness?.dimensions && readiness.dimensions.length > 0 ? (
                readiness.dimensions.map((dim, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "14px 18px",
                      background: "var(--ac-bg-surface-hover)",
                      borderRadius: 8,
                      border: "1px solid var(--ac-border)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <strong style={{ fontSize: "0.95rem" }}>{dim.dimension} READINESS</strong>
                      <span
                        style={{
                          fontSize: "0.75rem",
                          fontWeight: 700,
                          padding: "4px 8px",
                          borderRadius: 4,
                          background: dim.status === "READY" ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)",
                          color: dim.status === "READY" ? "var(--ac-status-compliant)" : "var(--ac-status-non-compliant)",
                        }}
                      >
                        {dim.status}
                      </span>
                    </div>
                    <p style={{ margin: "6px 0 0 0", color: "var(--ac-text-secondary)", fontSize: "0.85rem" }}>
                      {dim.summary}
                    </p>
                    {dim.blockers && dim.blockers.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        <span style={{ fontSize: "0.75rem", color: "var(--ac-status-non-compliant)", fontWeight: 600 }}>Active Blockers:</span>
                        <ul style={{ margin: "4px 0 0 16px", padding: 0, fontSize: "0.8rem", color: "var(--ac-status-non-compliant)" }}>
                          {dim.blockers.map((b, bIdx) => (
                            <li key={bIdx}>{b}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No readiness evaluation available.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* TAB 11: HISTORY */}
      {activeTab === "HISTORY" && (
        <div className="ac-card" style={{ padding: 20 }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", fontWeight: 700 }}>Unified Airframe History & Audit Trail</h3>
          <p style={{ color: "var(--ac-text-secondary)", fontSize: "0.85rem", marginBottom: 16 }}>
            Chronological log of airframe registration, component lifecycle events, flights, and maintenance records.
          </p>
          {history?.events && history.events.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {history.events.map((ev) => (
                <div
                  key={ev.event_id}
                  style={{
                    padding: "12px 16px",
                    background: "var(--ac-bg-surface-hover)",
                    borderRadius: 8,
                    border: "1px solid var(--ac-border)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <strong style={{ fontSize: "0.95rem" }}>{ev.title}</strong>
                      <span style={{ fontSize: "0.7rem", color: "var(--ac-text-secondary)" }}>[{ev.event_type}]</span>
                    </div>
                    <div style={{ color: "var(--ac-text-secondary)", fontSize: "0.85rem", marginTop: 2 }}>
                      {ev.description}
                    </div>
                    {ev.actor && (
                      <div style={{ color: "var(--ac-text-secondary)", fontSize: "0.75rem", marginTop: 4 }}>
                        By: {ev.actor}
                      </div>
                    )}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--ac-text-secondary)", whiteSpace: "nowrap" }}>
                    {new Date(ev.occurred_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No historical events recorded for this airframe.</p>
          )}
        </div>
      )}

      {/* TAB 12: INTELLIGENCE (D2.2 -- M4.3) */}
      {activeTab === "INTELLIGENCE" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {sessionType === "DEMO" ? (
            <div
              style={{
                padding: "12px 16px",
                background: "rgba(245, 158, 11, 0.08)",
                border: "1px solid rgba(245, 158, 11, 0.3)",
                borderRadius: 8,
                fontSize: "0.85rem",
                color: "var(--ac-status-review)",
              }}
            >
              The D2.2 Intelligence layer (readiness, risk, priority, decision,
              recommendation) is not available in demo mode. Sign in to a real
              organization to view it.
            </div>
          ) : (
            <>
              <div
                style={{
                  padding: "12px 16px",
                  background: "rgba(56, 189, 248, 0.08)",
                  border: "1px solid rgba(56, 189, 248, 0.3)",
                  borderRadius: 8,
                  fontSize: "0.85rem",
                  color: "var(--ac-accent)",
                }}
              >
                <strong>Deterministic Intelligence:</strong> Every value below is computed by
                the backend (readiness → risk → priority → decision → recommendation). This
                page only labels and formats that output — it never re-derives it.
              </div>

              {/* M7 Proactive Intelligence Signals for Asset */}
              <ProactiveSignalsSection
                signals={assetSignals}
                accessToken={accessToken}
                assetId={assetId}
                onSignalUpdated={refreshAssetSignals}
                title="Active Airframe Proactive Signals"
                subtitle="Live degradation trends, recurring defect patterns, and early-warning proximity triggers for this asset."
              />

              {/* Phase C: live telemetry (latest values, quality, age, flights) */}
              {hasFeature("flight_telemetry") && (
                <div className="ac-card" style={{ padding: 20 }}>
                  <h3 style={{ margin: "0 0 12px", fontSize: "1.1rem", fontWeight: 700 }}>Telemetry</h3>
                  <TelemetryPanel assetId={assetId} accessToken={accessToken} />
                </div>
              )}

              {/* H1: HUMS Foundation Health */}
              {hasFeature("hums") && (
                <div className="ac-card" style={{ padding: 20 }}>
                  <h3 style={{ margin: "0 0 12px", fontSize: "1.1rem", fontWeight: 700 }}>HUMS Health</h3>
                  <HUMSHealthPanel health={humsHealth} accessToken={accessToken} />
                  <div style={{ marginTop: 16, borderTop: "1px solid var(--ac-border)", paddingTop: 16 }}>
                    <HUMSHealthIntelligencePanel assetId={assetId} accessToken={accessToken} />
                  </div>
                  <div style={{ marginTop: 16, borderTop: "1px solid var(--ac-border)", paddingTop: 16 }}>
                    <div style={{ fontSize: 12, color: "var(--ac-text-secondary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
                      HUMS Diagnostics
                    </div>
                    <HUMSDiagnosticsPanel assetId={assetId} accessToken={accessToken} canWrite />
                  </div>
                  {/* Backend gates prognostics (RUL) behind predictive_maintenance as well as hums;
                      showing the panel without it would only render a 403. */}
                  {hasFeature("predictive_maintenance") && (
                    <div style={{ marginTop: 16, borderTop: "1px solid var(--ac-border)", paddingTop: 16 }}>
                      <div style={{ fontSize: 12, color: "var(--ac-text-secondary)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 0.5 }}>
                        HUMS Prognostics (Remaining Useful Life)
                      </div>
                      <HUMSPrognosticsPanel assetId={assetId} accessToken={accessToken} />
                    </div>
                  )}
                </div>
              )}

              {/* Digital Twin */}
              {hasFeature("digital_twin") && (
                <div className="ac-card" style={{ padding: 20 }}>
                  <h3 style={{ margin: "0 0 12px", fontSize: "1.1rem", fontWeight: 700 }}>Digital Twin</h3>
                  <DigitalTwinPanel assetId={assetId} accessToken={accessToken} />
                </div>
              )}

              {/* H7: MRO + Compliance + Readiness Intelligence Integration */}
              {hasFeature("mro_intelligence") && (
                <div className="ac-card" style={{ padding: 20 }}>
                  <h3 style={{ margin: "0 0 12px", fontSize: "1.1rem", fontWeight: 700 }}>
                    MRO + Compliance + Readiness Intelligence (H7)
                  </h3>
                  <MROIntelligencePanel assetId={assetId} accessToken={accessToken} canWrite />
                </div>
              )}

              {/* READINESS */}
              <div className="ac-card" style={{ padding: 20 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Readiness</h3>
                  {intelReadiness && <StatusBadge {...intelligenceReadinessBadge(intelReadiness.readiness_state)} />}
                </div>

                {intelReadiness ? (
                  <>
                    <p style={{ margin: "0 0 10px 0", color: "var(--ac-text-secondary)", fontSize: "0.85rem" }}>
                      {intelReadiness.explanation.join(" ")}
                    </p>
                    {intelReadiness.blockers.length > 0 && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        <span style={{ fontSize: "0.75rem", color: "var(--ac-status-non-compliant)", fontWeight: 600 }}>
                          Blockers ({intelReadiness.blockers.length}):
                        </span>
                        {intelReadiness.blockers.map((b, idx) => (
                          <div
                            key={idx}
                            style={{ padding: "8px 12px", background: "var(--ac-bg-surface-hover)", borderRadius: 6, fontSize: "0.8rem" }}
                          >
                            <span style={{ color: "var(--ac-text-secondary)" }}>[{b.source_domain}] </span>
                            {b.description}
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>Readiness intelligence unavailable.</p>
                )}
              </div>

              {/* RISK */}
              <div className="ac-card" style={{ padding: 20 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Risk</h3>
                  {intelRisk && <StatusBadge {...intelligenceRiskLevelBadge(intelRisk.risk_level)} />}
                </div>
                {intelRisk ? (
                  <>
                    <p style={{ margin: "0 0 10px 0", color: "var(--ac-text-secondary)", fontSize: "0.85rem" }}>
                      {intelRisk.explanation.join(" ")}
                    </p>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 8 }}>
                      {intelRisk.factors.map((f) => (
                        <div key={f.name} style={{ padding: "8px 12px", background: "var(--ac-bg-surface-hover)", borderRadius: 6 }}>
                          <div style={{ fontSize: "0.7rem", color: "var(--ac-text-secondary)", textTransform: "uppercase" }}>{f.name}</div>
                          <div style={{ fontSize: "0.85rem", fontWeight: 700, marginTop: 2 }}>{f.value}</div>
                          <div style={{ fontSize: "0.75rem", color: "var(--ac-text-secondary)", marginTop: 2 }}>{f.explanation}</div>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>Risk intelligence unavailable.</p>
                )}
              </div>

              {/* PRIORITY */}
              <div className="ac-card" style={{ padding: 20 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Priority</h3>
                  {intelPriority && <StatusBadge {...intelligenceRiskLevelBadge(intelPriority.priority_level)} />}
                </div>
                {intelPriority ? (
                  <>
                    <p style={{ margin: "0 0 6px 0", color: "var(--ac-text-secondary)", fontSize: "0.85rem" }}>
                      {intelPriority.explanation.join(" ")}
                    </p>
                    {intelPriority.escalated && (
                      <p style={{ margin: 0, color: "var(--ac-status-review)", fontSize: "0.8rem" }}>
                        ⚠ Escalated from base risk level ({intelPriority.blocker_count} concurrent blocker(s)).
                      </p>
                    )}
                  </>
                ) : (
                  <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>Priority intelligence unavailable.</p>
                )}
              </div>

              {/* DECISION */}
              <div className="ac-card" style={{ padding: 20 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Decision</h3>
                  {intelDecision && <StatusBadge {...intelligenceDecisionBadge(intelDecision.decision_state)} />}
                </div>
                {intelDecision ? (
                  <>
                    <p style={{ margin: "0 0 10px 0", color: "var(--ac-text-secondary)", fontSize: "0.85rem" }}>
                      {intelDecision.decision_reason}
                    </p>
                    {intelDecision.required_information.length > 0 && (
                      <div>
                        <span style={{ fontSize: "0.75rem", color: "var(--ac-status-review)", fontWeight: 600 }}>
                          Required Information:
                        </span>
                        <ul style={{ margin: "4px 0 0 16px", padding: 0, fontSize: "0.8rem", color: "var(--ac-status-review)" }}>
                          {intelDecision.required_information.map((info, idx) => (
                            <li key={idx}>{info}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                ) : (
                  <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>Decision intelligence unavailable.</p>
                )}
              </div>

              {/* RECOMMENDATION */}
              <div className="ac-card" style={{ padding: 20 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
                  <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700 }}>Recommendation</h3>
                  {intelRecommendation && (
                    <StatusBadge {...intelligenceDecisionBadge(intelRecommendation.recommendation_state)} />
                  )}
                </div>
                {intelRecommendation && intelRecommendation.items.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {intelRecommendation.items.map((item, idx) => (
                      <div
                        key={idx}
                        style={{ padding: "12px 16px", background: "var(--ac-bg-surface-hover)", borderRadius: 8, border: "1px solid var(--ac-border)" }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                          <span
                            style={{
                              fontSize: "0.7rem",
                              background: "var(--ac-border)",
                              padding: "2px 6px",
                              borderRadius: 4,
                              textTransform: "uppercase",
                            }}
                          >
                            {item.action_category.replace(/_/g, " ")}
                          </span>
                        </div>
                        <div style={{ fontSize: "0.9rem", color: "var(--ac-text-primary)" }}>{item.action}</div>
                        {item.resolution_condition && (
                          <div style={{ fontSize: "0.8rem", color: "var(--ac-text-secondary)", marginTop: 4 }}>
                            Resolution: {item.resolution_condition}
                          </div>
                        )}
                        {item.source_blocker && (
                          <div style={{ fontSize: "0.75rem", color: "var(--ac-text-muted)", marginTop: 6 }}>
                            Source: {item.source_blocker.related_record_type ?? item.source_blocker.source_domain}
                            {item.source_blocker.related_record_id ? ` #${item.source_blocker.related_record_id.slice(0, 8)}` : ""}
                            {item.source_blocker.regulatory_reference ? ` · ${item.source_blocker.regulatory_reference}` : ""}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                ) : (
                  <p style={{ color: "var(--ac-text-secondary)", fontStyle: "italic" }}>No recommendation available.</p>
                )}
              </div>

              {/* TRACEABILITY */}
              {intelRecommendation && intelRecommendation.blockers.length > 0 && (
                <div className="ac-card" style={{ padding: 20 }}>
                  <h3 style={{ margin: "0 0 12px 0", fontSize: "1.1rem", fontWeight: 700 }}>Source Traceability</h3>
                  <p style={{ margin: "0 0 12px 0", color: "var(--ac-text-secondary)", fontSize: "0.85rem" }}>
                    Every blocker below traces back to a real backend record — never an
                    unsupported or invented explanation.
                  </p>
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {intelRecommendation.blockers.map((b, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: "10px 14px",
                          background: "var(--ac-bg-surface-hover)",
                          borderRadius: 6,
                          fontSize: "0.8rem",
                          display: "flex",
                          flexDirection: "column",
                          gap: 2,
                        }}
                      >
                        <div>
                          <strong>{b.category}</strong>
                          <span style={{ color: "var(--ac-text-secondary)" }}> — {b.description}</span>
                        </div>
                        <div style={{ color: "var(--ac-text-muted)" }}>
                          {b.related_record_type ?? b.source_domain}
                          {b.related_record_id ? ` #${b.related_record_id.slice(0, 8)}` : ""}
                          {b.regulatory_reference ? ` · ${b.regulatory_reference}` : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Install Component Modal */}
      <InstallComponentModal
        isOpen={isInstallModalOpen}
        onClose={() => setIsInstallModalOpen(false)}
        onSubmit={handleInstallComponent}
      />

      {/* Log Flight Modal */}
      <LogFlightModal
        isOpen={isLogFlightModalOpen}
        onClose={() => setIsLogFlightModalOpen(false)}
        onSubmit={handleLogFlight}
      />
    </div>
  );
}
