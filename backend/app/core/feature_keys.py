"""Single authoritative source of canonical feature keys and normalization.

Every layer (database, registry, plan features, tenant overrides, entitlement
resolver, backend authorization, entitlement API, frontend context, sidebar,
route guards, LISA tools) uses these canonical identifiers.
"""

from __future__ import annotations

from enum import StrEnum


class FeatureKey(StrEnum):
    """Canonical feature keys recognized across the Kota Aerospace platform."""

    # Maintenance & Operations
    WORK_ORDER_MANAGEMENT = "work_order_management"
    INSPECTIONS_MANAGEMENT = "inspections_management"
    RELEASE_READINESS = "release_readiness"

    # Fleet & Operations
    AIRCRAFT_FLEET_MANAGEMENT = "aircraft_fleet_management"
    HELICOPTER_FLEET_MANAGEMENT = "helicopter_fleet_management"
    EVTOL_FLEET_MANAGEMENT = "evtol_fleet_management"
    AIRCRAFT_OPERATIONS = "aircraft_operations"
    AIRCRAFT_MRO = "aircraft_mro"
    DRONE_FLEET_MANAGEMENT = "drone_fleet_management"
    DRONE_MISSIONS = "drone_missions"
    HELICOPTER_OPERATIONS = "helicopter_operations"
    EVTOL_OPERATIONS = "evtol_operations"
    FLIGHT_TELEMETRY = "flight_telemetry"
    BATTERY_ANALYTICS = "battery_analytics"

    # Procurement
    PROCUREMENT_MANAGEMENT = "procurement_management"

    # Compliance & Governance
    COMPLIANCE_MANAGEMENT = "compliance_management"
    ADVANCED_COMPLIANCE_INTELLIGENCE = "advanced_compliance_intelligence"
    AUDIT_LOGGING = "audit_logging"

    # AI & Intelligence
    LISA_AI_COPILOT = "lisa_ai_copilot"
    PREDICTIVE_MAINTENANCE = "predictive_maintenance"

    # Advanced Engineering & Sensors
    DIGITAL_TWIN = "digital_twin"
    HUMS = "hums"
    MRO_INTELLIGENCE = "mro_intelligence"


