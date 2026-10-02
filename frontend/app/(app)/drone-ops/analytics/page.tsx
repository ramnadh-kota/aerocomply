import { DroneOpsStubPage } from "@/components/drone-ops/DroneOpsStubPage";
export default function AnalyticsPage() {
  return (
    <DroneOpsStubPage
      icon="▦"
      title="Analytics & Reports"
      subtitle="Fleet performance, utilization, and operational analytics"
      milestone="Milestone A6 — Customer Onboarding & Backend Integration"
      description="Comprehensive reporting across the drone fleet. Flight hour utilization, battery cycle trends, mission success rates, maintenance cost analysis, and operator performance summaries — all scoped to your organization."
      capabilities={[
        "Fleet utilization reports (flight hours, cycles, missions)",
        "Battery health trend analytics",
        "Mission completion and abort rate analysis",
        "Operator performance summaries",
        "Maintenance cost and schedule adherence tracking",
        "Exportable reports (PDF, CSV)",
        "Custom date range and per-drone scoping",
      ]}
    />
  );
}
