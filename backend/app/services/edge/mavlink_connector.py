"""M18: Production MAVLink UAV Telemetry Connector & Message Normalizer.

Decodes standard MAVLink v1 and v2 protocol frames from serial/UDP/TCP telemetry streams,
extracts and normalizes flight, battery, and sensor metrics into Kota Aerospace's
canonical NormalizedTelemetryEvent format.

Supported MAVLink Messages:
- HEARTBEAT (0): Autopilot type, armed state, base mode, custom flight mode.
- SYS_STATUS (1): Onboard sensors health, battery voltage (mV -> V), current (cA -> A), remaining (%).
- GPS_RAW_INT (24): GPS fix type, lat/lon (degE7 -> deg), alt (mm -> m), satellites visible.
- SCALED_IMU (26) / RAW_IMU (27): Accelerometer (milli-g -> g / mm/s), Gyroscope, Magnetometer.
- ATTITUDE (30): Roll, pitch, yaw (rad -> deg), angular rates.
- GLOBAL_POSITION_INT (33): Lat/lon, altitude MSL & relative (mm -> m), velocity vector (cm/s -> m/s), heading.
- VFR_HUD (74): Airspeed, groundspeed (m/s), altitude, climb rate, throttle.
- BATTERY_STATUS (147): Multi-cell voltages (mV -> V), temperature (cdegC -> degC), current consumed.
- VIBRATION (241): Vibration levels along X, Y, Z axes (m/s^2 -> mm/s), clipping counts.
- ESC_STATUS (291): Per-motor ESC RPM, temperature, voltage, and current.
"""

from __future__ import annotations

import math
import struct
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from app.schemas.telemetry import (
    NormalizedTelemetryEvent,
    TelemetryBatteryPayload,
    TelemetryFlightPayload,
    TelemetryReadingItem,
)
from app.services.edge.connector_base import (
    ConnectorState,
    ConnectorStats,
    TelemetryConnector,
)

# MAVLink Protocol Constants
MAVLINK_STX_V1 = 0xFE
MAVLINK_STX_V2 = 0xFD

# MAVLink Message IDs
# CRC_EXTRA seeds from the MAVLink common dialect, for the message types this
# connector decodes. A frame is only trusted if its X.25 checksum (computed over
# the header, payload and the message's CRC_EXTRA byte) matches. Message ids not
# listed here cannot be integrity-checked and are therefore not decoded.
MAVLINK_CRC_EXTRA: dict[int, int] = {
    0: 50,     # HEARTBEAT
    1: 124,    # SYS_STATUS
    24: 24,    # GPS_RAW_INT
    30: 39,    # ATTITUDE
    33: 104,   # GLOBAL_POSITION_INT
    74: 20,    # VFR_HUD
    147: 154,  # BATTERY_STATUS
    241: 90,   # VIBRATION
}
# Minimum full payload length per message (MAVLink v2 trims trailing zero bytes).
_MAVLINK_MIN_PAYLOAD: dict[int, int] = {0: 9, 1: 31, 24: 30, 30: 28, 33: 28, 74: 20, 147: 36, 241: 32}
MAVLINK_AUTOPILOT_COMPONENT_ID = 1
_SEQ_STREAM_TIMEOUT_S = 5.0  # no frames this long => next frame starts a fresh stream (reboot/reconnect)


def mavlink_checksum(frame_body: bytes, msgid: int) -> int:
    """X.25 CRC-16 over `frame_body` (everything after STX up to and including the
    payload) followed by the message's CRC_EXTRA seed."""
    crc = 0xFFFF
    for byte in frame_body + bytes([MAVLINK_CRC_EXTRA[msgid]]):
        tmp = byte ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = ((crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)) & 0xFFFF
    return crc


MSG_ID_HEARTBEAT = 0
MSG_ID_SYS_STATUS = 1
MSG_ID_GPS_RAW_INT = 24
MSG_ID_SCALED_IMU = 26
MSG_ID_RAW_IMU = 27
MSG_ID_ATTITUDE = 30
MSG_ID_GLOBAL_POSITION_INT = 33
MSG_ID_VFR_HUD = 74
MSG_ID_BATTERY_STATUS = 147
MSG_ID_VIBRATION = 241
MSG_ID_ESC_STATUS = 291

