"""Server-side listeners: UDP MAVLink and MQTT feeding the job queue, then the worker/pipeline.

UDP tests use real localhost sockets. MQTT tests use the in-memory broker TEST DOUBLE (app/listeners/testing.py):
they prove subscribe / filter / reconnect / back-pressure logic, not behaviour against a real broker."""
from __future__ import annotations

import asyncio
import json
import socket
import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import func, select

from app.core import secrets
from app.listeners import common, mqtt
from app.listeners.common import JobSink
from app.listeners.mqtt import MqttListener, topic_matches, validate_mqtt_config
from app.listeners.supervisor import Supervisor
from app.listeners.testing import InMemoryBroker
from app.listeners.udp_mavlink import ListenerRefused, run_udp, validate_udp_config
from app.models.background_job import BackgroundJob, JobStatus
from app.models.data_source import DataSource
from app.models.hums import HUMSSensorReading
from app.services import job_handlers, job_service
from tests.integration.test_acquisition_pipeline import _drone, _org, _source
from tests.unit.test_m20_mavlink_integrity import heartbeat, vibration


def session_factory_for(db):
    @contextmanager
    def factory():
        yield db
    return factory


def free_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def jobs_for(db, org_id):
    return db.execute(select(BackgroundJob).where(
        BackgroundJob.organization_id == org_id, BackgroundJob.job_type == job_handlers.INGEST)).scalars().all()


# ------------------------------------------------------------------ configuration is fail-closed
def test_udp_listener_refuses_to_start_without_a_protection():
    with pytest.raises(ListenerRefused, match="allowed_cidrs"):
        validate_udp_config({"listen": {"udp_port": 14550, "bind": "0.0.0.0"}}, None)
    with pytest.raises(ListenerRefused):
        validate_udp_config({"listen": {"udp_port": 14550}, "require_signing": True}, "datasource/unset/key")  # no key
    with pytest.raises(ListenerRefused, match="udp_port"):
        validate_udp_config({"listen": {"allowed_cidrs": ["10.0.0.0/8"]}}, None)
    with pytest.raises(ListenerRefused, match="CIDR"):
        validate_udp_config({"listen": {"udp_port": 1, "allowed_cidrs": ["not-a-cidr"]}}, None)
    ok = validate_udp_config({"listen": {"udp_port": 14550, "allowed_cidrs": ["10.0.0.0/8"]}}, None)
    assert ok.port == 14550 and ok.bind == "127.0.0.1" and not ok.signed          # default bind is loopback


def test_udp_listener_accepts_signing_as_the_protection(monkeypatch):
    monkeypatch.setenv(secrets.env_name("datasource/x/key"), "passphrase")
    cfg = validate_udp_config({"listen": {"udp_port": 14550}}, "datasource/x/key")
    assert cfg.signed and cfg.nets == []
    with pytest.raises(ListenerRefused):                                            # explicitly disabled signing
        validate_udp_config({"listen": {"udp_port": 14550}, "require_signing": False}, "datasource/x/key")


def test_mqtt_config_validation(monkeypatch):
    with pytest.raises(ListenerRefused, match="plaintext"):
        validate_mqtt_config({"listen": {"host": "broker.example.com", "topics": ["a/#"]}}, None)
    with pytest.raises(ListenerRefused, match="topics"):
        validate_mqtt_config({"listen": {"host": "localhost"}}, None)
    with pytest.raises(ListenerRefused, match="#"):
        validate_mqtt_config({"listen": {"host": "localhost", "topics": ["a/#/b"]}}, None)
    monkeypatch.setenv(secrets.env_name("datasource/m/pw"), "s3cret")
    s = validate_mqtt_config({"listen": {"host": "broker.example.com", "tls": True, "topics": ["a/#"], "username": "u"}},
                             "datasource/m/pw")
    assert s.port == 8883 and s.password == "s3cret" and "s3cret" not in repr(s)


@pytest.mark.parametrize("flt,topic,ok", [
    ("a/b", "a/b", True), ("a/+", "a/x", True), ("a/+", "a/x/y", False), ("a/#", "a/x/y", True), ("a/#", "a", True),
    ("+/telemetry", "d1/telemetry", True), ("+/telemetry", "d1/other", False), ("#", "any/thing", True),
])
def test_topic_matching(flt, topic, ok):
    assert topic_matches(flt, topic) is ok


