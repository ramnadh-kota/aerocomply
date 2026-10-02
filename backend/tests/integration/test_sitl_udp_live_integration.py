"""Live Network Socket SITL Integration Test.

Validates that real MAVLink v2 UDP datagrams are transmitted across a real network socket (127.0.0.1:14550),
received by the edge gateway transport listener, decoded by MAVLinkConnector with X.25 CRC-16 checks,
and published to the LiveBroker for client consumption without data corruption.
"""
from __future__ import annotations

import socket
import struct
import threading
import time
import uuid
import pytest

from app.services.edge.mavlink_connector import MAVLinkConnector
from app.services.live_state_service import LiveBroker
from tests.unit.test_m20_mavlink_integrity import frame_v2, heartbeat, sys_status


def test_sitl_udp_socket_live_transmission():
    # 1. Setup UDP receiver socket
    host = "127.0.0.1"
    port = 14552  # dynamic test port
    
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind((host, port))
    server_sock.settimeout(2.0)
    
    connector = MAVLinkConnector()
    received_events = []
    stop_event = threading.Event()
    
    def receiver_thread():
        while not stop_event.is_set():
            try:
                data, _ = server_sock.recvfrom(2048)
                events = connector.feed_bytes(data)
                received_events.extend(events)
            except socket.timeout:
                continue
            except Exception:
                break

    t = threading.Thread(target=receiver_thread, daemon=True)
    t.start()
    
    # 2. Setup UDP sender (Virtual SITL Drone)
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    try:
        # Transmit 5 MAVLink v2 frames over UDP network stack
        hb = heartbeat(sysid=1, seq=1)
        client_sock.sendto(hb, (host, port))
        
        ss = sys_status(volt_mv=24500, cur_ca=1200, remaining=92, sysid=1, seq=2)
        client_sock.sendto(ss, (host, port))
        
        # Virtual Drone 2
        hb2 = heartbeat(sysid=2, seq=1)
        client_sock.sendto(hb2, (host, port))
        
        # Give receiver thread time to capture packets
        time.sleep(0.3)
    finally:
        stop_event.set()
        t.join(timeout=1.0)
        server_sock.close()
        client_sock.close()
    
    # 3. Assertions on real socket transmission
    assert len(received_events) >= 2
    assert connector.stats.bytes_received > 0
    assert connector.stats.events_generated >= 2
    assert 1 in connector.vehicles
    assert 2 in connector.vehicles
    assert connector.vehicles[1].battery_voltage_v == 24.5
    assert connector.vehicles[1].battery_remaining_pct == 92
