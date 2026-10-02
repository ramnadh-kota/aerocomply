import { DroneOpsStubPage } from "@/components/drone-ops/DroneOpsStubPage";
export default function AlertsPage() {
  return (
    <DroneOpsStubPage
      icon="🔔"
      title="Alerts & Events"
      subtitle="Operational alert management and event history"
      milestone="Milestone A4 — Missions, Alerts & Flight History"
      description="Full alert management center. Filter, acknowledge, and investigate operational events across the entire drone fleet. Access complete event history with severity filters, time ranges, and per-drone scoping."
      capabilities={[
        "Full event history with severity and time filters",
        "Bulk acknowledgment and alert assignment",
        "Event detail view with evidence references",
        "Per-drone event scoping",
        "Alert escalation and notification rules",
        "Integration with backend operational event API",
        "Real-time alert stream via WebSocket/SSE",
      ]}
    />
  );
}
