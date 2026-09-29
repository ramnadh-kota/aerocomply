# Kota Aerospace — Suite Architecture Specification

## 1. Core Architectural Principle
Kota Aerospace implements a **Suite-First Commercial Architecture** designed to serve heterogeneous aerospace domains while sharing core platform capabilities.

The canonical hierarchy is:
```text
Platform Operator (Global Catalog)
       ↓
ProductSuite (AIRCRAFT | DRONE_UAV | HELICOPTER | EVTOL_AAM)
       ↓
Plan (with suite_id NOT NULL, e.g., Starter, Professional, Enterprise)
       ↓
Subscription (organization_id, plan_id, suite_id)
       ↓
Organization
       ↓
Users / Roles (RBAC)
       ↓
Effective Entitlements (Suite Modules, Feature Keys, Usage Limits)
```

---

## 2. Supported Domain Product Suites

### 1. Aircraft Suite (`code: "AIRCRAFT"`)
- **Target Market**: Fixed-wing commercial air carriers, cargo operators, regional airlines, business aviation, and PART-145 MROs.
- **Core Modules & Capabilities**:
  - `aircraft_fleet_management`: Aircraft tail registration, MSN tracking, flight hours/cycles, engine assignment, maintenance scheduling.
  - `mro_intelligence`: Work orders, task cards, technician authorization, part tracking, RII second-inspector gates.
  - `inspections_management`: Scheduled/unscheduled inspection programs, interval thresholds.
  - `compliance_obligations`: Airworthiness Directives (ADs), Service Bulletins (SBs), regulatory applicability engines.
  - `digital_evidence`: SHA-256 tamper-evident digital thread, maintenance sign-offs, inspector acceptance gates.
  - `ai_chat_assistant` (LISA): Grounded AOG recovery, release readiness, procurement bottleneck tracking.

### 2. Drone / UAV Suite (`code: "DRONE_UAV"`)
- **Target Market**: Autonomous drone fleet operators, inspection service providers, BVLOS logistics, defense/enterprise UAV fleets.
- **Core Modules & Capabilities**:
  - `drone_fleet_management`: Drone registration, hardware serial tracking, firmware tracking.
  - `drone_missions`: Mission planning, flight logging, automated telemetry capture.
  - `battery_analytics`: Battery serial lineage, cycle counts, cell voltage balance, degradation modeling.
  - `flight_telemetry` & `live_telemetry_streaming`: Real-time MAVLink v2 ingestion, DJI FlightHub 2 webhook integration.
  - `hums_health_monitoring`: Vibration RMS, FFT spectral features, bearing degradation tracking.
  - `proactive_maintenance_m7`: Automated exceedance detection, proactive maintenance signals.

### 3. Helicopter Suite (`code: "HELICOPTER"`)
- **Target Market**: Rotary-wing operators, Emergency Medical Services (EMS), offshore oil & gas transport, utility/heavy-lift helicopters.
- **Engine Reuse with Domain Grounding**:
  - Reuses the core asset engine, work order management, compliance engine, and evidence thread.
  - Uses specialized high-frequency rotor vibration analysis, transmission gearbox HUMS parameters, and rotor blade tracking algorithms.

### 4. eVTOL / AAM Suite (`code: "EVTOL_AAM"`)
- **Target Market**: Electric vertical takeoff and landing aircraft, urban air mobility (UAM), advanced electric air cargo.
- **Engine Reuse with Domain Grounding**:
  - Reuses multi-rotor drone battery health telemetry algorithms combined with Part-135/Part-121 aircraft airworthiness and compliance frameworks.
  - Specialized distributed electric propulsion (DEP) monitoring and high-voltage inverter thermal tracking.

---

## 3. Database Schema Mapping

```sql
-- Product Suites Catalog Table (Platform-level)
CREATE TABLE product_suites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    icon VARCHAR(64),
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- Plans Table (Linked strictly to a ProductSuite)
CREATE TABLE plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    suite_id UUID NOT NULL REFERENCES product_suites(id) ON DELETE RESTRICT,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(255) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    CONSTRAINT uq_plans_suite_id_code UNIQUE (suite_id, code)
);

-- Subscriptions Table (Links Organization to a Plan and its Suite)
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    plan_id UUID NOT NULL REFERENCES plans(id) ON DELETE RESTRICT,
    suite_id UUID NOT NULL REFERENCES product_suites(id) ON DELETE RESTRICT,
    status VARCHAR(32) NOT NULL,
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ends_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);
```

---

## 4. Multi-Suite Organization Support
Kota Aerospace allows a single enterprise organization to hold subscriptions to multiple product suites simultaneously (e.g. an operator managing both commercial fixed-wing aircraft and an inspection drone fleet).

- **Per-Suite Ambiguity Guarding**: Overlapping subscription ambiguity checks (`_assert_no_ambiguity`) enforce uniqueness per `(organization_id, suite_id)`.
- **Entitlement Aggregation**: An organization holding an active Aircraft subscription and an active Drone subscription receives access to the respective modules of both suites without authorization conflicts.
