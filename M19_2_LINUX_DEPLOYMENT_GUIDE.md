# Kota Aerospace — M19.2 Linux Deployment & Operations Guide

**Target Environment:** Linux Companion Computers (Ubuntu 22.04 / 24.04 LTS, Debian 12, Raspberry Pi OS 64-bit)  
**Supported Hardware:** Raspberry Pi Compute Module 4, NVIDIA Jetson Orin Nano, x86_64 Industrial PC  
**Daemon Process:** `kota-gateway` (systemd service)  

---

## 1. Prerequisites & OS Preparation

### System Requirements:
- Linux kernel >= 5.10 with network namespace and cgroups v2 support.
- Python >= 3.10 and `pip`.
- SQLite >= 3.35 (standard in all modern Linux distributions).
- Serial/USB driver (`ch341`, `ftdi_sio`, or `cdc_acm`) if connecting via hardware UART/USB.

### Create Dedicated System User & Directories:
```bash
# Create dedicated system service account without login shell
sudo useradd --system --no-create-home --user-group --shell /usr/sbin/nologin kota

# Create configuration, state, and logging directories
sudo mkdir -p /etc/kota /var/lib/kota /var/log/kota

# Set ownership and permissions
sudo chown -R kota:kota /etc/kota /var/lib/kota /var/log/kota
sudo chmod 700 /etc/kota /var/lib/kota /var/log/kota
```

---

## 2. Package Installation

### Option A: Install from Wheel / Source Distribution (Production)
```bash
sudo pip install ./gateway
```

Verify that the CLI executable is installed:
```bash
kota-gateway --version
# Output: kota-gateway 1.0.0
```

### Option B: Editable Install (Development / Bench Testing)
```bash
pip install -e ./gateway
```

---

## 3. Systemd Service Setup

### Step 1: Install Unit File
Copy the provided unit file to systemd's system unit directory:
```bash
sudo cp gateway/systemd/kota-gateway.service /etc/systemd/system/kota-gateway.service
sudo chmod 644 /etc/systemd/system/kota-gateway.service
```

### Step 2: Validate Configuration
Before starting the service, test your configuration using the preflight validator:
```bash
sudo -u kota kota-gateway --config /etc/kota/gateway.json --validate-only
# Expected Output: [INFO] kota_gateway: Configuration is valid.
```

### Step 3: Enable and Start the Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable kota-gateway
sudo systemctl start kota-gateway
```

### Step 4: Verify Service Status
```bash
sudo systemctl status kota-gateway
```

Expected active status:
```
● kota-gateway.service - Kota Aerospace Edge Telemetry Gateway Daemon
     Loaded: loaded (/etc/systemd/system/kota-gateway.service; enabled; vendor preset: enabled)
     Active: active (running) since Sun 2026-10-04 10:15:00 UTC; 12s ago
    Process: 1245 ExecStartPre=/usr/local/bin/kota-gateway --config /etc/kota/gateway.json --validate-only (code=exited, status=0/SUCCESS)
   Main PID: 1246 (kota-gateway)
      Tasks: 4 (limit: 4915)
     Memory: 24.5M
     CGroup: /system.slice/kota-gateway.service
             └─1246 /usr/bin/python3 /usr/local/bin/kota-gateway --config /etc/kota/gateway.json
```

---

## 4. Monitoring & Troubleshooting

### Viewing Live Logs:
```bash
# Follow live gateway logs with journalctl
sudo journalctl -u kota-gateway -f
```

### Common Failure Modes & Diagnostics:

| Issue | Log Indication | Root Cause & Resolution |
|---|---|---|
| **Invalid Device Key** | `Heartbeat AUTHENTICATION failure (HTTP 401)` | Check `/etc/kota/gateway.json`. Device key has expired, is malformed, or was revoked on the platform. |
| **Device ID Mismatch** | `Heartbeat PERMISSION failure (HTTP 403)` | The `device_id` in `gateway.json` does not match the UUID in the token. Re-provision using `provision_edge_device.py`. |
| **Insecure HTTP Rejection** | `Insecure HTTP transport rejected` | Production gateway requires HTTPS (`https://...`). Set `allow_insecure_http: true` only for local bench testing. |
| **Serial Port Permission** | `Permission denied: '/dev/ttyACM0'` | Add the `kota` user to the `dialout` group: `sudo usermod -aG dialout kota` and reboot/restart service. |
| **Queue Saturation** | `Queue byte capacity reached` | Ingress MAVLink rate exceeds cellular upload bandwidth. Gateway automatically evicts low-priority debug records to preserve navigation and alarms. |

---

## 5. Rollback & Uninstallation

```bash
# Stop and disable service
sudo systemctl stop kota-gateway
sudo systemctl disable kota-gateway
sudo rm /etc/systemd/system/kota-gateway.service
sudo systemctl daemon-reload

# Uninstall python package
sudo pip uninstall -y kota-gateway

# Preserve queue database for forensic analysis (optional)
sudo cp /var/lib/kota/gateway_queue.db ~/gateway_queue.backup.db
```
