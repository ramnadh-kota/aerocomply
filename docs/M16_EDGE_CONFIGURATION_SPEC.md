# M16 Edge Configuration Specification

## 1. Overview
The KOTA Edge Platform employs an immutable, versioned configuration contract to govern how edge devices acquire, sample, envelope, and buffer physical sensor data.

---

## 2. Configuration Schema & Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `sampling_hz` | `int` | `1000` | Sampling rate for vibration accelerometers ($100 - 5000\text{ Hz}$). |
| `telemetry_interval_sec` | `int` | `5` | Periodic burst transmission interval ($1 - 60\text{ s}$). |
| `heartbeat_interval_sec` | `int` | `30` | Device status ping interval ($10 - 300\text{ s}$). |
| `buffer_capacity` | `int` | `500` | Maximum offline FIFO queue capacity ($100 - 5000\text{ records}$). |
| `offline_ttl_hours` | `int` | `72` | Maximum age of buffered offline data before warning. |
| `active_channels` | `list[str]` | `["CH1"]` | Hardware bus/port channels enabled for sampling. |
| `clip_threshold_g` | `float` | `25.0` | Accelerometer clip limit for `OUT_OF_RANGE` detection. |

---

## 3. Versioning & Rollback Lifecycle

```text
Draft Update (v2) ──► Validated ──► Applied (Active: v2)
                                         │
                                         ▼ (Rollback Requested)
                                     Applied (Active: v1)
```

1. **Version Immutability:** Configuration versions are strictly append-only.
2. **Rollback Safety:** Rollbacks restore a previous validated configuration snapshot with an immutable audit entry (`edge_device.config_rolled_back`).
3. **Synchronicity Tracking:** Edge heartbeats include running `config_version`. If less than cloud `active_config_version`, cloud responds with `requires_config_sync = true`.
