import { DroneOpsStubPage } from "@/components/drone-ops/DroneOpsStubPage";
export default function MissionsPage() {
  return (
    <DroneOpsStubPage
      icon="◔"
      title="Missions & Routes"
      subtitle="Mission planning, authorization, and progress tracking"
      milestone="Milestone A4 — Missions, Alerts & Flight History"
      description="Plan and monitor drone missions from pre-flight authorization through waypoint completion. View active and historical mission records, authorize planned missions, and track waypoint progress in real time."
      capabilities={[
        "Mission creation with waypoints and operating area",
        "Pre-flight authorization workflow",
        "Waypoint progress tracking and completion timeline",
        "Mission handoff visualization",
        "Flight event timeline per mission",
        "Mission history and status filters",
        "Integration with the Live Fleet Map for route overlay",
      ]}
    />
  );
}
