import { DroneOpsStubPage } from "@/components/drone-ops/DroneOpsStubPage";
export default function LiveFleetMapPage() {
  return (
    <DroneOpsStubPage
      icon="◉"
      title="Live Fleet Map"
      subtitle="Interactive geospatial drone fleet visualization"
      milestone="Milestone A3 — Interactive Map & Mission Visualization"
      description="The Live Fleet Map displays real-time GPS positions of all connected drones on a satellite-imagery basemap. Drone markers update continuously from MAVLink telemetry. Mission routes and waypoints are overlaid as interactive path layers."
      capabilities={[
        "Real-time satellite map with drone position markers",
        "Heading and movement indicator overlays",
        "Historical and active flight path trails",
        "Waypoint and mission-route visualization",
        "Geofence, restricted zone, and caution area overlays",
        "Map layer controls (satellite, terrain, geofences, trails)",
        "Drone selection and map-centered focus",
        "Location freshness indicators for stale telemetry",
      ]}
    />
  );
}
