"""B3: Batch Data Acquisition Connectors — CSV and JSON file-based ingestion.

Architecture Invariants:
- Batch connectors are stateless per-file processors; they do NOT maintain persistent
  connections (unlike MAVLink/MQTT streaming connectors).
- Each call to process_file() returns a list of NormalizedTelemetryEvent objects.
- Parsing errors on individual rows are counted and logged; they do not abort the batch.
- Tenant context (organization_id) is validated before any persistence occurs.
- Maximum row limits prevent memory exhaustion from malformed/adversarial input files.

Supported CSV Columns (flexible — columns are matched case-insensitively):
  Required: asset_id OR device_sn OR serial_number
  Required: value OR measurement_value
  Required: sensor_code OR measurement_type
  Optional: unit, timestamp, event_type, data_quality, sensor_type, component_id

Supported JSON Formats:
  A. Array of objects: [{...}, {...}]
  B. Wrapped array: {"events": [...]} or {"data": [...]} or {"records": [...]}
  C. Single object: {...}  (treated as a single-event batch)
  D. NDJSON (one JSON object per line): {"key": val}\n{"key": val}
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog

from app.schemas.telemetry import (
    NormalizedTelemetryEvent,
    TelemetryReadingItem,
)

log = structlog.get_logger(__name__)

# Safety limits
MAX_ROWS = 10_000


def content_event_id(prefix: str, *parts: Any) -> str:
    """Deterministic event id derived from the record's CONTENT.

    Re-uploading the same file yields the same ids (idempotent), while two different
    records can never collide -- the old `<connector>-R<row>-<timestamp>` id made row 2 of
    two different vehicles' files with the same start time the SAME event, so the second
    vehicle's data was silently discarded as a "duplicate"."""
    import hashlib

    digest = hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class BatchIngestResult:
    """Summary result of a batch file ingestion attempt."""

    def __init__(self) -> None:
        self.total_rows: int = 0
        self.parsed: int = 0
        self.errors: int = 0
        self.events: list[NormalizedTelemetryEvent] = []
        self.error_samples: list[str] = []  # first 10 parse errors


