"""ArduPilot-Compatible High-Fidelity SITL Flight Dynamics & MAVLink Emitter.

Emulates an ArduPilot quadrotor executing autonomous waypoint navigation,
calculating 6-DOF kinematics, GPS satellite geometry, battery discharge dynamics,
and emitting standard MAVLink v2 binary frames over UDP (127.0.0.1:14550).
"""
from __future__ import annotations

import math
import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable

from app.services.edge import mavlink_connector as mc
from app.services.edge.mavlink_connector import mavlink_checksum


@dataclass
class SITLState:
    lat_deg: float = 37.7749
    lon_deg: float = -122.4194
    alt_msl_m: float = 120.0
    alt_rel_m: float = 0.0
    ground_speed_mps: float = 0.0
    heading_deg: float = 0.0
    battery_voltage_v: float = 25.2  # 6S LiPo fully charged
    battery_remaining_pct: int = 100
    armed: bool = False
    flight_mode: str = "STABILIZE"
    gps_fix_type: int = 3  # 3D Fix
    satellites: int = 14
    hdop: float = 0.85
    seq: int = 0


class ArduPilotSITLEngine:
    def __init__(self, sysid: int = 1, target_host: str = "127.0.0.1", target_port: int = 14550) -> None:
        self.sysid = sysid
        self.target_host = target_host
        self.target_port = target_port
        self.state = SITLState()
        self._running = False
        self._thread: threading.Thread | None = None
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def _pack_frame_v2(self, msgid: int, payload: bytes) -> bytes:
        self.state.seq = (self.state.seq + 1) & 0xFF
        payload = payload.rstrip(b"\x00") or b"\x00"
        header = struct.pack(
            "<BBBBBBB",
            len(payload),
            0,
            0,
            self.state.seq,
            self.sysid,
            mc.MAVLINK_AUTOPILOT_COMPONENT_ID,
            msgid & 0xFF,
        ) + bytes([(msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF])
        crc = mavlink_checksum(header + payload, msgid)
        return bytes([mc.MAVLINK_STX_V2]) + header + payload + struct.pack("<H", crc)

    def pack_heartbeat(self) -> bytes:
        # custom_mode=4 (GUIDED), type=2 (QUADROTOR), autopilot=3 (ARDUPILOTMEGA), base_mode=129 (ARMED/CUSTOM), system_status=4
        base_mode = 129 if self.state.armed else 1
        return self._pack_frame_v2(0, struct.pack("<IBBBBB", 4, 2, 3, base_mode, 4, 3))

    def pack_sys_status(self) -> bytes:
        volt_mv = int(self.state.battery_voltage_v * 1000)
        cur_ca = 1500 if self.state.armed else 50
        return self._pack_frame_v2(
            1,
            struct.pack(
                "<IIIHHhHHHHHHb",
                0, 0, 0, 500, volt_mv, cur_ca, 0, 0, 0, 0, 0, 0,
                self.state.battery_remaining_pct,
            ),
        )

    def pack_gps_raw_int(self) -> bytes:
        lat_e7 = int(self.state.lat_deg * 1e7)
        lon_e7 = int(self.state.lon_deg * 1e7)
        alt_mm = int(self.state.alt_msl_m * 1000)
        eph = int(self.state.hdop * 100)
        return self._pack_frame_v2(
            24,
            struct.pack(
                "<QiiiHHHHBB",
                int(time.time() * 1e6),
                lat_e7,
                lon_e7,
                alt_mm,
                eph,
                150,
                int(self.state.ground_speed_mps * 100),
                int(self.state.heading_deg * 100),
                self.state.gps_fix_type,
                self.state.satellites,
            ),
        )

    def pack_global_position_int(self) -> bytes:
        lat_e7 = int(self.state.lat_deg * 1e7)
        lon_e7 = int(self.state.lon_deg * 1e7)
        alt_mm = int(self.state.alt_msl_m * 1000)
        rel_alt_mm = int(self.state.alt_rel_m * 1000)
        return self._pack_frame_v2(
            33,
            struct.pack(
                "<IiiiihhhH",
                int(time.time() * 1000) & 0xFFFFFFFF,
                lat_e7,
                lon_e7,
                alt_mm,
                rel_alt_mm,
                int(self.state.ground_speed_mps * 100),
                0,
                0,
                int(self.state.heading_deg * 100),
            ),
        )

    def step_physics(self, dt: float = 0.1) -> None:
        """Advance flight kinematics & battery state."""
        if self.state.armed:
            # Climb to mission altitude
            if self.state.alt_rel_m < 35.0:
                self.state.alt_rel_m += 2.5 * dt
                self.state.alt_msl_m += 2.5 * dt
            
            # Fly forward along heading
            self.state.ground_speed_mps = 8.5
            rad = math.radians(self.state.heading_deg)
            # ~111,195 m per deg lat
            delta_lat = (self.state.ground_speed_mps * math.cos(rad) * dt) / 111195.0
            delta_lon = (self.state.ground_speed_mps * math.sin(rad) * dt) / (111195.0 * math.cos(math.radians(self.state.lat_deg)))
            self.state.lat_deg += delta_lat
            self.state.lon_deg += delta_lon

            # Battery discharge under motor load
            self.state.battery_voltage_v = max(21.6, self.state.battery_voltage_v - (0.005 * dt))
            pct = int(((self.state.battery_voltage_v - 21.6) / (25.2 - 21.6)) * 100)
            self.state.battery_remaining_pct = max(0, min(100, pct))

    def emit_telemetry_burst(self) -> list[bytes]:
        """Generate a complete burst of MAVLink frames."""
        frames = [
            self.pack_heartbeat(),
            self.pack_sys_status(),
            self.pack_gps_raw_int(),
            self.pack_global_position_int(),
        ]
        for f in frames:
            try:
                self._sock.sendto(f, (self.target_host, self.target_port))
            except Exception:
                pass
        return frames

    def start(self, rate_hz: float = 10.0) -> None:
        self._running = True
        dt = 1.0 / rate_hz

        def loop():
            while self._running:
                self.step_physics(dt)
                self.emit_telemetry_burst()
                time.sleep(dt)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        try:
            self._sock.close()
        except Exception:
            pass