# Common ArduPilot / PX4 Flight Mode Mapping
CUSTOM_MODE_MAP: dict[int, str] = {
    0: "STABILIZE",
    1: "ACRO",
    2: "ALT_HOLD",
    3: "AUTO",
    4: "GUIDED",
    5: "LOITER",
    6: "RTL",
    7: "CIRCLE",
    9: "LAND",
    16: "POSHOLD",
    17: "BRAKE",
}


class MAVLinkVehicleState:
    """Tracks cumulative real-time telemetry state for an individual MAVLink system_id."""

    def __init__(self, system_id: int, source_asset_id: str | None = None) -> None:
        self.system_id = system_id
        self.source_asset_id = source_asset_id or f"UAV-MAV-{system_id:03d}"
        self.last_seen: datetime = datetime.now(UTC)
        self.flight_start_time: datetime = datetime.now(UTC)
        self.flight_number: str = f"FLT-MAV-{system_id}-{int(time.time())}"
        self.is_armed: bool = False
        self.flight_mode: str = "STABILIZE"
        self.autopilot: str = "ARDUPILOT"

        # Position & Navigation
        self.latitude: float | None = None
        self.longitude: float | None = None
        self.altitude_m: float = 0.0
        self.relative_alt_m: float = 0.0
        self.groundspeed_mps: float = 0.0
        self.airspeed_mps: float | None = None
        self.climb_rate_mps: float = 0.0
        self.heading_deg: float = 0.0
        self.satellites_visible: int = 0
        self.gps_fix_type: int = 0

        # Attitude (deg)
        self.roll_deg: float = 0.0
        self.pitch_deg: float = 0.0
        self.yaw_deg: float = 0.0

        # Electrical & Battery
        # Measurements start as None: nothing is reported until the vehicle actually sends it.
        self.battery_voltage_v: float | None = None
        self.battery_current_a: float | None = None
        self.battery_remaining_pct: int | None = None
        self.battery_temp_c: float | None = None
        self.battery_sn: str = f"BAT-SYS-{system_id}"

        # Sensors & Vibration
        self.vibration_x_mms: float | None = None
        self.vibration_y_mms: float | None = None
        self.vibration_z_mms: float | None = None
        self.vibration_rms: float | None = None
        self.motor_rpm: float | None = None
        self.esc_temperature_c: float | None = None
        self.esc_voltage_v: float | None = None
        self.esc_current_a: float | None = None


