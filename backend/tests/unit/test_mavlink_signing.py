"""MAVLink 2 signing verification.

The signer below is written from the MAVLink 2 signing spec (signature = first 48 bits of
SHA-256(secret_key + header + payload + CRC + link_id + timestamp)), independently of the connector's verifier.
It was NOT cross-checked against pymavlink (not installed here): interoperability with a real autopilot's signer is
part of the hardware bench plan."""
from __future__ import annotations

import hashlib
import struct

import pytest

from app.core import secrets
from app.services.edge import mavlink_connector as mc
from app.services.edge.mavlink_connector import MAVLinkConnector, mavlink_checksum

KEY = bytes(range(32))


def signed_frame(msgid, payload, *, key=KEY, ts=1000, link=0, seq=0, sysid=1, compid=1):
    payload = payload.rstrip(b"\x00") or b"\x00"
    header = bytes([mc.MAVLINK_STX_V2, len(payload), 1, 0, seq & 0xFF, sysid, compid, msgid & 0xFF,
                    (msgid >> 8) & 0xFF, (msgid >> 16) & 0xFF])
    crc = struct.pack("<H", mavlink_checksum(header[1:] + payload, msgid))
    ts_b = ts.to_bytes(6, "little")
    sig = hashlib.sha256(key + header + payload + crc + bytes([link]) + ts_b).digest()[:6]
    return header + payload + crc + bytes([link]) + ts_b + sig


def vib(**kw):
    return signed_frame(241, struct.pack("<QfffIII", 1, 3.0, 4.0, 5.0, 0, 0, 0), **kw)


def test_valid_signature_is_accepted():
    c = MAVLinkConnector(signing_key=KEY)
    assert len(c.feed_bytes(vib(seq=1, ts=10))) == 1
    assert c.integrity["signed_frames"] == 1 and c.integrity["bad_signature"] == 0


def test_wrong_key_tampered_payload_and_tampered_signature_are_rejected():
    c = MAVLinkConnector(signing_key=KEY)
    assert c.feed_bytes(vib(seq=1, key=b"\xff" * 32)) == []
    good = bytearray(vib(seq=2, ts=20))
    tampered = bytearray(good)
    tampered[12] ^= 0x01                      # payload byte flipped: CRC now fails first
    assert c.feed_bytes(bytes(tampered)) == []
    sig_flip = bytearray(good)
    sig_flip[-1] ^= 0x01                      # only the signature is wrong
    assert c.feed_bytes(bytes(sig_flip)) == []
    assert c.integrity["bad_signature"] >= 2
    assert len(c.feed_bytes(bytes(good))) == 1        # the untouched frame still passes


def test_replayed_frame_and_older_timestamp_are_rejected():
    c = MAVLinkConnector(signing_key=KEY)
    frame = vib(seq=1, ts=500)
    assert len(c.feed_bytes(frame)) == 1
    assert c.feed_bytes(frame) == []                                  # exact replay
    assert c.feed_bytes(vib(seq=2, ts=499)) == []                     # valid signature, stale timestamp
    assert c.integrity["replayed_signature"] == 2
    assert len(c.feed_bytes(vib(seq=3, ts=501))) == 1                 # newer timestamp is fine


def test_timestamps_are_tracked_per_link_and_per_vehicle():
    c = MAVLinkConnector(signing_key=KEY)
    assert len(c.feed_bytes(vib(seq=1, ts=900, link=0))) == 1
    assert len(c.feed_bytes(vib(seq=2, ts=100, link=1))) == 1         # other link: its own clock
    assert len(c.feed_bytes(vib(seq=1, ts=100, sysid=2))) == 1        # other vehicle


def test_unsigned_and_v1_frames_are_refused_when_a_key_is_configured():
    from tests.unit.test_m20_mavlink_integrity import vibration

    c = MAVLinkConnector(signing_key=KEY)
    assert c.feed_bytes(vibration(seq=1)) == []
    assert c.integrity["unsigned_rejected"] == 1
    v1 = bytes([mc.MAVLINK_STX_V1, 32, 0, 1, 1, 241]) + b"\x00" * 32
    v1 += struct.pack("<H", mavlink_checksum(v1[1:], 241))
    assert c.feed_bytes(v1) == []


def test_forged_frames_cannot_poison_sequence_tracking():
    c = MAVLinkConnector(signing_key=KEY)
    assert len(c.feed_bytes(vib(seq=10, ts=1))) == 1
    c.feed_bytes(vib(seq=200, ts=2, key=b"\x01" * 32))                # forged far-ahead sequence
    assert len(c.feed_bytes(vib(seq=11, ts=3))) == 1                  # genuine stream continues
    assert c.integrity["lost"] == 0


def test_no_key_keeps_previous_behaviour_and_require_signed_alone_fails_closed():
    c = MAVLinkConnector()
    assert len(c.feed_bytes(vib(seq=1, key=b"\x09" * 32))) == 1       # unverified, framed and counted only
    closed = MAVLinkConnector(require_signed=True)                    # required but no key: reject everything
    assert closed.feed_bytes(vib(seq=1)) == []


def test_key_must_be_32_bytes():
    with pytest.raises(ValueError):
        MAVLinkConnector(signing_key=b"short")


def test_secret_reference_resolution(monkeypatch):
    monkeypatch.setenv("KOTA_SECRET_DATASOURCE_ORG_1_SRC_2_MAVLINK_KEY", "abc")
    assert secrets.resolve("datasource/org-1/src-2/mavlink_key") == "abc"
    assert secrets.resolve("datasource/org-1/src-2/other") is None
    assert secrets.resolve(None) is None and secrets.resolve("  ") is None
