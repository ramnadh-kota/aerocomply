"use client";

import dynamic from "next/dynamic";
import type { DroneState } from "@/lib/drone-ops/types";

// Leaflet MUST be loaded dynamically with SSR disabled to prevent 
// "window is not defined" errors during server rendering.
const FleetMapClient = dynamic(() => import("./FleetMapClient"), {
  ssr: false,
  loading: () => (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "var(--ac-bg-elevated)", color: "var(--ac-text-muted)" }}>
      <div style={{ fontSize: 24, marginBottom: 8 }} className="spinner">◉</div>
      <strong>Loading Map Engine...</strong>
    </div>
  ),
});

interface FleetMapProps {
  drones: DroneState[];
  selectedDroneId: string | null;
  onSelectDrone: (id: string) => void;
  isSimulated: boolean;
}

export function FleetMap(props: FleetMapProps) {
  return <FleetMapClient {...props} />;
}
