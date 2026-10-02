import { DroneOpsStubPage } from "@/components/drone-ops/DroneOpsStubPage";
export default function CopilotPage() {
  return (
    <DroneOpsStubPage
      icon="✦"
      title="LISA Copilot"
      subtitle="AI-powered operational intelligence for drone fleet management"
      milestone="Milestone A5 — LISA Copilot Experience"
      description="LISA provides contextual operational summaries, proactive alerts, and answers to fleet questions. Evidence behind every explanation is linked to source telemetry and mission records. Predictions are always labeled as estimates — confirmed telemetry is clearly distinguished from LISA's interpretations."
      capabilities={[
        "Persistent LISA panel accessible from any drone-ops page",
        "Contextual question suggestions based on current fleet state",
        "Conversational interface with evidence links",
        "Current fleet summary and operational event explanations",
        "Confidence indicators for predictions and estimates",
        "Proactive notification of operational anomalies",
        "Fleet context awareness (active missions, alerts, health)",
        "Optional speech playback if product-compatible",
      ]}
    />
  );
}
