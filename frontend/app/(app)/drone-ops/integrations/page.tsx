import { DroneOpsStubPage } from "@/components/drone-ops/DroneOpsStubPage";
export default function IntegrationsPage() {
  return (
    <DroneOpsStubPage
      icon="◫"
      title="Drone Integrations"
      subtitle="MAVLink, Ground Control Software, and hardware integrations"
      milestone="Milestone A6 — Customer Onboarding & Backend Integration"
      description="Set up and manage integrations between your drone hardware, ground control software, and the Kota Aerospace platform. The guided onboarding flow walks you through drone enrollment, MAVLink configuration, and connectivity verification."
      capabilities={[
        "MAVLink / MAVProxy connection setup and diagnostics",
        "Guided drone enrollment workflow",
        "Integration health monitoring",
        "QGroundControl and Mission Planner compatibility",
        "API key management for direct integrations",
        "Telemetry format and field mapping configuration",
        "Integration test suite and validation reports",
      ]}
    />
  );
}
