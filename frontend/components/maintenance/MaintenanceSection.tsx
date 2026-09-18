"use client";

// M17.4C/M17.5C — usage-based maintenance for a Drone, Battery, or
// Component. Real backend data only (GET .../maintenance-due); this
// component never computes due status, remaining usage, thresholds, or
// lifetime usage itself -- the backend (app/services/maintenance_service.py)
// is authoritative. Asset-generic naming and props (not
// "DroneMaintenance...") -- the parent supplies which target's API calls
// to use (dronesApi.getMaintenanceDue / getBatteryMaintenanceDue /
// getComponentMaintenanceDue and their applicability/accomplishment
// counterparts), so this one component serves all three without
// duplicating the rendering/interaction logic.

import { useState } from "react";
import { StatusBadge, maintenanceDueStatusBadge } from "@/components/status/StatusBadge";
import { normalizeApiError, type NormalizedApiError } from "@/lib/apiClient";
import { type MaintenanceDueItem, type MaintenanceIntervalType } from "@/lib/api/drones";

const _HOURS_METRICS = new Set(["FLIGHT_HOURS", "COMPONENT_HOURS"]);

function formatUsage(item: MaintenanceDueItem): string | null {
  if (item.current_usage == null) return null;
  const isHours = _HOURS_METRICS.has(item.requirement.interval_type);
  const threshold = isHours ? item.requirement.fh_interval : item.requirement.fc_interval;
  const unit = isHours ? "hours" : "cycles";
  if (threshold == null) return null;
  return `${item.current_usage.toFixed(1)} / ${threshold} ${unit} (since last maintenance)`;
}

function formatLifetimeUsage(item: MaintenanceDueItem): string | null {
  if (item.lifetime_usage == null) return null;
  const unit = _HOURS_METRICS.has(item.requirement.interval_type) ? "hours" : "cycles";
  return `${item.lifetime_usage.toFixed(1)} ${unit} lifetime`;
}

function MaintenanceItemCard({
  item,
  canWrite,
  onAccomplished,
}: {
  item: MaintenanceDueItem;
  canWrite: boolean;
  onAccomplished: (requirementId: string) => void;
}) {
  const badge = maintenanceDueStatusBadge(item.due_status);
  const usage = formatUsage(item);
  const [recording, setRecording] = useState(false);

  return (
    <div className="ac-card" style={{ padding: 10 }}>
      <div className="ac-flex ac-justify-between" style={{ alignItems: "center", flexWrap: "wrap", gap: 8 }}>
        <span className="ac-text-sm" style={{ fontWeight: 600 }}>
          {item.requirement.description}
        </span>
        <StatusBadge status={badge.status} label={badge.label} />
      </div>
      {usage && <div className="ac-text-sm ac-text-muted" style={{ marginTop: 4 }}>{usage}</div>}
      {item.remaining_usage != null && (
        <div className="ac-text-sm ac-text-muted">{item.remaining_usage.toFixed(1)} remaining</div>
      )}
      {formatLifetimeUsage(item) && (
        <div className="ac-text-sm ac-text-muted">{formatLifetimeUsage(item)}</div>
      )}
      {item.due_date && (
        <div className="ac-text-sm ac-text-muted">Due {new Date(item.due_date).toLocaleDateString()}</div>
      )}
      <div className="ac-text-sm ac-text-muted" style={{ marginTop: 4 }}>{item.reason}</div>
      {item.last_accomplished_at && (
        <div className="ac-text-sm ac-text-muted">
          Last accomplished {new Date(item.last_accomplished_at).toLocaleDateString()}
        </div>
      )}
      {canWrite && (
        <button
          className="ac-btn"
          style={{ marginTop: 8 }}
          disabled={recording}
          onClick={() => {
            setRecording(true);
            Promise.resolve(onAccomplished(item.requirement.id)).finally(() => setRecording(false));
          }}
        >
          {recording ? "Recording…" : "Mark Accomplished"}
        </button>
      )}
    </div>
  );
}

export interface MaintenanceRequirementDraft {
  description: string;
  ata_chapter: string;
  interval_type: MaintenanceIntervalType;
  fh_interval: number | null;
  fc_interval: number | null;
  calendar_interval_days: number | null;
}

