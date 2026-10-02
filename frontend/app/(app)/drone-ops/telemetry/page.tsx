import { DroneOpsStubPage } from "@/components/drone-ops/DroneOpsStubPage";
export default function TelemetryPage() {
  return (
    <DroneOpsStubPage
      icon="⇄"
      title="Connectivity & Telemetry"
      subtitle="MAVLink telemetry streams, connection health, and data quality"
      milestone="Milestone A2 — Live Fleet Overview & Drone Details"
      description="Monitor the health of every drone's telemetry link. View signal quality, data latency, packet loss rates, and connection history. Diagnose connectivity issues and configure MAVLink integration endpoints."
      capabilities={[
        "Per-drone connection status and RSSI monitoring",
        "MAVLink telemetry stream visualization",
        "Packet loss and latency metrics",
        "Data freshness and staleness indicators",
        "Integration diagnostics and setup workflow",
        "WebSocket / SSE connection state display",
        "Telemetry history and gap detection",
      ]}
    />
  );
}
