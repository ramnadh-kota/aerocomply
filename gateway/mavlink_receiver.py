"""MAVLink receiver module with strict frame boundary safety for UDP and TCP sources.

Implements frame-aware buffering to guarantee complete MAVLink v1 and v2 frames are preserved
across partial TCP stream reads and multi-frame UDP datagrams without splitting frames across batches.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Callable

from gateway.config import GatewayConfig

logger = logging.getLogger("kota_gateway.receiver")

MAVLINK_STX_V1 = 0xFE
MAVLINK_STX_V2 = 0xFD
MAVLINK_SIGNATURE_LEN = 13


def extract_mavlink_frames(buf: bytearray) -> tuple[list[bytes], bytearray]:
    """Extract complete MAVLink v1 and v2 frames from a byte buffer.

    Returns:
        (extracted_frames, remaining_buffer)
    """
    frames: list[bytes] = []

    while len(buf) >= 8:
        # 1. Resynchronize on first occurrence of STX byte
        stx = buf[0]
        if stx not in (MAVLINK_STX_V1, MAVLINK_STX_V2):
            # Scan forward to next STX
            next_sync_v1 = buf.find(bytes([MAVLINK_STX_V1]))
            next_sync_v2 = buf.find(bytes([MAVLINK_STX_V2]))

            candidates = [idx for idx in (next_sync_v1, next_sync_v2) if idx != -1]
            if not candidates:
                # No sync bytes in buffer at all; drop buffer
                buf.clear()
                break
            first_sync = min(candidates)
            del buf[:first_sync]
            stx = buf[0]

        # 2. Determine frame length
        payload_len = buf[1]
        if stx == MAVLINK_STX_V2:
            if len(buf) < 10:
                # Wait for full header (10 bytes)
                break
            signed = bool(buf[2] & 0x01)
            frame_len = 10 + payload_len + 2 + (MAVLINK_SIGNATURE_LEN if signed else 0)
        else:
            # MAVLink v1: STX(1) + LEN(1) + SEQ(1) + SYSID(1) + COMPID(1) + MSGID(1) + PAYLOAD(L) + CRC(2)
            frame_len = 6 + payload_len + 2

        # 3. Check if complete frame is present
        if len(buf) < frame_len:
            # Wait for remainder of frame to arrive
            break

        # 4. Extract frame
        frame = bytes(buf[:frame_len])
        del buf[:frame_len]
        frames.append(frame)

    return frames, buf


class MAVLinkReceiver:
    """Listens for MAVLink byte streams, ensuring frame boundary preservation."""

    def __init__(self, config: GatewayConfig, on_chunk_received: Callable[[bytes], None]) -> None:
        self.config = config
        self.on_chunk_received = on_chunk_received
        self._running = False
        self._thread: threading.Thread | None = None
        self._socket: socket.socket | None = None

    def start(self) -> None:
        """Start receiver thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="MAVLinkReceiverThread")
        self._thread.start()
        logger.info(f"MAVLink receiver started on source: {self.config.mavlink_source}")

    def stop(self) -> None:
        """Stop receiver thread and close active sockets."""
        self._running = False
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("MAVLink receiver stopped")

    def _run(self) -> None:
        source = self.config.mavlink_source.strip()
        if source.startswith("udp:"):
            self._run_udp(source)
        elif source.startswith("tcp:"):
            self._run_tcp(source)
        elif source.startswith("serial:"):
            logger.error(
                f"Serial transport '{source}' requested but native serial driver requires hardware validation. "
                "Serial transport is currently unvalidated in software emulation."
            )
            raise NotImplementedError("Serial transport requires hardware testbed validation.")
        else:
            logger.warning(f"Unrecognized connection protocol for '{source}'. Defaulting to UDP.")
            self._run_udp(source)

    def _run_udp(self, source: str) -> None:
        """UDP Socket Listener with multi-frame extraction per datagram."""
        parts = source.replace("udp:", "").split(":")
        host = parts[0] if parts[0] else "0.0.0.0"
        port = int(parts[1]) if len(parts) > 1 else 14550

        while self._running:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
                sock.settimeout(1.0)
                self._socket = sock
                logger.info(f"UDP listener bound to {host}:{port}")

                while self._running:
                    try:
                        data, addr = sock.recvfrom(65535)
                        if not data:
                            continue
                        # A single UDP packet may contain multiple MAVLink frames
                        frames, remaining = extract_mavlink_frames(bytearray(data))
                        if frames:
                            for frame in frames:
                                self.on_chunk_received(frame)
                        else:
                            # Forward raw datagram if no recognized frame sync byte
                            self.on_chunk_received(data)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self._running:
                            logger.error(f"UDP socket read error: {e}")
                            break
            except Exception as e:
                if self._running:
                    logger.error(f"Failed to bind UDP socket ({host}:{port}): {e}. Retrying in 2s...")
                    time.sleep(2.0)
            finally:
                if self._socket:
                    try:
                        self._socket.close()
                    except Exception:
                        pass
                    self._socket = None

    def _run_tcp(self, source: str) -> None:
        """TCP Stream Listener with partial read assembly and frame preservation."""
        parts = source.replace("tcp:", "").split(":")
        host = parts[0] if parts[0] else "127.0.0.1"
        port = int(parts[1]) if len(parts) > 1 else 5760

        while self._running:
            rx_buf = bytearray()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                logger.info(f"Connecting TCP to {host}:{port}...")
                sock.connect((host, port))
                sock.settimeout(1.0)
                self._socket = sock
                logger.info(f"TCP connection established to {host}:{port}")

                while self._running:
                    try:
                        data = sock.recv(4096)
                        if not data:
                            logger.warning("TCP connection closed by remote host")
                            break
                        rx_buf.extend(data)
                        frames, rx_buf = extract_mavlink_frames(rx_buf)
                        for frame in frames:
                            self.on_chunk_received(frame)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        if self._running:
                            logger.error(f"TCP read error: {e}")
                            break
            except Exception as e:
                if self._running:
                    logger.error(f"TCP connection failed ({host}:{port}): {e}. Retrying in 3s...")
                    time.sleep(3.0)
            finally:
                if self._socket:
                    try:
                        self._socket.close()
                    except Exception:
                        pass
                    self._socket = None
