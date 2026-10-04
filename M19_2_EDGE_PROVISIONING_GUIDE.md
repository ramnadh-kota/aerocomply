# Kota Aerospace — M19.2 Edge Device Provisioning Guide

**Target Audience:** Field Engineers, Drone Operations Managers, Flight Test Engineers  
**Applies To:** Kota Aerospace Remote Edge Telemetry Gateway (`kota-gateway`)  
**Security Classification:** Operational Guide  

---

## 1. Overview & Architecture

Every companion computer running `kota-gateway` authenticates to the Kota Aerospace platform using a dedicated machine credential presented in the `X-Kota-Device-Key` HTTP header:

```
kdev.<edge_device_uuid>.<secret>
```

- **Tenant Isolation:** The device UUID is bound to a single organization (`Organization.id`). Telemetry and heartbeats submitted with this token can only ever write into the owning organization.
- **Credential Storage:** The token is never stored in plaintext in the platform database. Only `SHA-256(secret)` is retained. The plaintext token is returned **exactly once** during provisioning or key rotation.
- **Local Companion Storage:** Stored in a restricted configuration file (`/etc/kota/gateway.json`) with `0600` (read/write only by the `kota` user).

---

## 2. Provisioning Workflow

### Prerequisites
1. Operator account with `ORG_MANAGE` role in the target organization.
2. Network connectivity from the companion computer to the Kota Cloud API.

### Step 1: Obtain Operator Bearer Token
Log in via the Kota API or portal to retrieve an operator JWT:

```bash
export KOTA_API_URL="https://api.aerocomply.com/api/v1"
export KOTA_AUTH_TOKEN="<OPERATOR_JWT_TOKEN>"
```

### Step 2: Execute Provisioning CLI
Run `provision_edge_device.py` to enroll the companion computer and generate `/etc/kota/gateway.json`:

```bash
# Basic enrollment
sudo python scripts/provision_edge_device.py \
    --api-url "${KOTA_API_URL}" \
    --auth-token "${KOTA_AUTH_TOKEN}" \
    --device-id "companion-cm4-alpha-01" \
    --asset-id "936f99aa-7bed-4963-9ed1-d8db219c59ed" \
    --output "/etc/kota/gateway.json" \
    --verify
```

### Output Example (Secrets Redacted):
```
2026-10-04 10:00:00 [INFO] Enrolling device 'companion-cm4-alpha-01' via API endpoint: https://api.aerocomply.com/api/v1
2026-10-04 10:00:01 [INFO] Device enrolled successfully (Device ID: companion-cm4-alpha-01, Token: kdev.1809a043-8e09-48b5-8963-d484a20e6557.***)
2026-10-04 10:00:01 [INFO] Executing initial diagnostic heartbeat handshake...
2026-10-04 10:00:02 [INFO] Heartbeat verification passed: credentials authenticated and active.
2026-10-04 10:00:02 [INFO] Secure configuration written atomically to '/etc/kota/gateway.json' (mode 0600).
2026-10-04 10:00:02 [INFO] Provisioning completed successfully.
```

---

## 3. Configuration File Schema (`/etc/kota/gateway.json`)

```json
{
  "api_url": "https://api.aerocomply.com/api/v1",
  "device_id": "companion-cm4-alpha-01",
  "device_key": "kdev.1809a043-8e09-48b5-8963-d484a20e6557.c3ByaW5nLXZhbGlkYXRpb24tdG9rZW4tMjAyNg",
  "mavlink_source": "udp:127.0.0.1:14550",
  "queue_db_path": "/var/lib/kota/gateway_queue.db",
  "allow_insecure_http": false,
  "heartbeat_interval_seconds": 15.0,
  "batch_size_bytes": 65536,
  "max_queue_entries": 50000,
  "max_queue_bytes": 104857600,
  "log_level": "INFO"
}
```

---

## 4. Credential Rotation & Revocation

### Rotating Device Credentials:
When rotating credentials on an active aircraft, the backend supports a rotation grace period so telemetry transmission is never interrupted:

```bash
# Call rotation API with 60-second overlap grace
curl -X POST "${KOTA_API_URL}/edge/devices/companion-cm4-alpha-01/credential/rotate" \
     -H "Authorization: Bearer ${KOTA_AUTH_TOKEN}" \
     -H "Content-Type: application/json" \
     -d '{"grace_seconds": 60}'
```

Update `/etc/kota/gateway.json` with the newly minted token and restart the gateway service:
```bash
sudo systemctl restart kota-gateway
```

### Emergency Revocation:
If a physical drone or companion computer is compromised, stolen, or lost:
```bash
# Immediately revoke device
curl -X POST "${KOTA_API_URL}/edge/devices/companion-cm4-alpha-01/revoke" \
     -H "Authorization: Bearer ${KOTA_AUTH_TOKEN}"
```
Once revoked, all subsequent heartbeats and telemetry uploads fail immediately with HTTP 401 Unauthorized.
