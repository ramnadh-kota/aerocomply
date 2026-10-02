"use client";

import { useEffect, useState, useMemo } from "react";
import { MapContainer, TileLayer, Marker, Tooltip, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { DroneState } from "@/lib/drone-ops/types";

// Fix Leaflet's default icon path issues in Next.js
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

interface FleetMapClientProps {
  drones: DroneState[];
  selectedDroneId: string | null;
  onSelectDrone: (id: string) => void;
  isSimulated: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Map Bounds Fitter
// ─────────────────────────────────────────────────────────────────────────────
function MapBoundsFitter({ drones, shouldFit, onFitComplete }: { drones: DroneState[], shouldFit: boolean, onFitComplete: () => void }) {
  const map = useMap();
  
  useEffect(() => {
    if (!shouldFit) return;
    
    const validPositions = drones
      .filter(d => d.latitude !== null && d.longitude !== null)
      .map(d => [d.latitude, d.longitude] as [number, number]);
      
    if (validPositions.length > 0) {
      const bounds = L.latLngBounds(validPositions);
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 16 });
    }
    
    onFitComplete();
  }, [drones, shouldFit, map, onFitComplete]);

  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Custom Icons
// ─────────────────────────────────────────────────────────────────────────────
function createDroneIcon(drone: DroneState, isSimulated: boolean, isSelected: boolean) {
  let color = "#9ca3af"; // Unknown / Stale
  let dash = false;
  
  if (isSimulated) {
    color = "#3b82f6"; // Blue for simulated
    dash = true;
  } else if (drone.connection_status === "CONNECTED" && drone.altitude !== null && drone.altitude > 0) {
    color = "#10b981"; // Live Airborne
  } else if (drone.connection_status === "CONNECTED") {
    color = "#fbbf24"; // Live Grounded
  } else if (drone.connection_status === "DISCONNECTED") {
    color = "#ef4444"; // Offline
  }

  const border = isSelected ? "2px solid #ffffff" : "2px solid rgba(255,255,255,0.8)";
  const zIndex = isSelected ? 1000 : 1;
  const shadow = isSelected ? "0 0 12px rgba(255,255,255,0.6)" : "0 2px 4px rgba(0,0,0,0.3)";
  const dashStyle = dash ? "border-style: dashed;" : "";

  const html = `
    <div style="
      background-color: ${color};
      width: 14px;
      height: 14px;
      border-radius: 50%;
      ${dashStyle}
      border: ${border};
      box-shadow: ${shadow};
      position: relative;
    ">
      ${isSelected ? `<div style="position:absolute; top:-4px; left:-4px; right:-4px; bottom:-4px; border: 1px solid #fff; border-radius: 50%; animation: pulse 2s infinite"></div>` : ""}
    </div>
  `;

  return L.divIcon({
    html,
    className: "ac-custom-drone-icon",
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// FleetMapClient
// ─────────────────────────────────────────────────────────────────────────────
export default function FleetMapClient({ drones, selectedDroneId, onSelectDrone, isSimulated }: FleetMapClientProps) {
  const [shouldFit, setShouldFit] = useState(true);

  const mappedDrones = useMemo(() => {
    return drones.filter(d => d.latitude !== null && d.longitude !== null);
  }, [drones]);

  // Center on Bangalore by default if no drones
  const defaultCenter: [number, number] = [12.9716, 77.5946];

  if (mappedDrones.length === 0) {
    return (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", background: "var(--ac-bg-elevated)", color: "var(--ac-text-muted)" }}>
        <div style={{ fontSize: 24, marginBottom: 8 }}>◉</div>
        <strong>No Valid Positions</strong>
        <span style={{ fontSize: 12 }}>None of the current fleet have valid GPS coordinates.</span>
      </div>
    );
  }

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <MapContainer 
        center={mappedDrones[0] ? [mappedDrones[0].latitude!, mappedDrones[0].longitude!] : defaultCenter} 
        zoom={14} 
        style={{ width: "100%", height: "100%", zIndex: 1 }}
        zoomControl={false}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
        />

        <MapBoundsFitter drones={mappedDrones} shouldFit={shouldFit} onFitComplete={() => setShouldFit(false)} />

        {mappedDrones.map(drone => (
          <Marker 
            key={drone.asset_id} 
            position={[drone.latitude!, drone.longitude!]}
            icon={createDroneIcon(drone, isSimulated, drone.asset_id === selectedDroneId)}
            eventHandlers={{
              click: () => onSelectDrone(drone.asset_id)
            }}
          >
            <Tooltip direction="top" offset={[0, -10]} opacity={0.9}>
              <div style={{ padding: "2px 4px", fontSize: 12, fontWeight: 600 }}>
                {drone.registration}
                <div style={{ fontSize: 10, fontWeight: 400, color: "#666" }}>
                  {drone.altitude !== null ? `${Math.round(drone.altitude)}m` : ""} {drone.flight_mode}
                </div>
              </div>
            </Tooltip>
          </Marker>
        ))}
      </MapContainer>

      {/* Manual Fit Fleet Control */}
      <button 
        className="ac-btn-secondary"
        onClick={() => setShouldFit(true)}
        style={{
          position: "absolute",
          top: "16px",
          right: "16px",
          zIndex: 10,
          background: "var(--ac-bg-card)",
          boxShadow: "0 2px 8px rgba(0,0,0,0.5)",
          padding: "6px 12px",
          fontSize: 12,
        }}
      >
        Fit Fleet
      </button>

      {/* Mode Indicator Overlay */}
      <div style={{
        position: "absolute",
        bottom: "16px",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 10,
        background: "rgba(0,0,0,0.7)",
        backdropFilter: "blur(4px)",
        padding: "4px 12px",
        borderRadius: "16px",
        fontSize: 11,
        color: isSimulated ? "var(--ac-status-review)" : "var(--ac-text-muted)",
        border: `1px solid ${isSimulated ? "var(--ac-status-review)" : "rgba(255,255,255,0.1)"}`,
        pointerEvents: "none"
      }}>
        {isSimulated ? "SIMULATED COORDINATES" : "LIVE TELEMETRY ACTIVE"}
      </div>
    </div>
  );
}