# Normalization mapping from all known variants / legacy aliases / uppercase strings
# to the canonical feature key string value.
_FEATURE_KEY_ALIASES: dict[str, str] = {
    # Digital Twin
    "digital_twin": FeatureKey.DIGITAL_TWIN.value,
    "digital_twin_beta": FeatureKey.DIGITAL_TWIN.value,
    "digital_twin_module": FeatureKey.DIGITAL_TWIN.value,
    "digitaltwin": FeatureKey.DIGITAL_TWIN.value,
    "digital_twin_feature": FeatureKey.DIGITAL_TWIN.value,
    # HUMS
    "hums": FeatureKey.HUMS.value,
    "hums_module": FeatureKey.HUMS.value,
    "hums_ai": FeatureKey.HUMS.value,
    "hums_feature": FeatureKey.HUMS.value,
    "hums_intelligence": FeatureKey.HUMS.value,
    # LISA
    "lisa": FeatureKey.LISA_AI_COPILOT.value,
    "lisa_ai": FeatureKey.LISA_AI_COPILOT.value,
    "lisa_ai_copilot": FeatureKey.LISA_AI_COPILOT.value,
    "lisa_copilot": FeatureKey.LISA_AI_COPILOT.value,
    "ai_assistant": FeatureKey.LISA_AI_COPILOT.value,
    "ai_copilot": FeatureKey.LISA_AI_COPILOT.value,
    # MRO Intelligence
    "mro_intelligence": FeatureKey.MRO_INTELLIGENCE.value,
    "mro_intelligence_module": FeatureKey.MRO_INTELLIGENCE.value,
    "mro_intel": FeatureKey.MRO_INTELLIGENCE.value,
    # Work Orders
    "work_order_management": FeatureKey.WORK_ORDER_MANAGEMENT.value,
    "work_orders": FeatureKey.WORK_ORDER_MANAGEMENT.value,
    "work_order": FeatureKey.WORK_ORDER_MANAGEMENT.value,
    # Inspections
    "inspections_management": FeatureKey.INSPECTIONS_MANAGEMENT.value,
    "inspections": FeatureKey.INSPECTIONS_MANAGEMENT.value,
    "maintenance_inspections": FeatureKey.INSPECTIONS_MANAGEMENT.value,
    # Aircraft Fleets & Operations
    "aircraft_fleet_management": FeatureKey.AIRCRAFT_FLEET_MANAGEMENT.value,
    "aircraft_fleet": FeatureKey.AIRCRAFT_FLEET_MANAGEMENT.value,
    "aircraft_operations": FeatureKey.AIRCRAFT_OPERATIONS.value,
    "aircraft_mro": FeatureKey.AIRCRAFT_MRO.value,
    # Helicopter Fleets & Operations
    "helicopter_fleet_management": FeatureKey.HELICOPTER_FLEET_MANAGEMENT.value,
    "helicopter_fleet": FeatureKey.HELICOPTER_FLEET_MANAGEMENT.value,
    "helicopter_operations": FeatureKey.HELICOPTER_OPERATIONS.value,
    # eVTOL Fleets & Operations
    "evtol_fleet_management": FeatureKey.EVTOL_FLEET_MANAGEMENT.value,
    "evtol_fleet": FeatureKey.EVTOL_FLEET_MANAGEMENT.value,
    "evtol_operations": FeatureKey.EVTOL_OPERATIONS.value,
    # Drones & Missions
    "drone_fleet_management": FeatureKey.DRONE_FLEET_MANAGEMENT.value,
    "drone_operations": FeatureKey.DRONE_FLEET_MANAGEMENT.value,
    "drones": FeatureKey.DRONE_FLEET_MANAGEMENT.value,
    "drone_missions": FeatureKey.DRONE_MISSIONS.value,
    # Flight Telemetry
    "flight_telemetry": FeatureKey.FLIGHT_TELEMETRY.value,
    "telemetry": FeatureKey.FLIGHT_TELEMETRY.value,
    # Battery Analytics
    "battery_analytics": FeatureKey.BATTERY_ANALYTICS.value,
    "battery_operations": FeatureKey.BATTERY_ANALYTICS.value,
    # Procurement
    "procurement_management": FeatureKey.PROCUREMENT_MANAGEMENT.value,
    "procurement": FeatureKey.PROCUREMENT_MANAGEMENT.value,
    "procurement_operations": FeatureKey.PROCUREMENT_MANAGEMENT.value,
    # Compliance
    "compliance_management": FeatureKey.COMPLIANCE_MANAGEMENT.value,
    "compliance": FeatureKey.COMPLIANCE_MANAGEMENT.value,
    "compliance_reporting": FeatureKey.COMPLIANCE_MANAGEMENT.value,
    "compliance_governance": FeatureKey.COMPLIANCE_MANAGEMENT.value,
    # Advanced Compliance Intelligence
    "advanced_compliance_intelligence": FeatureKey.ADVANCED_COMPLIANCE_INTELLIGENCE.value,
    "compliance_intelligence": FeatureKey.ADVANCED_COMPLIANCE_INTELLIGENCE.value,
    # Predictive Maintenance
    "predictive_maintenance": FeatureKey.PREDICTIVE_MAINTENANCE.value,
    "predictive_ops": FeatureKey.PREDICTIVE_MAINTENANCE.value,
    # Release Readiness
    "release_readiness": FeatureKey.RELEASE_READINESS.value,
    # Audit Logging
    "audit_logging": FeatureKey.AUDIT_LOGGING.value,
    "audit_trail": FeatureKey.AUDIT_LOGGING.value,
}


def canonicalize_feature_key(key: str) -> str:
    """Normalize any feature key string (case-insensitive, alias-mapped) to its canonical key."""
    normalized = key.strip().lower()
    return _FEATURE_KEY_ALIASES.get(normalized, normalized)


# Baseline capabilities that exist in NO seeded/default plan today but that every
# tenant has always had (audit trail, release readiness). Gating them on the
# backend must not lock existing tenants out, so they are treated as enabled
# UNLESS a plan row or a tenant override explicitly disables them. Platform
# Admin can still turn them off; absence alone never denies.
DEFAULT_ON_FEATURES: frozenset[str] = frozenset(
    {FeatureKey.AUDIT_LOGGING.value, FeatureKey.RELEASE_READINESS.value}
)


def is_default_on_feature(key: str) -> bool:
    return canonicalize_feature_key(key) in DEFAULT_ON_FEATURES


def is_known_feature_key(key: str) -> bool:
    """True when `key` is a registered canonical key or alias (case-insensitive)."""
    return key.strip().lower() in _FEATURE_KEY_ALIASES


def get_feature_lookup_aliases(canonical_key: str) -> list[str]:
    """Return all known alias strings (including common uppercase variants) for a canonical feature."""
    aliases = [canonical_key, canonical_key.upper()]
    for alias, canonical in _FEATURE_KEY_ALIASES.items():
        if canonical == canonical_key:
            if alias not in aliases:
                aliases.append(alias)
            alias_upper = alias.upper()
            if alias_upper not in aliases:
                aliases.append(alias_upper)
    return aliases
