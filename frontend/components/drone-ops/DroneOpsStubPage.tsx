"use client";

import Link from "next/link";

// ─────────────────────────────────────────────────────────────────────────────
// DroneOpsStubPage — shared empty state for drone-ops routes not yet implemented.
// Each stub identifies itself clearly so users (and devs) know the status.
// ─────────────────────────────────────────────────────────────────────────────

interface DroneOpsStubPageProps {
  icon: string;
  title: string;
  subtitle: string;
  milestone: string;
  description: string;
  capabilities?: string[];
}

export function DroneOpsStubPage({
  icon,
  title,
  subtitle,
  milestone,
  description,
  capabilities = [],
}: DroneOpsStubPageProps) {
  return (
    <div className="ac-drone-stub-page" role="main">
      <div className="ac-drone-stub-card">
        {/* Milestone badge */}
        <div className="ac-drone-stub-milestone">
          <span aria-hidden="true">◔</span>
          {milestone}
        </div>

        {/* Icon */}
        <div className="ac-drone-stub-icon" aria-hidden="true">{icon}</div>

        {/* Heading */}
        <h1 className="ac-drone-stub-title">{title}</h1>
        <p className="ac-drone-stub-subtitle">{subtitle}</p>

        {/* Description */}
        <p className="ac-drone-stub-description">{description}</p>

        {/* Planned capabilities */}
        {capabilities.length > 0 && (
          <div className="ac-drone-stub-capabilities">
            <h2 className="ac-drone-stub-cap-heading">Planned Capabilities</h2>
            <ul className="ac-drone-stub-cap-list">
              {capabilities.map((cap) => (
                <li key={cap} className="ac-drone-stub-cap-item">
                  <span aria-hidden="true" style={{ color: "var(--ac-accent)", marginRight: 6 }}>◆</span>
                  {cap}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Navigation */}
        <div className="ac-drone-stub-actions">
          <Link href="/drone-ops/overview" className="ac-btn ac-btn-primary">
            ← Operations Overview
          </Link>
          <Link href="/drones" className="ac-btn">
            Drone Fleet Registry
          </Link>
        </div>
      </div>
    </div>
  );
}
