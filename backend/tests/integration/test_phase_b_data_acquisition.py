"""Phase B — Automated Aerospace Data Acquisition Tests.

Covers:
- B1: DataSource model, service CRUD, tenant isolation, delete guards
- B1: DataSource API endpoints (create, list, get, update, delete, stats overview)
- B2: MQTTConnector — canonical, compact sensor, flat OEM, topic asset extraction
- B3: CSVBatchConnector — flexible column mapping, multi-row, parse errors, size limits
- B3: JSONBatchConnector — array, wrapped, single object, NDJSON, canonical
- Cross-boundary: verify connector produces NormalizedTelemetryEvent that passes
  telemetry_service.process_normalized_event without errors
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime

import pytest

from app.models.data_source import DataSource, DataSourceConnectorType, DataSourceStatus
from app.schemas.data_source import DataSourceCreate, DataSourceUpdate
from app.services import data_source_service
from app.services.data_source_service import DataSourceError
from app.services.edge.batch_connectors import CSVBatchConnector, JSONBatchConnector
from app.services.edge.mqtt_connector import MQTTConnector


# ===========================================================================
# Helpers
# ===========================================================================


def _org_id() -> uuid.UUID:
    return uuid.uuid4()


def _make_data_source_payload(
    name: str | None = None,
    connector_type: str = DataSourceConnectorType.MQTT,
) -> DataSourceCreate:
    return DataSourceCreate(
        name=name or f"test-source-{uuid.uuid4().hex[:8]}",
        connector_type=connector_type,
        connection_config={"host": "broker.example.com", "port": 1883, "topic": "kota/#"},
    )


# ===========================================================================
# B1: DataSource Model & Service — Unit Tests (no DB)
# ===========================================================================


class TestDataSourceConstants:
    def test_connector_types_defined(self):
        for ct in [
            DataSourceConnectorType.MAVLINK,
            DataSourceConnectorType.MQTT,
            DataSourceConnectorType.DJI_FLIGHTHUB,
            DataSourceConnectorType.CSV_BATCH,
            DataSourceConnectorType.JSON_BATCH,
            DataSourceConnectorType.OEM_API,
            DataSourceConnectorType.GENERIC_WEBHOOK,
        ]:
            assert ct in DataSourceConnectorType.ALL

    def test_status_values(self):
        statuses = {
            DataSourceStatus.DRAFT,
            DataSourceStatus.ACTIVE,
            DataSourceStatus.PAUSED,
            DataSourceStatus.DECOMMISSIONED,
        }
        assert len(statuses) == 4

    def test_connector_type_all_is_frozen_set(self):
        assert isinstance(DataSourceConnectorType.ALL, frozenset)
        assert len(DataSourceConnectorType.ALL) == 7


class TestDataSourceSchema:
    def test_valid_create_schema(self):
        payload = DataSourceCreate(
            name="MQTT Primary",
            connector_type=DataSourceConnectorType.MQTT,
            connection_config={"host": "broker.local", "port": 1883},
        )
        assert payload.connector_type == "MQTT"
        assert payload.connection_config["host"] == "broker.local"

    def test_invalid_connector_type_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="connector_type"):
            DataSourceCreate(
                name="Bad Type",
                connector_type="FOOBAR",
                connection_config={},
            )

    def test_invalid_status_in_update_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="status"):
            DataSourceUpdate(status="NOT_A_STATUS")

    def test_valid_update_schema(self):
        upd = DataSourceUpdate(status=DataSourceStatus.ACTIVE, name="New Name")
        assert upd.status == "ACTIVE"
        assert upd.name == "New Name"

    def test_all_fields_optional_in_update(self):
        upd = DataSourceUpdate()
        assert upd.name is None
        assert upd.status is None

    def test_secret_reference_not_in_connection_config(self):
        """Validate that secret_reference is separate from connection_config."""
        payload = DataSourceCreate(
            name="Secure MQTT",
            connector_type=DataSourceConnectorType.MQTT,
            connection_config={"host": "broker.local"},
            secret_reference="secrets/org/src/password",
        )
        assert "password" not in payload.connection_config
        assert payload.secret_reference == "secrets/org/src/password"


class TestComputeHealth:
    def _source(self, status: str, failures: int):
        """Build a minimal duck-typed object that compute_health() can use."""
        from types import SimpleNamespace
        return SimpleNamespace(status=status, consecutive_failures=failures)

    def test_active_zero_failures_is_healthy(self):
        s = self._source(DataSourceStatus.ACTIVE, 0)
        assert data_source_service.compute_health(s) == "HEALTHY"

    def test_active_two_failures_is_degraded(self):
        s = self._source(DataSourceStatus.ACTIVE, 2)
        assert data_source_service.compute_health(s) == "DEGRADED"

    def test_active_five_failures_is_failed(self):
        s = self._source(DataSourceStatus.ACTIVE, 5)
        assert data_source_service.compute_health(s) == "FAILED"

    def test_paused_is_inactive(self):
        s = self._source(DataSourceStatus.PAUSED, 0)
        assert data_source_service.compute_health(s) == "INACTIVE"

    def test_decommissioned_is_inactive(self):
        s = self._source(DataSourceStatus.DECOMMISSIONED, 0)
        assert data_source_service.compute_health(s) == "INACTIVE"

    def test_draft_is_inactive(self):
        s = self._source(DataSourceStatus.DRAFT, 99)
        assert data_source_service.compute_health(s) == "INACTIVE"


# ===========================================================================
# B2: MQTT Connector — Unit Tests
# ===========================================================================


class TestMQTTConnectorConnection:
    def test_connect_returns_true(self):
        c = MQTTConnector(connector_id="test-mqtt")
        assert c.connect("mqtt://broker:1883") is True

    def test_disconnect_sets_state(self):
        from app.services.edge.connector_base import ConnectorState

        c = MQTTConnector(connector_id="test-mqtt")
        c.connect("mqtt://broker:1883")
        c.disconnect()
        assert c.state == ConnectorState.DISCONNECTED

    def test_connection_config_returned(self):
        c = MQTTConnector(
            connector_id="test-mqtt",
            topic_filter="kota/telemetry/#",
            source_system="MY_MQTT",
        )
        c.connect("mqtt://broker:1883")
        cfg = c.get_connection_config()
        assert cfg["endpoint_uri"] == "mqtt://broker:1883"
        assert cfg["topic_filter"] == "kota/telemetry/#"
        assert cfg["source_system"] == "MY_MQTT"


class TestMQTTConnectorCanonicalFormat:
    def _make_canonical_payload(self, asset_id: str = "DRONE-001") -> dict:
        return {
            "source_system": "EXTERNAL_SYSTEM",
            "source_event_id": f"EVT-{uuid.uuid4().hex[:12]}",
            "source_asset_id": asset_id,
            "event_type": "TELEMETRY_PING",
            "event_timestamp": datetime.now(UTC).isoformat(),
            "readings": [
                {
                    "sensor_code": "TEMP_ENGINE",
                    "sensor_type": "THERMAL",
                    "measurement_type": "TEMPERATURE",
                    "value": 82.5,
                    "unit": "degC",
                    "data_quality": "VALID",
                }
            ],
        }

    def test_canonical_payload_produces_event(self):
        c = MQTTConnector(connector_id="test-mqtt")
        c.connect("mqtt://broker:1883")
        payload = self._make_canonical_payload("DRONE-001")
        raw = json.dumps(payload).encode("utf-8")
        events = c.feed_bytes(raw, topic="kota/telemetry/test")
        assert len(events) == 1
        assert events[0].source_asset_id == "DRONE-001"
        assert events[0].source_system == "EXTERNAL_SYSTEM"

    def test_canonical_reading_preserved(self):
        c = MQTTConnector(connector_id="test-mqtt")
        c.connect("mqtt://broker:1883")
        payload = self._make_canonical_payload()
        events = c.feed_bytes(json.dumps(payload).encode(), topic="test")
        assert len(events[0].readings) == 1
        assert events[0].readings[0].sensor_code == "TEMP_ENGINE"
        assert events[0].readings[0].value == 82.5

    def test_stats_updated_after_message(self):
        c = MQTTConnector(connector_id="test-mqtt")
        c.connect("mqtt://broker:1883")
        payload = self._make_canonical_payload()
        c.feed_bytes(json.dumps(payload).encode(), topic="test")
        assert c.stats.messages_received == 1
        assert c.stats.events_generated == 1
        assert c.stats.bytes_received > 0


class TestMQTTConnectorCompactSensor:
    def test_compact_sensor_produces_reading(self):
        c = MQTTConnector(connector_id="test-compact", source_system="SENSOR_NET")
        c.connect("mqtt://broker:1883")
        payload = {
            "sensor_code": "VIB_X",
            "measurement_type": "VIBRATION",
            "value": 3.14,
            "unit": "mm/s",
            "asset_id": "DRONE-SN-99",
        }
        events = c.feed_bytes(json.dumps(payload).encode(), topic="sensors/DRONE-SN-99")
        assert len(events) == 1
        assert events[0].readings[0].sensor_code == "VIB_X"
        assert events[0].readings[0].value == 3.14

    def test_compact_sensor_asset_from_payload(self):
        c = MQTTConnector(connector_id="test-compact")
        c.connect("mqtt://broker:1883")
        payload = {"sensor_code": "BATT_V", "value": 11.8, "unit": "V", "asset_id": "DRONE-ALPHA"}
        # Use empty topic so _extract_asset_from_topic returns None, forcing payload fallback
        events = c.feed_bytes(json.dumps(payload).encode(), topic="")
        assert events[0].source_asset_id == "DRONE-ALPHA"

    def test_compact_sensor_event_type_is_ping(self):
        c = MQTTConnector(connector_id="test-compact")
        c.connect("mqtt://broker:1883")
        payload = {"sensor_code": "TEMP", "value": 50.0, "unit": "degC", "device_sn": "SN-42"}
        events = c.feed_bytes(json.dumps(payload).encode(), topic="t")
        assert events[0].event_type == "TELEMETRY_PING"


class TestMQTTConnectorFlatOEM:
    def test_flat_oem_extracts_numeric_readings(self):
        c = MQTTConnector(connector_id="test-oem", source_system="OEM_TELEMETRY")
        c.connect("mqtt://broker:1883")
        payload = {
            "device_sn": "OEM-DRONE-001",
            "temperature": 45.2,
            "voltage": 22.8,
            "rpm": 1200.0,
            "status": "ACTIVE",
        }
        events = c.feed_bytes(json.dumps(payload).encode(), topic="oem/telemetry")
        assert len(events) == 1
        reading_codes = {r.sensor_code for r in events[0].readings}
        assert "TEMPERATURE" in reading_codes
        assert "VOLTAGE" in reading_codes
        assert "RPM" in reading_codes
        assert "STATUS" not in reading_codes  # non-numeric

    def test_flat_oem_asset_id_from_device_sn(self):
        c = MQTTConnector(connector_id="test-oem")
        c.connect("mqtt://broker:1883")
        payload = {"device_sn": "MY-DEVICE-42", "temp": 30.0}
        # Empty topic forces fallback to device_sn in payload
        events = c.feed_bytes(json.dumps(payload).encode(), topic="")
        assert events[0].source_asset_id == "MY-DEVICE-42"


class TestMQTTConnectorTopicAssetExtraction:
    def test_uuid_in_topic_extracted(self):
        c = MQTTConnector(connector_id="test-topic")
        drone_id = str(uuid.uuid4())
        result = c._extract_asset_from_topic(f"kota/telemetry/{drone_id}/PING")
        assert result == drone_id

    def test_no_uuid_returns_last_segment(self):
        c = MQTTConnector(connector_id="test-topic")
        result = c._extract_asset_from_topic("kota/telemetry/DRONE-ALPHA")
        assert result == "DRONE-ALPHA"

    def test_empty_topic_returns_none(self):
        c = MQTTConnector(connector_id="test-topic")
        result = c._extract_asset_from_topic("")
        assert result is None


class TestMQTTConnectorErrorHandling:
    def test_invalid_json_produces_no_events(self):
        c = MQTTConnector(connector_id="test-err")
        c.connect("mqtt://broker:1883")
        events = c.feed_bytes(b"NOT VALID JSON", topic="t")
        assert events == []
        assert c.stats.parse_errors == 1

    def test_missing_value_in_compact_handled_gracefully(self):
        c = MQTTConnector(connector_id="test-err")
        c.connect("mqtt://broker:1883")
        # No 'value' field — should fall through to flat OEM decoder
        payload = {"sensor_code": "TEMP", "asset_id": "D1"}
        events = c.feed_bytes(json.dumps(payload).encode(), topic="t")
        # Flat OEM will produce no numeric readings since nothing numeric remains
        assert isinstance(events, list)

    def test_stats_parse_error_increments(self):
        c = MQTTConnector(connector_id="test-err")
        c.connect("mqtt://broker:1883")
        c.feed_bytes(b"bad", topic="t")
        c.feed_bytes(b"alsobad", topic="t")
        assert c.stats.parse_errors == 2


# ===========================================================================
# B3: CSV Batch Connector — Unit Tests
# ===========================================================================


def _make_csv_bytes(rows: list[dict]) -> bytes:
    """Builds CSV bytes from a list of row dicts."""
    if not rows:
        return b""
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


class TestCSVBatchConnector:
    def test_single_row_produces_event(self):
        c = CSVBatchConnector(connector_id="csv-1", source_system="CSV_BATCH")
        rows = [{"asset_id": "DRONE-01", "sensor_code": "TEMP", "value": "45.5", "unit": "degC"}]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.parsed == 1
        assert result.errors == 0
        assert result.events[0].readings[0].value == 45.5

    def test_multi_row_produces_multiple_events(self):
        c = CSVBatchConnector(connector_id="csv-2")
        rows = [
            {"device_sn": "SN-1", "sensor_code": "BATT_V", "value": "22.5", "unit": "V"},
            {"device_sn": "SN-2", "sensor_code": "BATT_V", "value": "21.8", "unit": "V"},
            {"device_sn": "SN-3", "sensor_code": "RPM", "value": "1200.0", "unit": "rpm"},
        ]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.parsed == 3
        assert result.total_rows == 3

    def test_asset_id_resolution_priority(self):
        """asset_id takes precedence over device_sn."""
        c = CSVBatchConnector(connector_id="csv-3")
        rows = [{"asset_id": "PRIM-ID", "device_sn": "SEC-ID", "sensor_code": "TEMP", "value": "30.0", "unit": ""}]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.events[0].source_asset_id == "PRIM-ID"

    def test_invalid_value_counts_as_error(self):
        c = CSVBatchConnector(connector_id="csv-4")
        rows = [{"asset_id": "D1", "sensor_code": "TEMP", "value": "NOT_A_NUMBER", "unit": "degC"}]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.parsed == 0
        assert result.errors == 1

    def test_missing_asset_id_counts_as_error(self):
        c = CSVBatchConnector(connector_id="csv-5")
        rows = [{"sensor_code": "TEMP", "value": "10.0", "unit": ""}]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.errors == 1
        assert result.parsed == 0

    def test_mixed_valid_invalid_rows(self):
        c = CSVBatchConnector(connector_id="csv-6")
        rows = [
            {"asset_id": "D1", "sensor_code": "TEMP", "value": "30.0", "unit": "degC"},
            {"sensor_code": "TEMP", "value": "30.0", "unit": "degC"},  # no asset_id
            {"asset_id": "D2", "sensor_code": "VIB", "value": "1.5", "unit": "mm/s"},
        ]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.parsed == 2
        assert result.errors == 1

    def test_column_alias_measurement_value(self):
        """Supports 'measurement_value' as an alias for 'value'."""
        c = CSVBatchConnector(connector_id="csv-7")
        rows = [{"asset_id": "D1", "sensor_code": "PRESS", "measurement_value": "101325.0", "unit": "Pa"}]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.parsed == 1
        assert result.events[0].readings[0].value == 101325.0

    def test_column_alias_serial_number(self):
        """Supports 'serial_number' as asset identifier."""
        c = CSVBatchConnector(connector_id="csv-8")
        rows = [{"serial_number": "FC30-001", "sensor_code": "TEMP", "value": "55.0", "unit": ""}]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.events[0].source_asset_id == "FC30-001"

    def test_timestamp_parsing_iso(self):
        c = CSVBatchConnector(connector_id="csv-9")
        rows = [{"asset_id": "D1", "sensor_code": "T", "value": "10.0", "unit": "", "timestamp": "2026-01-15 10:30:00"}]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.parsed == 1
        ts = result.events[0].event_timestamp
        assert ts.year == 2026
        assert ts.month == 1

    def test_file_size_limit_enforced(self):
        c = CSVBatchConnector(connector_id="csv-size")
        oversized = b"x" * (51 * 1024 * 1024)
        with pytest.raises(ValueError, match="maximum allowed size"):
            c.process_file(oversized)

    def test_row_limit_respected(self):
        c = CSVBatchConnector(connector_id="csv-limit", max_rows=5)
        rows = [{"asset_id": "D1", "sensor_code": "T", "value": str(i), "unit": ""} for i in range(20)]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.parsed <= 5

    def test_case_insensitive_column_matching(self):
        """Column headers are matched case-insensitively."""
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["ASSET_ID", "SENSOR_CODE", "VALUE", "UNIT"])
        writer.writeheader()
        writer.writerow({"ASSET_ID": "D1", "SENSOR_CODE": "TEMP", "VALUE": "100.0", "UNIT": "degC"})
        result = c = CSVBatchConnector(connector_id="csv-case")
        result = c.process_file(buf.getvalue().encode("utf-8"))
        assert result.parsed == 1

    def test_empty_csv_produces_no_events(self):
        c = CSVBatchConnector(connector_id="csv-empty")
        result = c.process_file(b"")
        assert result.parsed == 0
        assert result.total_rows == 0

    def test_source_system_propagated(self):
        c = CSVBatchConnector(connector_id="csv-src", source_system="MY_CSV_SOURCE")
        rows = [{"asset_id": "D1", "sensor_code": "T", "value": "1.0", "unit": ""}]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.events[0].source_system == "MY_CSV_SOURCE"


# ===========================================================================
# B3: JSON Batch Connector — Unit Tests
# ===========================================================================


class TestJSONBatchConnector:
    def test_json_array_format(self):
        c = JSONBatchConnector(connector_id="json-1")
        records = [
            {"asset_id": "DRONE-01", "temperature": 45.0, "voltage": 22.5},
            {"asset_id": "DRONE-02", "temperature": 40.0, "rpm": 1100.0},
        ]
        result = c.process_file(json.dumps(records).encode())
        assert result.parsed == 2
        assert result.total_rows == 2

    def test_json_wrapped_events_key(self):
        c = JSONBatchConnector(connector_id="json-2")
        data = {
            "events": [
                {"asset_id": "D1", "voltage": 22.0},
                {"asset_id": "D2", "temperature": 35.0},
            ]
        }
        result = c.process_file(json.dumps(data).encode())
        assert result.parsed == 2

    def test_json_wrapped_data_key(self):
        c = JSONBatchConnector(connector_id="json-3")
        data = {"data": [{"asset_id": "D1", "pressure": 101000.0}]}
        result = c.process_file(json.dumps(data).encode())
        assert result.parsed == 1

    def test_json_single_object(self):
        c = JSONBatchConnector(connector_id="json-4")
        record = {"asset_id": "DRONE-99", "battery": 98.5}
        result = c.process_file(json.dumps(record).encode())
        assert result.parsed == 1
        assert result.events[0].source_asset_id == "DRONE-99"

    def test_ndjson_format(self):
        c = JSONBatchConnector(connector_id="json-5")
        lines = "\n".join([
            json.dumps({"asset_id": "D1", "temp": 30.0}),
            json.dumps({"asset_id": "D2", "temp": 35.0}),
            json.dumps({"asset_id": "D3", "temp": 28.0}),
        ])
        result = c.process_file(lines.encode())
        assert result.parsed == 3

    def test_canonical_json_format(self):
        c = JSONBatchConnector(connector_id="json-6")
        records = [{
            "source_system": "EXTERNAL_ERP",
            "source_event_id": "EVT-001",
            "source_asset_id": "DRONE-CANONICAL",
            "event_type": "FLIGHT_COMPLETED",
            "event_timestamp": datetime.now(UTC).isoformat(),
            "readings": [
                {"sensor_code": "FLIGHT_HOURS", "sensor_type": "USAGE",
                 "measurement_type": "HOURS", "value": 1.5, "unit": "h", "data_quality": "VALID"}
            ],
        }]
        result = c.process_file(json.dumps(records).encode())
        assert result.parsed == 1
        assert result.events[0].source_system == "EXTERNAL_ERP"
        assert result.events[0].source_asset_id == "DRONE-CANONICAL"

    def test_readings_list_preserved(self):
        c = JSONBatchConnector(connector_id="json-7")
        record = {
            "asset_id": "DRONE-01",
            "readings": [
                {"sensor_code": "VIB_X", "sensor_type": "MECHANICAL", "measurement_type": "VIBRATION",
                 "value": 2.5, "unit": "mm/s", "data_quality": "VALID"},
                {"sensor_code": "TEMP_M", "sensor_type": "THERMAL", "measurement_type": "TEMPERATURE",
                 "value": 75.0, "unit": "degC", "data_quality": "VALID"},
            ],
        }
        result = c.process_file(json.dumps([record]).encode())
        assert result.parsed == 1
        assert len(result.events[0].readings) == 2

    def test_missing_asset_id_counts_as_error(self):
        c = JSONBatchConnector(connector_id="json-err")
        records = [{"temperature": 30.0}]  # no asset_id
        result = c.process_file(json.dumps(records).encode())
        assert result.errors == 1
        assert result.parsed == 0

    def test_mixed_valid_invalid_records(self):
        c = JSONBatchConnector(connector_id="json-mix")
        records = [
            {"asset_id": "D1", "temp": 30.0},
            {"temperature": 28.0},  # missing asset_id
            {"asset_id": "D2", "pressure": 101325.0},
        ]
        result = c.process_file(json.dumps(records).encode())
        assert result.parsed == 2
        assert result.errors == 1

    def test_non_numeric_fields_skipped(self):
        c = JSONBatchConnector(connector_id="json-skip")
        records = [{"asset_id": "D1", "status": "ACTIVE", "mode": "MANUAL", "altitude": 100.0}]
        result = c.process_file(json.dumps(records).encode())
        assert result.parsed == 1
        codes = {r.sensor_code for r in result.events[0].readings}
        assert "ALTITUDE" in codes
        assert "STATUS" not in codes
        assert "MODE" not in codes

    def test_file_size_limit_enforced(self):
        c = JSONBatchConnector(connector_id="json-size")
        with pytest.raises(ValueError, match="maximum allowed size"):
            c.process_file(b"x" * (51 * 1024 * 1024))

    def test_record_limit_respected(self):
        c = JSONBatchConnector(connector_id="json-limit", max_records=3)
        records = [{"asset_id": f"D{i}", "temp": float(i)} for i in range(100)]
        result = c.process_file(json.dumps(records).encode())
        assert result.parsed <= 3

    def test_source_system_propagated(self):
        c = JSONBatchConnector(connector_id="json-src", source_system="MY_JSON_SOURCE")
        records = [{"asset_id": "D1", "temperature": 30.0}]
        result = c.process_file(json.dumps(records).encode())
        assert result.events[0].source_system == "MY_JSON_SOURCE"


# ===========================================================================
# B1: DataSource Service — Integration Tests (requires DB)
# ===========================================================================


@pytest.mark.integration
class TestDataSourceServiceIntegration:
    def test_create_data_source(self, db_session):
        org_id = uuid.uuid4()
        payload = _make_data_source_payload(connector_type=DataSourceConnectorType.MQTT)
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=payload
        )
        db_session.flush()
        assert source.id is not None
        assert source.organization_id == org_id
        assert source.status == DataSourceStatus.DRAFT
        assert source.connector_type == DataSourceConnectorType.MQTT
        assert source.total_events_ingested == 0

    def test_create_duplicate_name_raises(self, db_session):
        org_id = uuid.uuid4()
        name = f"dupe-{uuid.uuid4().hex[:6]}"
        data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload(name=name)
        )
        db_session.flush()
        with pytest.raises(DataSourceError, match="already exists"):
            data_source_service.create_data_source(
                db_session, organization_id=org_id, payload=_make_data_source_payload(name=name)
            )

    def test_same_name_different_org_allowed(self, db_session):
        name = f"shared-{uuid.uuid4().hex[:6]}"
        s1 = data_source_service.create_data_source(
            db_session, organization_id=uuid.uuid4(), payload=_make_data_source_payload(name=name)
        )
        s2 = data_source_service.create_data_source(
            db_session, organization_id=uuid.uuid4(), payload=_make_data_source_payload(name=name)
        )
        db_session.flush()
        assert s1.id != s2.id

    def test_get_data_source_success(self, db_session):
        from app.core.errors import NotFoundError

        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        fetched = data_source_service.get_data_source(
            db_session, organization_id=org_id, data_source_id=source.id
        )
        assert fetched.id == source.id

    def test_get_data_source_wrong_org_raises(self, db_session):
        from app.core.errors import NotFoundError

        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        with pytest.raises(NotFoundError):
            data_source_service.get_data_source(
                db_session, organization_id=uuid.uuid4(), data_source_id=source.id
            )

    def test_list_data_sources_pagination(self, db_session):
        org_id = uuid.uuid4()
        for i in range(5):
            data_source_service.create_data_source(
                db_session,
                organization_id=org_id,
                payload=_make_data_source_payload(name=f"source-{i}-{uuid.uuid4().hex[:6]}"),
            )
        db_session.flush()
        total, page = data_source_service.list_data_sources(
            db_session, organization_id=org_id, limit=3, offset=0
        )
        assert total == 5
        assert len(page) == 3

    def test_list_data_sources_filter_by_connector_type(self, db_session):
        org_id = uuid.uuid4()
        data_source_service.create_data_source(
            db_session, organization_id=org_id,
            payload=DataSourceCreate(name=f"mqtt-{uuid.uuid4().hex[:6]}", connector_type=DataSourceConnectorType.MQTT, connection_config={})
        )
        data_source_service.create_data_source(
            db_session, organization_id=org_id,
            payload=DataSourceCreate(name=f"csv-{uuid.uuid4().hex[:6]}", connector_type=DataSourceConnectorType.CSV_BATCH, connection_config={})
        )
        db_session.flush()
        _, mqtt_only = data_source_service.list_data_sources(
            db_session, organization_id=org_id, connector_type=DataSourceConnectorType.MQTT
        )
        assert all(s.connector_type == DataSourceConnectorType.MQTT for s in mqtt_only)

    def test_update_data_source_name(self, db_session):
        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload(name="old-name")
        )
        db_session.flush()
        updated = data_source_service.update_data_source(
            db_session, organization_id=org_id, data_source_id=source.id,
            payload=DataSourceUpdate(name="new-name")
        )
        assert updated.name == "new-name"

    def test_update_data_source_status_to_active(self, db_session):
        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        updated = data_source_service.update_data_source(
            db_session, organization_id=org_id, data_source_id=source.id,
            payload=DataSourceUpdate(status=DataSourceStatus.ACTIVE)
        )
        assert updated.status == DataSourceStatus.ACTIVE

    def test_update_wrong_org_raises(self, db_session):
        from app.core.errors import NotFoundError

        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        with pytest.raises(NotFoundError):
            data_source_service.update_data_source(
                db_session, organization_id=uuid.uuid4(), data_source_id=source.id,
                payload=DataSourceUpdate(name="hacked")
            )

    def test_delete_draft_source_succeeds(self, db_session):
        from app.core.errors import NotFoundError

        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        data_source_service.delete_data_source(
            db_session, organization_id=org_id, data_source_id=source.id
        )
        db_session.flush()
        with pytest.raises(NotFoundError):
            data_source_service.get_data_source(
                db_session, organization_id=org_id, data_source_id=source.id
            )

    def test_delete_active_source_raises(self, db_session):
        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        data_source_service.update_data_source(
            db_session, organization_id=org_id, data_source_id=source.id,
            payload=DataSourceUpdate(status=DataSourceStatus.ACTIVE)
        )
        with pytest.raises(DataSourceError, match="Cannot delete"):
            data_source_service.delete_data_source(
                db_session, organization_id=org_id, data_source_id=source.id
            )

    def test_delete_paused_source_raises(self, db_session):
        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        data_source_service.update_data_source(
            db_session, organization_id=org_id, data_source_id=source.id,
            payload=DataSourceUpdate(status=DataSourceStatus.PAUSED)
        )
        with pytest.raises(DataSourceError, match="Cannot delete"):
            data_source_service.delete_data_source(
                db_session, organization_id=org_id, data_source_id=source.id
            )

    def test_delete_decommissioned_source_succeeds(self, db_session):
        from app.core.errors import NotFoundError

        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        data_source_service.update_data_source(
            db_session, organization_id=org_id, data_source_id=source.id,
            payload=DataSourceUpdate(status=DataSourceStatus.DECOMMISSIONED)
        )
        data_source_service.delete_data_source(
            db_session, organization_id=org_id, data_source_id=source.id
        )
        db_session.flush()
        with pytest.raises(NotFoundError):
            data_source_service.get_data_source(
                db_session, organization_id=org_id, data_source_id=source.id
            )

    def test_record_acquisition_success(self, db_session):
        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        data_source_service.record_acquisition_success(
            db_session, organization_id=org_id, data_source_id=source.id, events_count=42
        )
        db_session.flush()
        updated = data_source_service.get_data_source(
            db_session, organization_id=org_id, data_source_id=source.id
        )
        assert updated.total_events_ingested == 42
        assert updated.consecutive_failures == 0
        assert updated.last_acquisition_at is not None

    def test_record_acquisition_failure_increments_counter(self, db_session):
        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        data_source_service.record_acquisition_failure(
            db_session, organization_id=org_id, data_source_id=source.id, rejected_count=5
        )
        data_source_service.record_acquisition_failure(
            db_session, organization_id=org_id, data_source_id=source.id, rejected_count=3
        )
        db_session.flush()
        updated = data_source_service.get_data_source(
            db_session, organization_id=org_id, data_source_id=source.id
        )
        assert updated.consecutive_failures == 2
        assert updated.total_events_rejected == 8

    def test_acquisition_success_resets_failure_counter(self, db_session):
        org_id = uuid.uuid4()
        source = data_source_service.create_data_source(
            db_session, organization_id=org_id, payload=_make_data_source_payload()
        )
        db_session.flush()
        for _ in range(3):
            data_source_service.record_acquisition_failure(
                db_session, organization_id=org_id, data_source_id=source.id
            )
        data_source_service.record_acquisition_success(
            db_session, organization_id=org_id, data_source_id=source.id, events_count=1
        )
        db_session.flush()
        updated = data_source_service.get_data_source(
            db_session, organization_id=org_id, data_source_id=source.id
        )
        assert updated.consecutive_failures == 0

    def test_list_data_sources_tenant_isolated(self, db_session):
        """Sources created for one org are not visible from another."""
        org1 = uuid.uuid4()
        org2 = uuid.uuid4()
        for i in range(3):
            data_source_service.create_data_source(
                db_session, organization_id=org1,
                payload=_make_data_source_payload(name=f"org1-src-{i}-{uuid.uuid4().hex[:6]}")
            )
        db_session.flush()
        total, sources = data_source_service.list_data_sources(
            db_session, organization_id=org2
        )
        assert total == 0
        assert len(sources) == 0


# ===========================================================================
# B1: Data Source API — Integration Tests (with HTTP client)
# ===========================================================================


def _register_and_login(client, db_session):
    """Bootstrap an org + admin user and return (org_id, auth_headers)."""
    from tests.integration.conftest import make_platform_admin_headers

    pa_headers = make_platform_admin_headers(client, db_session)
    org_name = f"AcqTestOrg-{uuid.uuid4().hex[:8]}"
    # M20: this helper used field names the API never accepted (org_name / admin_name) and
    # expected a 200 with an "organization" object, so every test using it failed at setup
    # (422) -- the DataSource API had never actually been exercised over HTTP. The real
    # contract: organization_name / admin_full_name, 201, and a bare TokenResponse.
    reg_resp = client.post(
        "/api/v1/auth/register-organization",
        json={
            "organization_name": org_name,
            "admin_email": f"admin-{uuid.uuid4().hex[:8]}@acq-test.com",
            "admin_password": "TestPassword123!",
            "admin_full_name": "Acq Admin",
        },
        headers=pa_headers,
    )
    assert reg_resp.status_code == 201, reg_resp.text
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    org_id = client.get("/api/v1/auth/me", headers=headers).json()["organization_id"]
    return org_id, headers


@pytest.mark.integration
class TestDataSourceAPIIntegration:
    def test_create_data_source_201(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        resp = client.post(
            "/api/v1/data-sources",
            json={
                "name": "Primary MQTT",
                "connector_type": "MQTT",
                "connection_config": {"host": "broker.example.com", "port": 1883},
            },
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["connector_type"] == "MQTT"
        assert data["status"] == "DRAFT"
        assert data["total_events_ingested"] == 0
        assert "id" in data

    def test_create_data_source_invalid_type_422(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        resp = client.post(
            "/api/v1/data-sources",
            json={
                "name": "Bad Connector",
                "connector_type": "NONEXISTENT",
                "connection_config": {},
            },
            headers=headers,
        )
        assert resp.status_code == 422

    def test_create_duplicate_name_409(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        payload = {
            "name": "My Source",
            "connector_type": "CSV_BATCH",
            "connection_config": {},
        }
        r1 = client.post("/api/v1/data-sources", json=payload, headers=headers)
        assert r1.status_code == 201
        r2 = client.post("/api/v1/data-sources", json=payload, headers=headers)
        assert r2.status_code == 409

    def test_list_data_sources_empty(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        resp = client.get("/api/v1/data-sources", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_data_sources_returns_created(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        client.post(
            "/api/v1/data-sources",
            json={"name": "SrcA", "connector_type": "MAVLINK", "connection_config": {"endpoint": "udp://0.0.0.0:14550"}},
            headers=headers,
        )
        client.post(
            "/api/v1/data-sources",
            json={"name": "SrcB", "connector_type": "MQTT", "connection_config": {}},
            headers=headers,
        )
        resp = client.get("/api/v1/data-sources", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_get_data_source_by_id(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        create_resp = client.post(
            "/api/v1/data-sources",
            json={"name": "GetMe", "connector_type": "DJI_FLIGHTHUB", "connection_config": {}},
            headers=headers,
        )
        src_id = create_resp.json()["id"]
        resp = client.get(f"/api/v1/data-sources/{src_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "GetMe"

    def test_get_data_source_not_found_404(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        resp = client.get(f"/api/v1/data-sources/{uuid.uuid4()}", headers=headers)
        assert resp.status_code == 404

    def test_update_data_source_status(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        create_resp = client.post(
            "/api/v1/data-sources",
            json={"name": "UpdateMe", "connector_type": "MQTT", "connection_config": {}},
            headers=headers,
        )
        src_id = create_resp.json()["id"]
        resp = client.patch(
            f"/api/v1/data-sources/{src_id}",
            json={"status": "ACTIVE"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ACTIVE"

    def test_delete_draft_source_204(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        create_resp = client.post(
            "/api/v1/data-sources",
            json={"name": "DeleteMe", "connector_type": "CSV_BATCH", "connection_config": {}},
            headers=headers,
        )
        src_id = create_resp.json()["id"]
        del_resp = client.delete(f"/api/v1/data-sources/{src_id}", headers=headers)
        assert del_resp.status_code == 204
        get_resp = client.get(f"/api/v1/data-sources/{src_id}", headers=headers)
        assert get_resp.status_code == 404

    def test_delete_active_source_409(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        create_resp = client.post(
            "/api/v1/data-sources",
            json={"name": "ActiveSource", "connector_type": "MQTT", "connection_config": {}},
            headers=headers,
        )
        src_id = create_resp.json()["id"]
        client.patch(f"/api/v1/data-sources/{src_id}", json={"status": "ACTIVE"}, headers=headers)
        del_resp = client.delete(f"/api/v1/data-sources/{src_id}", headers=headers)
        assert del_resp.status_code == 409

    def test_unauthenticated_request_401(self, client, db_session):
        resp = client.get("/api/v1/data-sources")
        assert resp.status_code == 401

    def test_tenant_isolation_cross_org(self, client, db_session):
        """Source created by org1 is not visible to org2."""
        _, h1 = _register_and_login(client, db_session)
        _, h2 = _register_and_login(client, db_session)

        create_resp = client.post(
            "/api/v1/data-sources",
            json={"name": "OrgOneSource", "connector_type": "MQTT", "connection_config": {}},
            headers=h1,
        )
        src_id = create_resp.json()["id"]

        resp = client.get(f"/api/v1/data-sources/{src_id}", headers=h2)
        assert resp.status_code == 404

    def test_stats_overview_endpoint(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        client.post(
            "/api/v1/data-sources",
            json={"name": "StatsSource", "connector_type": "MAVLINK", "connection_config": {}},
            headers=headers,
        )
        resp = client.get("/api/v1/data-sources/stats/overview", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_sources" in data
        assert "by_health" in data
        assert "by_connector_type" in data

    def test_filter_by_connector_type(self, client, db_session):
        _, headers = _register_and_login(client, db_session)
        for ct in ["MQTT", "MQTT", "CSV_BATCH"]:
            client.post(
                "/api/v1/data-sources",
                json={"name": f"src-{uuid.uuid4().hex[:6]}", "connector_type": ct, "connection_config": {}},
                headers=headers,
            )
        resp = client.get("/api/v1/data-sources?connector_type=MQTT", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(s["connector_type"] == "MQTT" for s in data["items"])


# ===========================================================================
# B Cross-boundary: Connector Event → Telemetry Processing
# ===========================================================================


@pytest.mark.integration
class TestAcquisitionToTelemetryPipeline:
    """Verify that events produced by connectors can be handed to telemetry_service
    without schema/validation errors (the actual DB persist requires a real asset)."""

    def test_mqtt_event_schema_valid_for_telemetry_service(self):
        """MQTTConnector output satisfies NormalizedTelemetryEvent contract."""
        from app.schemas.telemetry import NormalizedTelemetryEvent

        c = MQTTConnector(connector_id="pipeline-test", source_system="KOTA_MQTT")
        c.connect("mqtt://broker:1883")
        payload = {
            "sensor_code": "ENGINE_TEMP",
            "measurement_type": "TEMPERATURE",
            "value": 92.0,
            "unit": "degC",
            "asset_id": "DRONE-PIPELINE-01",
        }
        events = c.feed_bytes(json.dumps(payload).encode(), topic="kota/test")
        assert len(events) == 1
        event = events[0]
        # Must validate as NormalizedTelemetryEvent (re-validation)
        validated = NormalizedTelemetryEvent.model_validate(event.model_dump())
        assert validated.source_asset_id == "DRONE-PIPELINE-01"

    def test_csv_event_schema_valid_for_telemetry_service(self):
        from app.schemas.telemetry import NormalizedTelemetryEvent

        c = CSVBatchConnector(connector_id="pipeline-csv")
        rows = [{"asset_id": "DRONE-CSV-01", "sensor_code": "VIB_Z", "value": "2.1", "unit": "mm/s"}]
        result = c.process_file(_make_csv_bytes(rows))
        assert result.parsed == 1
        validated = NormalizedTelemetryEvent.model_validate(result.events[0].model_dump())
        assert validated.source_asset_id == "DRONE-CSV-01"

    def test_json_event_schema_valid_for_telemetry_service(self):
        from app.schemas.telemetry import NormalizedTelemetryEvent

        c = JSONBatchConnector(connector_id="pipeline-json")
        records = [{"asset_id": "DRONE-JSON-01", "temperature": 55.0, "voltage": 22.3}]
        result = c.process_file(json.dumps(records).encode())
        assert result.parsed == 1
        validated = NormalizedTelemetryEvent.model_validate(result.events[0].model_dump())
        assert validated.source_asset_id == "DRONE-JSON-01"

    def test_nan_value_rejected_by_schema(self):
        """NaN readings must be rejected at the schema level (TelemetryReadingItem)."""
        from pydantic import ValidationError
        from app.schemas.telemetry import TelemetryReadingItem

        with pytest.raises(ValidationError):
            TelemetryReadingItem(
                sensor_code="BAD",
                sensor_type="TEST",
                measurement_type="TEST",
                value=float("nan"),
                unit="",
                data_quality="VALID",
            )

    def test_infinity_value_rejected_by_schema(self):
        from pydantic import ValidationError
        from app.schemas.telemetry import TelemetryReadingItem

        with pytest.raises(ValidationError):
            TelemetryReadingItem(
                sensor_code="INF",
                sensor_type="TEST",
                measurement_type="TEST",
                value=float("inf"),
                unit="",
                data_quality="VALID",
            )
