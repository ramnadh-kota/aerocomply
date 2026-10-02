import { DroneOpsStubPage } from "@/components/drone-ops/DroneOpsStubPage";
export default function MaintenancePage() {
  return (
    <DroneOpsStubPage
      icon="⛭"
      title="Maintenance"
      subtitle="Drone-specific maintenance scheduling and work order management"
      milestone="Milestone A2 — Live Fleet Overview & Drone Details"
      description="Manage maintenance schedules, work orders, and accomplishment records for every drone, battery, and component in your fleet. Usage-based maintenance tracking ensures nothing falls overdue based on actual flight hours and cycles."
      capabilities={[
        "Usage-based maintenance due items (flight hours, cycles, calendar)",
        "Battery and component maintenance scheduling",
        "Maintenance accomplishment recording",
        "Work order integration for drone fleet",
        "Pre-flight maintenance clearance status",
        "Maintenance history per drone and component",
        "Links to existing /drones/[id] maintenance records",
      ]}
    />
  );
}
