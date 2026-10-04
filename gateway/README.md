# Kota Aerospace — Remote Edge Telemetry Gateway (`kota-gateway`)

The Kota Aerospace Remote Edge Telemetry Gateway connects UAS, eVTOL, and general aviation companion computers to the Kota Aerospace platform.

## Features
- Ingests MAVLink streams over UDP/TCP with STX boundary preservation.
- Local ACID store-and-forward queue in SQLite WAL mode.
- Exponential backoff retry and poison-batch quarantine.
- Independent heartbeat thread reporting health and queue depth.
- Hardware credential loading from secured files (`0600`).
- Systemd daemon integration for companion computers.

## Installation

```bash
# Production install
pip install ./gateway

# Editable development install
pip install -e ./gateway
```

## Usage

```bash
# Validate configuration without starting listeners
kota-gateway --config /etc/kota/gateway.json --validate-only

# Run daemon
kota-gateway --config /etc/kota/gateway.json
```