# ------------------------------------------------------------------ sink: bounded memory + back-pressure
def test_sink_bounds_memory_and_sheds_load_at_queue_depth(client, db_session):
    org_id, h = _org(client, db_session, "sink")
    sid = uuid.UUID(_source(client, h, "MAVLINK", {"listen": {}}, active=False))
    sink = JobSink(organization_id=org_id, data_source_id=sid, session_factory=session_factory_for(db_session),
                   protocol="test", max_queue_depth=2)
    assert sink.add(b"x" * 10) and not sink.add(b"y" * common.MAX_BUFFER_BYTES)     # bounded buffer
    assert sink.flush() is True and sink.flush() is False                             # empty flush is a no-op
    sink.submit(b"second")
    assert len(jobs_for(db_session, org_id)) == 2
    assert sink.submit(b"third") is False                                              # depth reached: shed, not queued
    assert len(jobs_for(db_session, org_id)) == 2


def test_sink_enqueue_failure_is_swallowed_and_counted():
    @contextmanager
    def broken():
        raise RuntimeError("db down")
        yield

    sink = JobSink(organization_id=uuid.uuid4(), data_source_id=uuid.uuid4(), session_factory=broken, protocol="test")
    assert sink.submit(b"x") is False          # must not raise into the receive loop


# ------------------------------------------------------------------ UDP end to end
def _run_udp(sink, settings, datagrams, *, settle=0.4):
    async def go():
        stop, ready = asyncio.Event(), asyncio.Event()
        addr = {}
        task = asyncio.create_task(run_udp(sink, settings, stop, flush_interval=0.1,
                                           on_ready=lambda a: (addr.update(a=a), ready.set())))
        await asyncio.wait_for(ready.wait(), 5)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as tx:
            for d in datagrams:
                tx.sendto(d, addr["a"])
        await asyncio.sleep(settle)
        stop.set()
        await task
    asyncio.run(go())


def test_udp_datagrams_become_ingest_jobs_that_the_worker_processes(client, db_session):
    org_id, h = _org(client, db_session, "udp")
    asset = _drone(client, h)
    port = free_udp_port()
    cfg = {"system_id_map": {"1": asset}, "listen": {"bind": "127.0.0.1", "udp_port": port, "allowed_cidrs": ["127.0.0.0/8"]}}
    sid = _source(client, h, "MAVLINK", cfg)
    src = db_session.get(DataSource, uuid.UUID(sid))
    settings = validate_udp_config(src.connection_config, src.secret_reference)
    sink = JobSink(organization_id=org_id, data_source_id=src.id, session_factory=session_factory_for(db_session), protocol="udp")

    _run_udp(sink, settings, [heartbeat(seq=1), vibration(1.5, 1.6, 1.7, seq=2), vibration(1.5, 1.6, 1.7, seq=3)])
    jobs = jobs_for(db_session, org_id)
    assert jobs and all(j.organization_id == org_id and j.data_source_id == src.id for j in jobs)

    while job_service.run_one(db_session, worker_id="w", job_types=[job_handlers.INGEST]):
        pass
    assert {j.status for j in jobs_for(db_session, org_id)} == {JobStatus.SUCCEEDED}
    n = db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org_id))
    assert n == 2                                                       # both vibration frames, via listener->queue->worker


def test_udp_source_outside_the_allow_list_is_dropped(client, db_session):
    org_id, h = _org(client, db_session, "udp2")
    port = free_udp_port()
    sid = uuid.UUID(_source(client, h, "MAVLINK", {"listen": {"udp_port": port, "allowed_cidrs": ["10.0.0.0/8"]}}))
    settings = validate_udp_config({"listen": {"udp_port": port, "allowed_cidrs": ["10.0.0.0/8"]}}, None)
    sink = JobSink(organization_id=org_id, data_source_id=sid, session_factory=session_factory_for(db_session), protocol="udp")
    _run_udp(sink, settings, [vibration(seq=1)])
    assert jobs_for(db_session, org_id) == []


def test_udp_oversize_datagrams_are_dropped(client, db_session):
    org_id, h = _org(client, db_session, "udp3")
    port = free_udp_port()
    sid = uuid.UUID(_source(client, h, "MAVLINK", {"listen": {"udp_port": port, "allowed_cidrs": ["127.0.0.0/8"]}}))
    settings = validate_udp_config({"listen": {"udp_port": port, "allowed_cidrs": ["127.0.0.0/8"]}}, None)
    sink = JobSink(organization_id=org_id, data_source_id=sid, session_factory=session_factory_for(db_session), protocol="udp")
    _run_udp(sink, settings, [b"\x00" * 4000])
    assert jobs_for(db_session, org_id) == []


# ------------------------------------------------------------------ MQTT
def _mqtt_env(client, db_session, tag):
    org_id, h = _org(client, db_session, tag)
    asset = _drone(client, h, reg=f"MQ-{tag}")
    sid = uuid.UUID(_source(client, h, "MQTT", {"listen": {"host": "localhost", "topics": ["fleet/+/telemetry"]}}))
    settings = validate_mqtt_config({"listen": {"host": "localhost", "topics": ["fleet/+/telemetry"], "username": "kota"}}, None)
    sink = JobSink(organization_id=org_id, data_source_id=sid, session_factory=session_factory_for(db_session), protocol="mqtt")
    return org_id, asset, sid, settings, sink


