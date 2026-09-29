# KOTA AEROSPACE — DATA ACQUISITION & INGESTION ARCHITECTURE

## 1. Executive Summary & Purpose
The **Data Acquisition Layer (DAL)** provides a unified, deterministic, multi-modal ingestion pipeline that bridges diverse aerospace and drone telemetry, flight records, sensor data, MRO work orders, and compliance documents into Kota Aerospace's central intelligence fabric.

The architecture strictly decouples raw protocol framing and third-party vendor schemas from the internal analytical engine through canonical event representations, fail-closed validation, and organization-scoped tenant isolation.

---

## 2. Ingestion Modalities & Data Flow

```text
  [ REAL-TIME STREAMS ]           [ BATCH & FILES ]              [ ENTERPRISE CONNECTORS ]
  ├── MAVLink (v1 / v2)           ├── Flight Log CSV/JSON/BIN    ├── OEM Fleet Management API
  ├── MQTT Telemetry Feeds        ├── Maintenance Work Orders    ├── Maintenance / MRO ERP
  ├── Edge Gateway (REST / WS)    ├── Sensor Dumps (Vib/Temp)    ├── Cloud Object Storage (S3)
  └── Webhooks (DJI, Skyward)     └── Compliance Audit Records   └── Customer REST Pull Adapters
               │                                │                              │
               ▼                                ▼                              ▼
    [ Protocol Decoders ]             [ File Staging & Parse ]       [ Connector Adapters ]
   (Framing, CRC, Checksums)         (CSV/JSON Parser, Size Limit)  (Rate-limiting, Sync State)
               │                                │                              │
               └───────────────────────┬────────┴──────────────────────────────┘
                                       │
                                       ▼
                       [ Schema Normalization Layer ]
                    Converts to: NormalizedTelemetryEvent
                                       │
                                       ▼
                     [ Validation & Authorization Gate ]
                       ├── Tenant & Asset Scope Check
                       ├── Subscription & Entitlement Check
                       ├── Rate Limits & Quota Enforcement
                       └── Duplicate / Out-of-Order Filter
                                       │
                                       ▼
                          [ Ingestion Router & Queue ]
                                       │
        ┌──────────────────────────────┼──────────────────────────────┐
        ▼                              ▼                              ▼
 [ Telemetry Storage ]       [ Real-time HUMS Engine ]      [ M7 Event Trigger ]
 (TimescaleDB / Hypertable)  (Feature Extraction & RUL)    (Signal & Finding Gen)
```

---

## 3. Canonical Event Data Model

Every telemetry input, regardless of source protocol, is normalized into the authoritative `NormalizedTelemetryEvent` structure prior to downstream persistence or analysis:

```python
class NormalizedTelemetryEvent(BaseModel):
    # Tenant & Vehicle Identity
    organization_id: UUID
    suite_id: SuiteType  # e.g., DRONE_UAV, AIRCRAFT, HELICOPTER, EVTOL
    asset_id: UUID
    source_protocol: str  # "MAVLINK_V2", "DJI_WEBHOOK", "MQTT_CANVAS", "CSV_IMPORT"
    
    # Timing & Ordering
    timestamp_utc: datetime
    sequence_number: Optional[int] = None
    ingest_timestamp_utc: datetime = Field(default_factory=datetime.utcnow)
    
    # Flight Context
    flight_id: Optional[UUID] = None
    session_id: Optional[str] = None
    flight_phase: Optional[str] = None  # "TAKEOFF", "CLIMB", "CRUISE", "HOVER", "LANDING"
    
    # Core Spatial & Dynamic Telemetry
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_msl_m: Optional[float] = None
    altitude_relative_m: Optional[float] = None
    ground_speed_mps: Optional[float] = None
    air_speed_mps: Optional[float] = None
    heading_deg: Optional[float] = None
    
    # Attitude & Inertial
    roll_deg: Optional[float] = None
    pitch_deg: Optional[float] = None
    yaw_deg: Optional[float] = None
    roll_rate_dps: Optional[float] = None
    pitch_rate_dps: Optional[float] = None
    yaw_rate_dps: Optional[float] = None
    accel_x_g: Optional[float] = None
    accel_y_g: Optional[float] = None
    accel_z_g: Optional[float] = None
    
    # Power & Propulsion
    battery_voltage_v: Optional[float] = None
    battery_current_a: Optional[float] = None
    battery_remaining_pct: Optional[float] = None
    battery_temperature_c: Optional[float] = None
    motor_rpm: Optional[Dict[str, float]] = None
    motor_temp_c: Optional[Dict[str, float]] = None
    
    # Health & System Status
    system_status: Optional[str] = None  # "STANDBY", "ACTIVE", "CRITICAL", "EMERGENCY"
    sensor_health_flags: Optional[Dict[str, bool]] = None
    vibration_rms_g: Optional[float] = None
    
    # Raw Payload Storage & Traceability
    raw_payload_checksum: Optional[str] = None
    raw_payload_ref: Optional[str] = None
```

