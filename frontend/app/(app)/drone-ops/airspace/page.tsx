import { DroneOpsStubPage } from "@/components/drone-ops/DroneOpsStubPage";
export default function AirspacePage() {
  return (
    <DroneOpsStubPage
      icon="§"
      title="Airspace & Compliance"
      subtitle="Geofence management, restricted zones, and regulatory compliance"
      milestone="Milestone A3 — Interactive Map & Mission Visualization"
      description="Define and monitor geofences, restricted airspace zones, and caution areas. Track compliance with airspace authorizations per mission and verify that all flights operate within approved boundaries."
      capabilities={[
        "Geofence definition and management",
        "Restricted and caution zone overlays on the live map",
        "Geofence breach detection and alerting",
        "Airspace authorization per mission",
        "Regulatory compliance tracking",
        "Integration with NOTAM and airspace data sources",
        "Export and reporting for regulatory submissions",
      ]}
    />
  );
}