def test_mqtt_messages_are_filtered_queued_and_reconnect_after_a_drop(client, db_session, monkeypatch):
    monkeypatch.setattr(mqtt, "BACKOFF_MIN", 0.05)
    org_id, asset, sid, settings, sink = _mqtt_env(client, db_session, "mq1")
    broker = InMemoryBroker()
    broker.fail_connects = 2                                          # broker down for the first two attempts
    msg = lambda v: json.dumps({"asset_id": f"MQ-mq1", "sensor_code": "VIB", "value": v, "unit": "mm/s",     # noqa: E731
                                "timestamp": f"2026-01-01T12:00:0{int(v)}Z"}).encode()

    async def go():
        stop = asyncio.Event()
        listener = MqttListener(sink, settings, broker.client)
        task = asyncio.create_task(listener.run(stop))
        await asyncio.wait_for(listener.connected.wait(), 5)          # connected only after 2 refused attempts
        assert len(broker.connect_log) == 3 and broker.connect_log[-1]["username"] == "kota"
        assert broker.publish("fleet/d1/telemetry", msg(1)) == 1
        assert broker.publish("other/d1/telemetry", msg(2)) == 0      # not subscribed: never delivered
        listener.on_message("other/x/telemetry", msg(2))              # ...and rejected even if a broker misdelivers it
        listener.on_message("fleet/d1/telemetry", b"")                # empty payload dropped
        broker.drop_all_connections()                                 # network partition
        await asyncio.wait_for(_reconnected(listener, broker), 5)
        assert broker.publish("fleet/d1/telemetry", msg(3)) == 1      # subscriptions restored after reconnect
        stop.set()
        await task

    async def _reconnected(listener, br):
        await asyncio.sleep(0.02)
        while not listener.connected.is_set() or not any(c.connected for c in br.clients):
            await asyncio.sleep(0.02)

    asyncio.run(go())
    jobs = jobs_for(db_session, org_id)
    assert len(jobs) == 2 and all(j.payload["topic"] == "fleet/d1/telemetry" for j in jobs)
    while job_service.run_one(db_session, worker_id="w", job_types=[job_handlers.INGEST]):
        pass
    n = db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org_id))
    assert n == 2


def test_mqtt_redelivery_is_a_duplicate_not_double_counted(client, db_session):
    org_id, asset, sid, settings, sink = _mqtt_env(client, db_session, "mq2")
    listener = MqttListener(sink, settings, InMemoryBroker().client)
    body = json.dumps({"asset_id": "MQ-mq2", "sensor_code": "VIB", "value": 2.0, "unit": "mm/s",
                       "timestamp": "2026-01-01T12:00:00Z"}).encode()
    listener.on_message("fleet/d1/telemetry", body)
    listener.on_message("fleet/d1/telemetry", body)                   # QoS-1 redelivery
    while job_service.run_one(db_session, worker_id="w", job_types=[job_handlers.INGEST]):
        pass
    n = db_session.scalar(select(func.count(HUMSSensorReading.id)).where(HUMSSensorReading.organization_id == org_id))
    assert n == 1


# ------------------------------------------------------------------ supervisor
def test_supervisor_starts_active_sources_refuses_unsafe_ones_and_follows_status_changes(client, db_session):
    org_id, h = _org(client, db_session, "sup")
    port = free_udp_port()
    safe = _source(client, h, "MAVLINK", {"listen": {"udp_port": port, "allowed_cidrs": ["127.0.0.0/8"]}})
    unsafe = _source(client, h, "MAVLINK", {"listen": {"udp_port": free_udp_port()}})
    no_listen = _source(client, h, "MAVLINK", {})
    factory = session_factory_for(db_session)

    async def go():
        sup = Supervisor(session_factory=factory, reconcile_seconds=0.1, flush_interval=0.1)
        await sup.reconcile()
        assert set(sup.running) == {uuid.UUID(safe)}                  # unsafe refused, no-listen ignored
        assert uuid.UUID(unsafe) in sup.refused
        await sup.reconcile()                                          # unchanged: nothing restarts, no re-refusal churn
        assert set(sup.running) == {uuid.UUID(safe)}
        client.patch(f"/api/v1/data-sources/{safe}", headers=h, json={"status": "PAUSED"})
        await sup.reconcile()
        assert sup.running == {}                                      # paused source stops listening
        await sup.shutdown()

    asyncio.run(go())
    err = db_session.get(DataSource, uuid.UUID(unsafe)).last_error
    assert err and err.startswith("listener refused:") and "allowed_cidrs" in err
    assert no_listen  # noqa: S101 (created only to prove it is ignored)
