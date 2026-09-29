# KOTA AEROSPACE — M18 TECH GUY 1 DEPLOYMENT GUIDE
## Production & Development UAV Acquisition Deployment

### 1. Zero Production Dependencies
The Kota Aerospace UAV Data Acquisition Layer is strictly designed with **zero dependencies on Mission Planner, manual CSV flight uploads, or permanent laptop connections in production**.

---

### 2. Production Deployment Topology

#### Topology A: Onboard Companion Computer (Recommended)
```
+-------------------------------------------------------------+
|                     UAV AIRFRAME                            |
|                                                             |
|  +---------------------+         +-----------------------+  |
|  | Flight Controller   |  UART   | Companion Computer    |  |
|  | ArduPilot / PX4     |-------->| (RPi 4 / CM4 / Jetson)|  |
|  | TELEM2 / MAVLink    | 921600  | - Kota Gateway Daemon |  |
|  +---------------------+         | - LTE / 5G Modem      |  |
|                                  +-----------------------+  |
|                                              |              |
+----------------------------------------------|--------------+
                                               | TLS 1.3 / HTTPS
                                               v
                                        Kota Cloud API
```

#### Topology B: Cellular Telemetry Bridge / Smart Radio
```
+---------------------+     915MHz     +-----------------------+   Cellular   +------------+
| UAV + FC (MAVLink)  |--------------->| Ground Telemetry Base |------------->| Kota Cloud |
| (Air Unit)          |     Radio      | (Kota Gateway Daemon) |    HTTPS     | API Ingest |
+---------------------+                +-----------------------+              +------------+
```

---

### 3. Provisioning & Configuration

#### 3.1 Edge Gateway Environment Variables
```bash
# Gateway Identity & Tenant Scoping
KOTA_GATEWAY_ID="GW-HEAVY-LIFT-01"
KOTA_TENANT_API_TOKEN="ey..."
KOTA_CLOUD_BASE_URL="https://api.kota-aerospace.com"

# MAVLink Connection Endpoint (UART Serial or UDP Stream)
KOTA_MAVLINK_ENDPOINT="serial:///dev/ttyAMA0:921600"
# OR: KOTA_MAVLINK_ENDPOINT="udp://0.0.0.0:14550"

# Store-and-Forward Buffer Configuration
KOTA_BUFFER_CAPACITY=10000
KOTA_BATCH_SIZE=25
KOTA_HEARTBEAT_INTERVAL_SEC=30
```

#### 3.2 Systemd Service Unit (`/etc/systemd/system/kota-gateway.service`)
```ini
[Unit]
Description=Kota Aerospace UAV Telemetry Gateway Daemon
After=network.target network-online.target
Wants=network-online.target

[Service]
Type=simple
User=kota
WorkingDirectory=/opt/kota-gateway
ExecStart=/opt/kota-gateway/venv/bin/python -m app.services.edge.gateway_daemon
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
EnvironmentFile=/etc/kota/gateway.env

[Install]
WantedBy=multi-user.target
```

---

### 4. Development vs Production Topology Comparison

| Parameter | Development Mode | Production Mode |
|---|---|---|
| **MAVLink Source** | SITL Simulator / Mission Planner MAVProxy Relay | Onboard Flight Controller TELEM Port |
| **Transport** | UDP `127.0.0.1:14550` | High-speed UART (`/dev/ttyAMA0` 921600 baud) / LTE |
| **Laptop Requirement** | Temporary developer laptop for debugging | **NO laptop required (autonomous daemon)** |
| **GCS Requirement** | Mission Planner / QGroundControl for inspection | **NO GCS required in ingestion path** |
| **Store & Forward** | Memory FIFO queue | High-durability disk-backed FIFO queue |
| **Uplink** | Local testserver / mock cloud | Secured TLS 1.3 HTTPS with JWT Auth |
| **Monitoring** | Console verbose logging | Periodic Heartbeat + Cloud Control Center Metrics |