export function MaintenanceSection({
  items,
  loading,
  error,
  canWrite,
  intervalOptions,
  emptyMessage = "No maintenance rules configured yet.",
  onCreateAndLink,
  onAccomplish,
}: {
  items: MaintenanceDueItem[];
  loading: boolean;
  error: NormalizedApiError | null;
  canWrite: boolean;
  // M17.5C: which interval types make sense for this target -- a Drone
  // offers FLIGHT_HOURS/FLIGHT_CYCLES/CALENDAR, a Battery only
  // BATTERY_CYCLES, a Component COMPONENT_HOURS/COMPONENT_CYCLES. Never
  // let the UI offer a combination the backend would reject.
  intervalOptions: { value: MaintenanceIntervalType; label: string }[];
  emptyMessage?: string;
  onCreateAndLink: (draft: MaintenanceRequirementDraft) => Promise<unknown>;
  onAccomplish: (requirementId: string) => Promise<unknown>;
}) {
  const [description, setDescription] = useState("");
  const [ataChapter, setAtaChapter] = useState("");
  const [intervalType, setIntervalType] = useState<MaintenanceIntervalType>(
    intervalOptions[0]?.value ?? "FLIGHT_HOURS"
  );
  const [thresholdValue, setThresholdValue] = useState("");
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<NormalizedApiError | null>(null);

  const hoursTypes = new Set(["FLIGHT_HOURS", "COMPONENT_HOURS"]);
  const calendarTypes = new Set(["CALENDAR"]);

  const createAndLinkRequirement = () => {
    if (!description.trim() || !ataChapter.trim() || !thresholdValue.trim()) return;
    setCreating(true);
    setCreateError(null);
    const threshold = Number(thresholdValue);
    onCreateAndLink({
      description: description.trim(),
      ata_chapter: ataChapter.trim(),
      interval_type: intervalType,
      fh_interval: hoursTypes.has(intervalType) ? threshold : null,
      fc_interval:
        !hoursTypes.has(intervalType) && !calendarTypes.has(intervalType) ? threshold : null,
      calendar_interval_days: calendarTypes.has(intervalType) ? threshold : null,
    })
      .then(() => {
        setDescription("");
        setAtaChapter("");
        setThresholdValue("");
      })
      .catch((err) => setCreateError(normalizeApiError(err)))
      .finally(() => setCreating(false));
  };

  const recordAccomplishment = (requirementId: string) =>
    onAccomplish(requirementId).catch((err) => setCreateError(normalizeApiError(err)));

  if (loading) {
    return <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>Loading maintenance status…</p>;
  }
  if (error) {
    return (
      <p className="ac-text-sm" style={{ margin: 0, color: "var(--ac-status-non-compliant)" }}>
        {error.message}
      </p>
    );
  }

  return (
    <div>
      {items.length === 0 ? (
        <p className="ac-text-sm ac-text-muted" style={{ margin: 0 }}>
          {emptyMessage}
        </p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {items.map((item) => (
            <MaintenanceItemCard
              key={item.requirement.id}
              item={item}
              canWrite={canWrite}
              onAccomplished={recordAccomplishment}
            />
          ))}
        </div>
      )}

      {canWrite && (
        <div style={{ marginTop: 14, paddingTop: 14, borderTop: "1px solid var(--ac-border)" }}>
          <span className="ac-text-sm ac-text-muted" style={{ fontWeight: 600 }}>
            Add Maintenance Rule
          </span>
          <div className="ac-flex ac-gap-2" style={{ flexWrap: "wrap", marginTop: 8 }}>
            <input
              className="ac-input"
              style={{ width: 180 }}
              placeholder="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              aria-label="Maintenance rule description"
            />
            <input
              className="ac-input"
              style={{ width: 100 }}
              placeholder="ATA chapter"
              value={ataChapter}
              onChange={(e) => setAtaChapter(e.target.value)}
              aria-label="ATA chapter"
            />
            <select
              className="ac-input"
              style={{ width: 140 }}
              value={intervalType}
              onChange={(e) => setIntervalType(e.target.value as MaintenanceIntervalType)}
              aria-label="Interval type"
            >
              {intervalOptions.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
            <input
              className="ac-input"
              style={{ width: 100 }}
              placeholder="Interval"
              value={thresholdValue}
              onChange={(e) => setThresholdValue(e.target.value.replace(/\D/g, ""))}
              aria-label="Interval value"
            />
            <button
              className="ac-btn"
              onClick={createAndLinkRequirement}
              disabled={creating || !description.trim() || !ataChapter.trim() || !thresholdValue.trim()}
            >
              {creating ? "Adding…" : "Add Rule"}
            </button>
          </div>
          {createError && (
            <p className="ac-text-sm" style={{ margin: "8px 0 0", color: "var(--ac-status-non-compliant)" }}>
              {createError.message}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