class CSVBatchConnector:
    """Processes CSV files and converts rows into NormalizedTelemetryEvent objects.

    Usage:
        connector = CSVBatchConnector(source_system="CSV_BATCH", connector_id="...")
        with open("telemetry.csv", "rb") as f:
            result = connector.process_file(f.read())
        for event in result.events:
            telemetry_service.process_normalized_event(db, org_id, event, ...)
    """

    # Canonical column aliases in PRIORITY ORDER (first present wins). These were Python sets,
    # whose iteration order differs between processes (hash randomisation): a row carrying both
    # `asset_id` and `device_sn` could be attributed to a different asset on each run.
    _ASSET_COLS = ("asset_id", "serial_number", "device_sn", "sn")
    _VALUE_COLS = ("value", "measurement_value", "reading_value", "val")
    _CODE_COLS = ("sensor_code", "measurement_type", "parameter", "metric")
    _UNIT_COLS = ("unit", "uom", "units")
    _TS_COLS = ("timestamp", "event_timestamp", "recorded_at", "datetime", "time")
    _EVENT_TYPE_COLS = ("event_type", "event")
    _QUALITY_COLS = ("data_quality", "quality", "status")
    _SENSOR_TYPE_COLS = ("sensor_type", "type")

    def __init__(
        self,
        connector_id: str,
        source_system: str = "CSV_BATCH",
        max_rows: int = MAX_ROWS,
    ) -> None:
        self.connector_id = connector_id
        self.source_system = source_system
        self.max_rows = max_rows

    def process_file(self, raw_bytes: bytes) -> BatchIngestResult:
        """Parses a CSV file and returns normalized events.

        Raises:
            ValueError: If the file exceeds the maximum allowed size.
        """
        result = BatchIngestResult()

        if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"CSV file exceeds maximum allowed size ({MAX_FILE_SIZE_BYTES // (1024*1024)} MB)"
            )

        try:
            text = raw_bytes.decode("utf-8-sig")  # handles BOM from Excel exports
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1")

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            log.warning("csv_batch.empty_file", connector_id=self.connector_id)
            return result

        # Build case-insensitive column mapping
        col_map = {name.strip().lower(): name for name in (reader.fieldnames or [])}

        for row_num, raw_row in enumerate(reader, start=2):  # row 1 = header
            if row_num > self.max_rows + 1:
                log.warning(
                    "csv_batch.row_limit_reached",
                    connector_id=self.connector_id,
                    limit=self.max_rows,
                )
                break

            result.total_rows += 1
            # Normalize keys to lowercase for matching
            row = {k.strip().lower(): v.strip() if isinstance(v, str) else v for k, v in raw_row.items()}

            try:
                event = self._parse_row(row, col_map, row_num)
                if event:
                    result.events.append(event)
                    result.parsed += 1
                else:
                    result.errors += 1
            except Exception as exc:
                result.errors += 1
                if len(result.error_samples) < 10:
                    result.error_samples.append(f"Row {row_num}: {exc}")
                log.debug("csv_batch.row_parse_error", row_num=row_num, error=str(exc))

        log.info(
            "csv_batch.processed",
            connector_id=self.connector_id,
            total_rows=result.total_rows,
            parsed=result.parsed,
            errors=result.errors,
        )
        return result

    def _parse_row(
        self, row: dict[str, Any], col_map: dict[str, str], row_num: int
    ) -> NormalizedTelemetryEvent | None:
        """Parses a single CSV row into a NormalizedTelemetryEvent."""
        # Resolve asset ID
        asset_id = self._first_match(row, self._ASSET_COLS) or "UNKNOWN"
        if not asset_id or asset_id == "UNKNOWN":
            raise ValueError("Missing asset identifier (asset_id/device_sn/serial_number)")

        # Resolve value
        raw_value = self._first_match(row, self._VALUE_COLS)
        if raw_value is None:
            raise ValueError("Missing measurement value")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"Non-numeric value: {raw_value!r}")

        # Resolve sensor code / measurement type
        sensor_code = self._first_match(row, self._CODE_COLS) or "UNKNOWN_READING"
        unit = self._first_match(row, self._UNIT_COLS) or ""
        event_type = self._first_match(row, self._EVENT_TYPE_COLS) or "TELEMETRY_PING"
        data_quality = self._first_match(row, self._QUALITY_COLS) or "VALID"
        sensor_type = self._first_match(row, self._SENSOR_TYPE_COLS) or "TELEMETRY"

        # Resolve timestamp
        raw_ts = self._first_match(row, self._TS_COLS)
        event_ts = self._parse_timestamp(raw_ts)

        reading = TelemetryReadingItem(
            sensor_code=sensor_code[:64],
            sensor_type=sensor_type[:64],
            measurement_type=sensor_code[:64],
            value=value,
            unit=unit[:32],
            data_quality=data_quality[:32],
        )

        return NormalizedTelemetryEvent(
            source_system=self.source_system,
            source_event_id=content_event_id(
                "CSV", self.source_system, self.connector_id, asset_id, sensor_code, event_type,
                int(event_ts.timestamp() * 1000), value, unit,
            ),
            source_asset_id=asset_id[:128],
            event_type=event_type[:64],
            event_timestamp=event_ts,
            readings=[reading],
            raw_metadata={
                "source": "csv_batch",
                "row": row_num,
                "timestamp_source": "SOURCE" if raw_ts else "RECEIVED",
            },
        )

    @staticmethod
    def _first_match(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
        """Returns the first non-empty value from the row that matches any candidate column."""
        for key in candidates:
            val = row.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return None

    @staticmethod
    def _parse_timestamp(raw: str | None) -> datetime:
        """Parses a timestamp into a timezone-aware datetime.

        No timestamp at all => the received time (the event is flagged
        timestamp_source=RECEIVED). A timestamp that IS present but cannot be parsed raises:
        silently replacing it with "now" would file historical data under the import time.
        Zone-less values are taken as UTC (documented assumption)."""
        if not raw:
            return datetime.now(UTC)
        raw = raw.strip()
        try:
            dt_iso = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt_iso if dt_iso.tzinfo else dt_iso.replace(tzinfo=UTC)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return dt
            except ValueError:
                continue
        # Epoch milliseconds or seconds
        try:
            ts_float = float(raw)
            ts = ts_float / 1000.0 if ts_float > 1e10 else ts_float
            return datetime.fromtimestamp(ts, tz=UTC)
        except (TypeError, ValueError, OverflowError, OSError):
            pass
        raise ValueError(f"Unparseable timestamp: {raw!r}")


class JSONBatchConnector:
    """Processes JSON files and converts records into NormalizedTelemetryEvent objects.

    Supports four JSON layouts:
      A. Array: [{...}, {...}]
      B. Wrapped: {"events": [...]} / {"data": [...]} / {"records": [...]}
      C. Single object: {...}
      D. NDJSON: one JSON object per line

    Usage:
        connector = JSONBatchConnector(source_system="JSON_BATCH", connector_id="...")
        with open("telemetry.json", "rb") as f:
            result = connector.process_file(f.read())
    """

    _WRAPPER_KEYS = ("events", "data", "records", "items", "telemetry", "readings")

    def __init__(
        self,
        connector_id: str,
        source_system: str = "JSON_BATCH",
        max_records: int = MAX_ROWS,
    ) -> None:
        self.connector_id = connector_id
        self.source_system = source_system
        self.max_records = max_records

    def process_file(self, raw_bytes: bytes) -> BatchIngestResult:
        """Parses a JSON file and returns normalized events."""
        result = BatchIngestResult()

        if len(raw_bytes) > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"JSON file exceeds maximum allowed size ({MAX_FILE_SIZE_BYTES // (1024*1024)} MB)"
            )

        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = raw_bytes.decode("latin-1")

        records: list[dict[str, Any]] = self._extract_records(text)
        records = records[: self.max_records]

        for idx, record in enumerate(records):
            result.total_rows += 1
            try:
                event = self._decode_record(record, idx)
                if event:
                    result.events.append(event)
                    result.parsed += 1
                else:
                    result.errors += 1
            except Exception as exc:
                result.errors += 1
                if len(result.error_samples) < 10:
                    result.error_samples.append(f"Record {idx}: {exc}")
                log.debug("json_batch.record_parse_error", record_idx=idx, error=str(exc))

        log.info(
            "json_batch.processed",
            connector_id=self.connector_id,
            total_records=result.total_rows,
            parsed=result.parsed,
            errors=result.errors,
        )
        return result

    def _extract_records(self, text: str) -> list[dict[str, Any]]:
        """Detects JSON layout and extracts a list of record dicts."""
        text = text.strip()

        # Try standard JSON first
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [r for r in parsed if isinstance(r, dict)]
            if isinstance(parsed, dict):
                # Check for wrapper keys
                for key in self._WRAPPER_KEYS:
                    if key in parsed and isinstance(parsed[key], list):
                        return [r for r in parsed[key] if isinstance(r, dict)]
                # Single object
                return [parsed]
        except json.JSONDecodeError:
            pass

        # Try NDJSON
        records: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    records.append(obj)
            except json.JSONDecodeError:
                continue
        return records

    def _decode_record(
        self, record: dict[str, Any], idx: int
    ) -> NormalizedTelemetryEvent | None:
        """Decodes a JSON record dict into a NormalizedTelemetryEvent."""
        # --- Try canonical format first ---
        if "source_system" in record and "source_event_id" in record and "source_asset_id" in record:
            return self._decode_canonical(record)

        # --- Minimal format: must have at least asset + readings or readings list ---
        asset_id = (
            str(record.get("asset_id") or record.get("device_sn") or record.get("serial_number") or "")
            .strip()[:128]
        )
        if not asset_id:
            raise ValueError("Missing asset identifier")

        event_type = str(record.get("event_type") or "TELEMETRY_PING")[:64]

        # Parse event timestamp
        raw_ts = record.get("timestamp") or record.get("event_timestamp") or record.get("time")
        event_ts = CSVBatchConnector._parse_timestamp(str(raw_ts) if raw_ts is not None else None)

        # Build readings
        readings: list[TelemetryReadingItem] = []
        if "readings" in record and isinstance(record["readings"], list):
            for r in record["readings"]:
                try:
                    readings.append(TelemetryReadingItem(**r))
                except Exception:
                    continue
        else:
            # Scan for numeric fields
            skip_keys = {
                "asset_id", "device_sn", "serial_number", "timestamp",
                "event_timestamp", "event_type", "source_system", "time",
            }
            for key, val in record.items():
                if key in skip_keys or isinstance(val, bool):  # a flag is not a measurement
                    continue
                try:
                    fval = float(val)
                    if not (-1e12 < fval < 1e12):
                        continue
                    readings.append(
                        TelemetryReadingItem(
                            sensor_code=key.upper()[:64],
                            sensor_type="JSON_BATCH",
                            measurement_type=key.upper()[:64],
                            value=fval,
                            unit="",
                            data_quality="VALID",
                        )
                    )
                except (TypeError, ValueError):
                    continue

        return NormalizedTelemetryEvent(
            source_system=self.source_system,
            source_event_id=content_event_id(
                "JSON", self.source_system, self.connector_id, asset_id, event_type,
                int(event_ts.timestamp() * 1000),
                sorted((r.sensor_code, r.value, r.unit) for r in readings),
            ),
            source_asset_id=asset_id,
            event_type=event_type,
            event_timestamp=event_ts,
            readings=readings,
            raw_metadata={
                "source": "json_batch",
                "record_index": idx,
                "timestamp_source": "SOURCE" if raw_ts is not None else "RECEIVED",
            },
        )

    def _decode_canonical(self, record: dict[str, Any]) -> NormalizedTelemetryEvent | None:
        """Constructs a NormalizedTelemetryEvent directly from a canonical record dict."""
        try:
            if isinstance(record.get("event_timestamp"), str):
                record["event_timestamp"] = datetime.fromisoformat(
                    record["event_timestamp"].replace("Z", "+00:00")
                )
            return NormalizedTelemetryEvent(**record)
        except Exception as exc:
            log.warning("json_batch.canonical_decode_error", error=str(exc))
            return None