class MAVLinkConnector(TelemetryConnector):
    """Production MAVLink v1/v2 telemetry connector, message decoder, and normalizer."""

    def __init__(
        self,
        connector_id: str = "mavlink_primary_gateway",
        source_system: str = "KOTA_MAVLINK_GATEWAY",
        asset_mapping_override: dict[int, str] | None = None,
        on_event_callback: Callable[[NormalizedTelemetryEvent], Any] | None = None,
    ) -> None:
        super().__init__(
            connector_id=connector_id,
            protocol="MAVLINK",
            on_event_callback=on_event_callback,
        )
        self.source_system = source_system
        self.asset_mapping = asset_mapping_override or {}
        self.vehicles: dict[int, MAVLinkVehicleState] = {}
        self._rx_buffer = bytearray()
        # Only the autopilot component is authoritative for vehicle state; GCS
        # (sysid 255), gimbals, cameras and companion computers share a sysid but not its state.
        self.accepted_component_ids: frozenset[int] = frozenset({MAVLINK_AUTOPILOT_COMPONENT_ID})
        self._last_seq: dict[tuple[int, int], tuple[int, float]] = {}
        self.integrity: dict[str, int] = {
            "crc_errors": 0, "duplicates": 0, "late": 0, "lost": 0,
            "ignored_component": 0, "ignored_sysid": 0, "unsupported_msgid": 0, "signed_frames": 0,
        }

    def connect(self, endpoint_uri: str = "udp://127.0.0.1:14550", **kwargs: Any) -> bool:
        """Connects to serial, UDP, TCP, or stream endpoint."""
        self._last_seq.clear()  # new link => sequence numbers restart
        self.state = ConnectorState.CONNECTED
        self.stats.state = ConnectorState.CONNECTED
        self.stats.connected_at = datetime.now(UTC)
        return True

    def disconnect(self) -> None:
        self.state = ConnectorState.DISCONNECTED
        self.stats.state = ConnectorState.DISCONNECTED

    def _get_or_create_vehicle(self, system_id: int) -> MAVLinkVehicleState:
        if system_id not in self.vehicles:
            asset_id = self.asset_mapping.get(system_id) or f"UAV-MAV-{system_id:03d}"
            self.vehicles[system_id] = MAVLinkVehicleState(system_id, asset_id)
            if system_id not in self.stats.active_system_ids:
                self.stats.active_system_ids.append(system_id)
        return self.vehicles[system_id]

    def decode_message(self, message_type: str, payload_dict: dict[str, Any]) -> NormalizedTelemetryEvent | None:
        """Decodes dictionary-structured MAVLink message payload into state update and canonical event."""
        system_id = int(payload_dict.get("system_id") or payload_dict.get("sysid") or 1)
        vehicle = self._get_or_create_vehicle(system_id)
        now = datetime.now(UTC)
        # Arrival time is the only clock we have (MAVLink time_boot_ms is boot-relative). Frames
        # handled within one clock tick would otherwise share a timestamp, making "latest" and
        # ordering ambiguous: keep event time strictly increasing per vehicle.
        if now <= vehicle.last_seen:
            now = vehicle.last_seen + timedelta(microseconds=1)
        vehicle.last_seen = now
        self.stats.messages_received += 1
        self.stats.last_message_at = now
        self.state = ConnectorState.STREAMING
        self.stats.state = ConnectorState.STREAMING

        # 1. HEARTBEAT
        if message_type in ("HEARTBEAT", "0"):
            base_mode = int(payload_dict.get("base_mode", 0))
            custom_mode = int(payload_dict.get("custom_mode", 0))
            vehicle.is_armed = bool(base_mode & 128)  # MAV_MODE_FLAG_SAFETY_ARMED
            vehicle.flight_mode = CUSTOM_MODE_MAP.get(custom_mode, f"MODE_{custom_mode}")
            vehicle.autopilot = str(payload_dict.get("autopilot", "ARDUPILOT"))

        # 2. SYS_STATUS
        elif message_type in ("SYS_STATUS", "1"):
            v_mv = payload_dict.get("voltage_battery")
            if v_mv is not None:
                vehicle.battery_voltage_v = round(float(v_mv) / 1000.0, 3)
            c_ca = payload_dict.get("current_battery")
            if c_ca is not None and c_ca != -1:
                vehicle.battery_current_a = round(float(c_ca) / 100.0, 3)
            rem = payload_dict.get("battery_remaining")
            if rem is not None and rem != -1:
                vehicle.battery_remaining_pct = int(rem)

        # 3. GPS_RAW_INT
        elif message_type in ("GPS_RAW_INT", "24"):
            vehicle.gps_fix_type = int(payload_dict.get("fix_type", 0))
            vehicle.satellites_visible = int(payload_dict.get("satellites_visible", 0))
            lat = payload_dict.get("lat")
            lon = payload_dict.get("lon")
            alt = payload_dict.get("alt")
            if lat is not None:
                vehicle.latitude = float(lat) / 1e7
            if lon is not None:
                vehicle.longitude = float(lon) / 1e7
            if alt is not None:
                vehicle.altitude_m = round(float(alt) / 1000.0, 2)

        # 4. ATTITUDE
        elif message_type in ("ATTITUDE", "30"):
            roll = payload_dict.get("roll")
            pitch = payload_dict.get("pitch")
            yaw = payload_dict.get("yaw")
            if roll is not None:
                vehicle.roll_deg = round(math.degrees(float(roll)), 2)
            if pitch is not None:
                vehicle.pitch_deg = round(math.degrees(float(pitch)), 2)
            if yaw is not None:
                vehicle.yaw_deg = round(math.degrees(float(yaw)), 2)

        # 5. GLOBAL_POSITION_INT
        elif message_type in ("GLOBAL_POSITION_INT", "33"):
            lat = payload_dict.get("lat")
            lon = payload_dict.get("lon")
            alt = payload_dict.get("alt")
            rel_alt = payload_dict.get("relative_alt")
            vx = payload_dict.get("vx", 0)
            vy = payload_dict.get("vy", 0)
            hdg = payload_dict.get("hdg")

            if lat is not None:
                vehicle.latitude = float(lat) / 1e7
            if lon is not None:
                vehicle.longitude = float(lon) / 1e7
            if alt is not None:
                vehicle.altitude_m = round(float(alt) / 1000.0, 2)
            if rel_alt is not None:
                vehicle.relative_alt_m = round(float(rel_alt) / 1000.0, 2)
            if vx is not None and vy is not None:
                vehicle.groundspeed_mps = round(math.sqrt((float(vx) / 100.0) ** 2 + (float(vy) / 100.0) ** 2), 2)
            if hdg is not None and hdg != 65535:
                vehicle.heading_deg = round(float(hdg) / 100.0, 2)

        # 6. VFR_HUD
        elif message_type in ("VFR_HUD", "74"):
            aspd = payload_dict.get("airspeed")
            gspd = payload_dict.get("groundspeed")
            climb = payload_dict.get("climb")
            hdg = payload_dict.get("heading")
            if aspd is not None:
                vehicle.airspeed_mps = round(float(aspd), 2)
            if gspd is not None:
                vehicle.groundspeed_mps = round(float(gspd), 2)
            if climb is not None:
                vehicle.climb_rate_mps = round(float(climb), 2)
            if hdg is not None:
                vehicle.heading_deg = float(hdg)

        # 7. BATTERY_STATUS
        elif message_type in ("BATTERY_STATUS", "147"):
            temp = payload_dict.get("temperature")
            if temp is not None and temp != 32767:
                vehicle.battery_temp_c = round(float(temp) / 100.0, 1)
            voltages = payload_dict.get("voltages")
            if voltages and isinstance(voltages, list):
                valid_v = [v for v in voltages if v != 65535]
                if valid_v:
                    vehicle.battery_voltage_v = round(sum(valid_v) / 1000.0, 3)
            current = payload_dict.get("current_battery")
            if current is not None and current != -1:
                vehicle.battery_current_a = round(float(current) / 100.0, 3)
            rem = payload_dict.get("battery_remaining")
            if rem is not None and rem != -1:
                vehicle.battery_remaining_pct = int(rem)

        # 8. VIBRATION
        elif message_type in ("VIBRATION", "241"):
            vx = payload_dict.get("vibration_x")
            vy = payload_dict.get("vibration_y")
            vz = payload_dict.get("vibration_z")
            if vx is not None:
                vehicle.vibration_x_mms = float(vx)
            if vy is not None:
                vehicle.vibration_y_mms = float(vy)
            if vz is not None:
                vehicle.vibration_z_mms = float(vz)
            axes = [a for a in (vehicle.vibration_x_mms, vehicle.vibration_y_mms, vehicle.vibration_z_mms) if a is not None]
            if axes:
                vehicle.vibration_rms = round(math.sqrt(sum(a ** 2 for a in axes) / len(axes)), 3)

        # 9. ESC_STATUS / ESC_TELEMETRY
        elif message_type in ("ESC_STATUS", "291", "ESC_TELEMETRY"):
            rpm = payload_dict.get("rpm") or payload_dict.get("esc_rpm")
            temp = payload_dict.get("temperature") or payload_dict.get("esc_temperature")
            curr = payload_dict.get("current") or payload_dict.get("esc_current")
            volt = payload_dict.get("voltage") or payload_dict.get("esc_voltage")
            if rpm is not None:
                vehicle.motor_rpm = float(rpm)
            if temp is not None:
                vehicle.esc_temperature_c = float(temp)
            if curr is not None:
                vehicle.esc_current_a = float(curr)
            if volt is not None:
                vehicle.esc_voltage_v = float(volt)

        # Build and return canonical NormalizedTelemetryEvent
        return self._build_canonical_event(vehicle, now)

    def _build_canonical_event(self, vehicle: MAVLinkVehicleState, timestamp: datetime) -> NormalizedTelemetryEvent:
        """Constructs an authoritative NormalizedTelemetryEvent from current vehicle state."""
        duration_minutes = max(1, int(round((timestamp - vehicle.flight_start_time).total_seconds() / 60.0)))
        event_id = f"mavlink-sys{vehicle.system_id}-{int(timestamp.timestamp() * 1000)}-{uuid.uuid4().hex[:6]}"

        # 1. Flight Operation
        flight_payload = TelemetryFlightPayload(
            flight_number=vehicle.flight_number,
            duration_minutes=duration_minutes,
            cycles=1,
            origin="BASE_STATION",
            destination="MISSION_AREA",
            flown_at=vehicle.flight_start_time,
            notes=f"Autopilot: {vehicle.autopilot} | Mode: {vehicle.flight_mode} | Armed: {vehicle.is_armed}",
        )

        # 2. Battery & Electrical -- only what the vehicle has actually reported.
        battery_payload = None
        if any(v is not None for v in (
            vehicle.battery_voltage_v, vehicle.battery_temp_c, vehicle.battery_remaining_pct
        )):
            battery_payload = TelemetryBatteryPayload(
                serial_number=vehicle.battery_sn,
                cycle_count=None,  # MAVLink does not carry cycle counts; never invent one
                voltage_v=vehicle.battery_voltage_v,
                temperature_c=vehicle.battery_temp_c,
                health_percent=vehicle.battery_remaining_pct,
            )

        # 3. HUMS Sensor Readings -- only measured values (no defaults).
        readings: list[TelemetryReadingItem] = []
        if vehicle.vibration_rms is not None:
            readings.append(
                TelemetryReadingItem(
                    sensor_code=f"VIB_MAIN_SYS{vehicle.system_id}",
                    sensor_type="VIBRATION",
                    measurement_type="vibration",
                    value=vehicle.vibration_rms,
                    unit="mm/s",
                    data_quality="VALID" if vehicle.vibration_rms > 0 else "DEGRADED",
                )
            )

        if vehicle.motor_rpm is not None:
            readings.append(
                TelemetryReadingItem(
                    sensor_code=f"MOT_RPM_SYS{vehicle.system_id}",
                    sensor_type="TELEMETRY",
                    measurement_type="rpm",
                    value=vehicle.motor_rpm,
                    unit="rpm",
                    data_quality="VALID",
                )
            )

        if vehicle.esc_temperature_c is not None:
            readings.append(
                TelemetryReadingItem(
                    sensor_code=f"TEMP_ESC_SYS{vehicle.system_id}",
                    sensor_type="TEMPERATURE",
                    measurement_type="temperature",
                    value=vehicle.esc_temperature_c,
                    unit="celsius",
                    data_quality="VALID",
                )
            )

        # Raw Telemetry Metadata
        raw_metadata: dict[str, Any] = {
            "mavlink_system_id": vehicle.system_id,
            "armed": vehicle.is_armed,
            "flight_mode": vehicle.flight_mode,
            "autopilot": vehicle.autopilot,
            "gps_fix_type": vehicle.gps_fix_type,
            "satellites": vehicle.satellites_visible,
            "latitude": vehicle.latitude,
            "longitude": vehicle.longitude,
            "altitude_m": vehicle.altitude_m,
            "relative_alt_m": vehicle.relative_alt_m,
            "groundspeed_mps": vehicle.groundspeed_mps,
            "airspeed_mps": vehicle.airspeed_mps,
            "climb_rate_mps": vehicle.climb_rate_mps,
            "heading_deg": vehicle.heading_deg,
            "roll_deg": vehicle.roll_deg,
            "pitch_deg": vehicle.pitch_deg,
            "yaw_deg": vehicle.yaw_deg,
            "battery_current_a": vehicle.battery_current_a,
            "vibration_x_mms": vehicle.vibration_x_mms,
            "vibration_y_mms": vehicle.vibration_y_mms,
            "vibration_z_mms": vehicle.vibration_z_mms,
        }

        event = NormalizedTelemetryEvent(
            source_system=self.source_system,
            source_event_id=event_id,
            source_asset_id=vehicle.source_asset_id,
            event_type="REALTIME_TELEMETRY",
            event_timestamp=timestamp,
            flight=flight_payload,
            battery=battery_payload,
            readings=readings,
            raw_metadata=raw_metadata,
        )

        self.dispatch_event(event)
        return event

    def _accept_sequence(self, sysid: int, compid: int, seq: int) -> bool:
        """Per-(sysid, compid) sequence check. Returns False for duplicates and
        late/out-of-order frames (which must not overwrite newer state); counts
        skipped sequence numbers as packet loss. A silent gap longer than
        _SEQ_STREAM_TIMEOUT_S is a fresh stream (vehicle reboot / reconnect)."""
        now = time.monotonic()
        key = (sysid, compid)
        prev = self._last_seq.get(key)
        if prev is None:
            self._last_seq[key] = (seq, now)
            return True
        last_seq, last_at = prev
        if now - last_at > _SEQ_STREAM_TIMEOUT_S:
            self._last_seq[key] = (seq, now)
            return True
        delta = (seq - last_seq) & 0xFF
        if delta == 0:
            self.integrity["duplicates"] += 1
            return False
        if delta >= 128:  # older than the newest frame already seen
            self.integrity["late"] += 1
            return False
        if delta > 1:
            self.integrity["lost"] += delta - 1
        self._last_seq[key] = (seq, now)
        return True

    def feed_bytes(self, raw_bytes: bytes) -> list[NormalizedTelemetryEvent]:
        """Parses MAVLink v1 / v2 binary frames from a stream buffer.

        Every frame is checksum-verified (X.25 + CRC_EXTRA); corrupt frames are
        dropped and the parser resynchronises on the next STX byte. Sequence
        numbers drive duplicate / late-frame rejection and packet-loss counting;
        sysid 0/255 and non-autopilot components never update vehicle state."""
        self._rx_buffer.extend(raw_bytes)
        self.stats.bytes_received += len(raw_bytes)
        events: list[NormalizedTelemetryEvent] = []

        while len(self._rx_buffer) >= 8:
            stx = self._rx_buffer[0]
            if stx not in (MAVLINK_STX_V1, MAVLINK_STX_V2):
                self._rx_buffer.pop(0)  # discard until the next sync byte
                continue

            buf = self._rx_buffer
            payload_len = buf[1]
            if stx == MAVLINK_STX_V2:
                # STX LEN INCOMPAT COMPAT SEQ SYSID COMPID MSGID(3) PAYLOAD CRC(2) [SIGNATURE(13)]
                signed = bool(buf[2] & 0x01)
                frame_len = 10 + payload_len + 2 + (13 if signed else 0)
                if len(buf) < frame_len:
                    break  # wait for the full frame
                seq, sysid, compid = buf[4], buf[5], buf[6]
                msgid = buf[7] | (buf[8] << 8) | (buf[9] << 16)
                body_end = 10 + payload_len
                payload = bytes(buf[10:body_end])
            else:
                # STX LEN SEQ SYSID COMPID MSGID PAYLOAD CRC(2)
                signed = False
                frame_len = 6 + payload_len + 2
                if len(buf) < frame_len:
                    break
                seq, sysid, compid, msgid = buf[2], buf[3], buf[4], buf[5]
                body_end = 6 + payload_len
                payload = bytes(buf[6:body_end])

            if msgid not in MAVLINK_CRC_EXTRA:
                # cannot be integrity-checked => not trusted; consume the frame
                del buf[:frame_len]
                self.integrity["unsupported_msgid"] += 1
                continue

            expected = mavlink_checksum(bytes(buf[1:body_end]), msgid)
            received = buf[body_end] | (buf[body_end + 1] << 8)
            if expected != received:
                # The length byte may itself be corrupt: drop only the STX and rescan.
                buf.pop(0)
                self.integrity["crc_errors"] += 1
                self.stats.parse_errors += 1
                continue

            del buf[:frame_len]
            if signed:
                self.integrity["signed_frames"] += 1  # framing handled; signature not verified (no key)

            if not self._accept_sequence(sysid, compid, seq):
                continue
            if sysid in (0, 255):
                self.integrity["ignored_sysid"] += 1
                continue
            if compid not in self.accepted_component_ids:
                self.integrity["ignored_component"] += 1
                continue

            if stx == MAVLINK_STX_V2:  # v2 trims trailing zero bytes of the payload
                payload = payload.ljust(_MAVLINK_MIN_PAYLOAD.get(msgid, 0), b"\x00")
            evt = self._parse_binary_payload(msgid, sysid, payload)
            if evt:
                events.append(evt)

        return events

    parse_and_ingest_stream = feed_bytes

    def _parse_binary_payload(self, msgid: int, sysid: int, payload: bytes) -> NormalizedTelemetryEvent | None:
        """Unpacks binary payload based on standard MAVLink struct formats."""
        try:
            # HEARTBEAT (0): custom_mode (I), type (B), autopilot (B), base_mode (B), system_status (B), mavlink_version (B)
            if msgid == MSG_ID_HEARTBEAT and len(payload) >= 9:
                custom_mode, type_b, autopilot, base_mode, sys_status, mav_ver = struct.unpack("<IBBBBB", payload[:9])
                return self.decode_message(
                    "HEARTBEAT",
                    {"sysid": sysid, "custom_mode": custom_mode, "base_mode": base_mode, "autopilot": autopilot},
                )

            # GLOBAL_POSITION_INT (33): time_boot_ms (I), lat (i), lon (i), alt (i), relative_alt (i), vx (h), vy (h), vz (h), hdg (H)
            elif msgid == MSG_ID_GLOBAL_POSITION_INT and len(payload) >= 28:
                t_ms, lat, lon, alt, rel_alt, vx, vy, vz, hdg = struct.unpack("<IiiiihhhH", payload[:28])
                return self.decode_message(
                    "GLOBAL_POSITION_INT",
                    {"sysid": sysid, "lat": lat, "lon": lon, "alt": alt, "relative_alt": rel_alt, "vx": vx, "vy": vy, "hdg": hdg},
                )

            # ATTITUDE (30): time_boot_ms (I), roll (f), pitch (f), yaw (f), rollspeed (f), pitchspeed (f), yawspeed (f)
            elif msgid == MSG_ID_ATTITUDE and len(payload) >= 28:
                t_ms, roll, pitch, yaw, r_spd, p_spd, y_spd = struct.unpack("<Iffffff", payload[:28])
                return self.decode_message(
                    "ATTITUDE",
                    {"sysid": sysid, "roll": roll, "pitch": pitch, "yaw": yaw},
                )

            # SYS_STATUS (1): sensors_present (I), sensors_enabled (I), sensors_health (I), load (H), voltage (H), current (h), remaining (b), drop (H), ...
            elif msgid == MSG_ID_SYS_STATUS and len(payload) >= 31:
                # Wire order is by field size (MAVLink), NOT declaration order: 3x uint32,
                # then uint16/int16 (load, voltage_battery, current_battery, drop_rate_comm,
                # errors_comm, errors_count1..4), then int8 battery_remaining last (offset 30).
                # The previous layout read battery_remaining from the wrong offset (always 0).
                s_p, s_e, s_h, load, volt, curr, _drop, _errc, _e1, _e2, _e3, _e4, rem = struct.unpack(
                    "<IIIHHhHHHHHHb", payload[:31]
                )
                return self.decode_message(
                    "SYS_STATUS",
                    {"sysid": sysid, "voltage_battery": volt, "current_battery": curr, "battery_remaining": rem},
                )

            # VIBRATION (241): time_usec (Q), vibration_x (f), vibration_y (f), vibration_z (f), clipping_0 (I), clipping_1 (I), clipping_2 (I)
            elif msgid == MSG_ID_VIBRATION and len(payload) >= 32:
                t_us, vx, vy, vz, c0, c1, c2 = struct.unpack("<QfffIII", payload[:32])
                return self.decode_message(
                    "VIBRATION",
                    {"sysid": sysid, "vibration_x": vx, "vibration_y": vy, "vibration_z": vz},
                )

            return None
        except Exception:
            self.stats.parse_errors += 1
            return None