---

## 4. Ingestion Pipelines

### 4.1 Real-Time Ingestion (MAVLink, MQTT, Webhooks)
1. **Transport Layer**:
   - Webhooks received via `POST /api/v1/telemetry/ingest` and `POST /api/v1/webhooks/dji`.
   - MAVLink streams parsed directly from UDP/TCP socket listener or serial gateway.
2. **De-duplication**:
   - Evaluated via `(organization_id, asset_id, timestamp_utc, sequence_number)` cache key in Redis/Memory.
   - Sliding window of 10,000 sequence IDs per vehicle prevents replay attacks or redundant packet processing.
3. **Throughput & Backpressure**:
   - Ingestion endpoints return `202 Accepted` with correlation ID in `< 25ms`.
   - Streaming bursts are buffer-managed into asynchronous worker queues for feature extraction and long-term storage.

### 4.2 Batch File Ingestion (CSV, JSON, Flight Logs)
1. **Staged Upload**:
   - Files uploaded to temporary tenant-isolated storage: `POST /api/v1/data-import/{domain}/validate`.
2. **Schema & Header Verification**:
   - Inspects headers, data types, timestamp formats (ISO-8601, UNIX epoch, GPS milliseconds), and missing column mapping.
3. **Job Execution**:
   - Client triggers execution: `POST /api/v1/data-import/jobs/{job_id}/execute`.
   - Processes records in chunks of 500 rows with transactional rollback on structural violation.

### 4.3 Extensible Enterprise Connectors
- Connector plugins implement the `BaseDataConnector` interface:
  ```python
  class BaseDataConnector(ABC):
      @abstractmethod
      async def authenticate(self, credentials: Dict[str, Any]) -> bool:
          pass
          
      @abstractmethod
      async def fetch_incremental(self, since_timestamp: datetime) -> AsyncIterator[NormalizedTelemetryEvent]:
          pass
          
      @abstractmethod
      async def health_check(self) -> Dict[str, Any]:
          pass
  ```
- Adding a new vendor (e.g., Collins Aerospace, Garmin Pilot, FlightAware) requires implementing this adapter without touching database schemas or core ingestion endpoints.

---

## 5. Security, Isolation & Auditability

1. **Tenant Validation**:
   - Telemetry packets must contain valid API keys, JWTs, or registered hardware device tokens bound to an active `organization_id`.
   - Mismatched `asset_id` (e.g., drone registered to Org A, telemetry sent with Org B credentials) triggers an immediate `403 Forbidden` and security audit log entry.
2. **Entitlement Enforcement**:
   - If an organization's subscription has expired or exceeded its `max_telemetry_rate_hz` or `max_active_assets` limit, ingestion is throttled or rejected with `402 Payment Required / 429 Too Many Requests`.
3. **Audit Trail**:
   - Every ingest batch logs total packets received, parsed, dropped (with reason), and downstream processing latency.
