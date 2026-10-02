"use client";

// ─────────────────────────────────────────────────────────────────────────────
// Map placeholder — central panel for A1.
// A3 (Interactive Map) will replace this component with Leaflet/MapLibre.
// This placeholder establishes the correct dimensions and integration point.
// ─────────────────────────────────────────────────────────────────────────────

interface MapPlaceholderProps {
  droneCount: number;
  airborneCount: number;
}

export function MapPlaceholder({ droneCount, airborneCount }: MapPlaceholderProps) {
  return (
    <div className="ac-drone-map-placeholder" role="region" aria-label="Live fleet map (map library loading in A3)">
      {/* Decorative grid pattern */}
      <div className="ac-drone-map-grid" aria-hidden="true" />

      {/* Simulated drone position dots */}
      <div className="ac-drone-map-dots" aria-hidden="true">
        {/* Static representative positions — replaced by real GPS markers in A3 */}
        <div className="ac-drone-map-dot airborne" style={{ left: "38%", top: "42%" }} />
        <div className="ac-drone-map-dot airborne" style={{ left: "55%", top: "32%" }} />
        <div className="ac-drone-map-dot airborne" style={{ left: "62%", top: "58%" }} />
        <div className="ac-drone-map-dot airborne pulse" style={{ left: "44%", top: "65%" }} />
        <div className="ac-drone-map-dot grounded" style={{ left: "30%", top: "55%" }} />
        <div className="ac-drone-map-dot offline" style={{ left: "70%", top: "44%" }} />

        {/* Flight path lines */}
        <svg
          className="ac-drone-map-paths"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <polyline
            points="38,42 40,38 43,35 48,32 52,30 55,32"
            fill="none"
            stroke="rgba(90,155,255,0.4)"
            strokeWidth="0.4"
            strokeDasharray="1.2 0.8"
          />
          <polyline
            points="55,32 58,35 60,40 62,48 62,58"
            fill="none"
            stroke="rgba(90,155,255,0.3)"
            strokeWidth="0.35"
            strokeDasharray="1 0.8"
          />
          <polyline
            points="44,65 43,60 41,55 40,50 38,42"
            fill="none"
            stroke="rgba(47,191,113,0.45)"
            strokeWidth="0.35"
            strokeDasharray="1 0.8"
          />
        </svg>

        {/* Geofence ring */}
        <div className="ac-drone-map-geofence" style={{ left: "42%", top: "38%", width: 180, height: 150 }} aria-hidden="true" />
      </div>

      {/* Center label */}
      <div className="ac-drone-map-label">
        <div className="ac-drone-map-label-icon" aria-hidden="true">◉</div>
        <div className="ac-drone-map-label-text">
          <strong>Live Fleet Map</strong>
          <span>{airborneCount} of {droneCount} drones airborne</span>
          <small>Interactive satellite map loads in Milestone A3</small>
        </div>
      </div>

      {/* Map controls bar (positions integration layer for A3) */}
      <div className="ac-drone-map-controls" aria-label="Map layer controls">
        <button className="ac-drone-map-ctrl-btn active" disabled aria-pressed="true">Satellite</button>
        <button className="ac-drone-map-ctrl-btn" disabled>Terrain</button>
        <button className="ac-drone-map-ctrl-btn" disabled>Geofences</button>
        <button className="ac-drone-map-ctrl-btn" disabled>Trails</button>
      </div>
    </div>
  );
}
