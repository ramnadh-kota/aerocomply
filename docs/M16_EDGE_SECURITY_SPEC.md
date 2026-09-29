# M16 Edge Security Specification

## 1. Overview
This document specifies the security architecture, hardware identity verification, authenticated telemetry envelopes, command safety constraints, and revocation controls for the KOTA Edge Platform.

---

## 2. Security Pillars

### 1. Hardware Identity & Factory Token Authentication
- Each edge device is provisioned with a unique cryptographic pre-shared key (`provisioning_token`).
- Token hash is stored securely in PostgreSQL (`auth_token_hash = SHA256(secret)`).
- Edge nodes authenticate API requests via Bearer token or HMAC header.

### 2. Envelope Integrity & Tamper Detection
- Every `DeviceTelemetryEnvelope` includes an HMAC-SHA256 signature generated over:
  $$\text{Signature} = \text{HMAC-SHA256}(\text{device\_id} \parallel \text{sequence\_number} \parallel \text{timestamp})$$
- Monotonically increasing sequence numbers prevent replay attacks.

### 3. Safe Command Channel (Zero Remote Code Execution)
- KOTA Cloud **NEVER** allows arbitrary remote shell execution (`bash`, `ssh`, `eval`).
- Only pre-compiled, strictly parameterized operational commands are supported (`REQUEST_HEARTBEAT`, `REQUEST_CONFIG`, `APPLY_CONFIG`, `RESTART_ACQUISITION`, `REQUEST_DIAGNOSTICS`).

### 4. Deterministic Device Revocation
- When a device is flagged as lost, stolen, or decommissioned, operators invoke `POST /api/v1/edge/devices/{device_id}/revoke`.
- The device status is immediately transitioned to `REVOKED`.
- All subsequent telemetry submissions, heartbeats, and commands are blocked at the ingress boundary (`HTTP 403 Forbidden`).

### 5. Multi-Tenant Isolation
- Edge devices are bound to a single `organization_id`.
- Tenant A cannot query, configure, issue commands to, or receive telemetry from Tenant B's hardware devices.
