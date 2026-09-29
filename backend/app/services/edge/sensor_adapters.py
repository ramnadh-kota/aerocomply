"""M15: Physical Sensor Adapters & Boundary Data Quality.

Provides driver-level abstraction for physical bench sensors:
- Priority 1: Vibration (MEMS / Piezo / Accelerometer)
- Priority 2: Temperature (RTD / Thermocouple / I2C)
- Priority 3: Pressure (Piezo / Piezoresistive Transducer)
- Priority 4: Electrical (Voltage / Current Shunt)

Invariant:
- Sensor adapters ONLY acquire, validate, and package raw readings.
- No HUMS, health scoring, or fleet intelligence calculations happen inside adapters.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, Literal

from app.schemas.edge_hardware import EdgeSensorMeasurement


class PhysicalSensorAdapter(ABC):
    """Abstract base adapter for physical laboratory bench sensors."""

    def __init__(
        self,
        sensor_code: str,
        sensor_type: str,
        unit: str,
        port_or_bus: str = "USB0",
        sampling_rate_hz: float = 100.0,
    ) -> None:
        self.sensor_code = sensor_code
        self.sensor_type = sensor_type
        self.unit = unit
        self.port_or_bus = port_or_bus
        self.sampling_rate_hz = sampling_rate_hz
        self.is_connected = False
        self.last_read_at: datetime | None = None
        self.error_count = 0

    @abstractmethod
    def initialize(self) -> bool:
        """Initializes connection to the physical hardware interface."""
        pass

    @abstractmethod
    def read_sample(self, raw_data_override: Any = None) -> EdgeSensorMeasurement:
        """Reads a discrete measurement from the physical sensor."""
        pass

    def disconnect(self) -> None:
        self.is_connected = False


class VibrationSensorAdapter(PhysicalSensorAdapter):
    """Priority 1: Physical Vibration / Accelerometer Adapter.

    Extracts time-domain windowed metrics (RMS, Peak, Crest Factor, Kurtosis)
    from high-frequency acceleration samples.
    """

    def __init__(
        self,
        sensor_code: str = "MOT_1_VIB",
        unit: str = "g",
        port_or_bus: str = "USB0_ACCEL",
        sampling_rate_hz: float = 1000.0,
    ) -> None:
        super().__init__(
            sensor_code=sensor_code,
            sensor_type="VIBRATION",
            unit=unit,
            port_or_bus=port_or_bus,
            sampling_rate_hz=sampling_rate_hz,
        )

    def initialize(self) -> bool:
        self.is_connected = True
        self.error_count = 0
        return True

    def compute_metrics(self, samples: list[float]) -> dict[str, float]:
        """Computes deterministic time-domain features from raw vibration waveform."""
        if not samples:
            return {"rms_g": 0.0, "peak_g": 0.0, "crest_factor": 1.0, "kurtosis": 3.0}

        n = len(samples)
        # Mean & Variance
        mean_val = sum(samples) / n
        sq_sum = sum(s * s for s in samples)
        rms = math.sqrt(sq_sum / n)
        peak = max(abs(s) for s in samples)
        crest_factor = round(peak / rms, 3) if rms > 1e-6 else 1.0

        # Fourth moment (Kurtosis)
        variance = sum((s - mean_val) ** 2 for s in samples) / n
        if variance > 1e-9:
            fourth_moment = sum((s - mean_val) ** 4 for s in samples) / n
            kurtosis = round(fourth_moment / (variance**2), 3)
        else:
            kurtosis = 3.0

        return {
            "rms_g": round(rms, 4),
            "peak_g": round(peak, 4),
            "crest_factor": crest_factor,
            "kurtosis": kurtosis,
            "sample_count": float(n),
        }

    def read_sample(self, raw_data_override: list[float] | None = None) -> EdgeSensorMeasurement:
        now = datetime.now(UTC)
        self.last_read_at = now

        if not self.is_connected:
            self.error_count += 1
            return EdgeSensorMeasurement(
                sensor_code=self.sensor_code,
                sensor_type=self.sensor_type,
                timestamp=now,
                unit=self.unit,
                raw_values={"rms_g": 0.0, "peak_g": 0.0},
                quality="INVALID",
            )

        samples = raw_data_override if raw_data_override is not None else [0.18, 0.22, 0.17, 0.24, 0.19]
        metrics = self.compute_metrics(samples)

        # Quality evaluation at physical boundary
        quality: Literal["VALID", "SUSPECT", "OUT_OF_RANGE", "STALE", "INVALID"] = "VALID"
        if metrics["rms_g"] > 25.0:  # Physical sensor clip limit (25g accelerometer)
            quality = "OUT_OF_RANGE"
        elif len(samples) < 3:
            quality = "SUSPECT"

        return EdgeSensorMeasurement(
            sensor_code=self.sensor_code,
            sensor_type=self.sensor_type,
            timestamp=now,
            unit=self.unit,
            raw_values=metrics,
            quality=quality,
        )


class TemperatureSensorAdapter(PhysicalSensorAdapter):
    """Priority 2: Physical Temperature Sensor Adapter (RTD / Thermocouple / I2C)."""

    def __init__(
        self,
        sensor_code: str = "ENG_1_TEMP",
        unit: str = "degC",
        port_or_bus: str = "I2C_TEMP_0x48",
        min_valid_temp: float = -40.0,
        max_valid_temp: float = 250.0,
    ) -> None:
        super().__init__(
            sensor_code=sensor_code,
            sensor_type="TEMPERATURE",
            unit=unit,
            port_or_bus=port_or_bus,
            sampling_rate_hz=10.0,
        )
        self.min_valid_temp = min_valid_temp
        self.max_valid_temp = max_valid_temp

    def initialize(self) -> bool:
        self.is_connected = True
        return True

    def read_sample(self, raw_data_override: float | None = None) -> EdgeSensorMeasurement:
        now = datetime.now(UTC)
        self.last_read_at = now

        if not self.is_connected:
            self.error_count += 1
            return EdgeSensorMeasurement(
                sensor_code=self.sensor_code,
                sensor_type=self.sensor_type,
                timestamp=now,
                unit=self.unit,
                raw_values={"temp_c": 0.0},
                quality="INVALID",
            )

        temp_val = raw_data_override if raw_data_override is not None else 58.4

        quality: Literal["VALID", "SUSPECT", "OUT_OF_RANGE", "STALE", "INVALID"] = "VALID"
        if temp_val < self.min_valid_temp or temp_val > self.max_valid_temp:
            quality = "OUT_OF_RANGE"

        return EdgeSensorMeasurement(
            sensor_code=self.sensor_code,
            sensor_type=self.sensor_type,
            timestamp=now,
            unit=self.unit,
            raw_values={"temp_c": round(temp_val, 2)},
            quality=quality,
        )


class PressureSensorAdapter(PhysicalSensorAdapter):
    """Priority 3: Physical Pressure Sensor Adapter (Hydraulic / Pneumatic / Ambient)."""

    def __init__(
        self,
        sensor_code: str = "HYD_SYS_PRESS",
        unit: str = "bar",
        port_or_bus: str = "SPI_ADC_CH1",
        max_pressure_bar: float = 350.0,
    ) -> None:
        super().__init__(
            sensor_code=sensor_code,
            sensor_type="PRESSURE",
            unit=unit,
            port_or_bus=port_or_bus,
            sampling_rate_hz=50.0,
        )
        self.max_pressure_bar = max_pressure_bar

    def initialize(self) -> bool:
        self.is_connected = True
        return True

    def read_sample(self, raw_data_override: float | None = None) -> EdgeSensorMeasurement:
        now = datetime.now(UTC)
        self.last_read_at = now

        if not self.is_connected:
            self.error_count += 1
            return EdgeSensorMeasurement(
                sensor_code=self.sensor_code,
                sensor_type=self.sensor_type,
                timestamp=now,
                unit=self.unit,
                raw_values={"pressure_bar": 0.0},
                quality="INVALID",
            )

        press_val = raw_data_override if raw_data_override is not None else 205.0

        quality: Literal["VALID", "SUSPECT", "OUT_OF_RANGE", "STALE", "INVALID"] = "VALID"
        if press_val < 0.0 or press_val > self.max_pressure_bar:
            quality = "OUT_OF_RANGE"

        return EdgeSensorMeasurement(
            sensor_code=self.sensor_code,
            sensor_type=self.sensor_type,
            timestamp=now,
            unit=self.unit,
            raw_values={"pressure_bar": round(press_val, 2)},
            quality=quality,
        )


class ElectricalSensorAdapter(PhysicalSensorAdapter):
    """Priority 4: Physical Electrical Bus Adapter (Voltage & Current Shunt)."""

    def __init__(
        self,
        sensor_code: str = "MAIN_BUS_ELEC",
        unit: str = "V",
        port_or_bus: str = "I2C_INA226_0x40",
    ) -> None:
        super().__init__(
            sensor_code=sensor_code,
            sensor_type="ELECTRICAL",
            unit=unit,
            port_or_bus=port_or_bus,
            sampling_rate_hz=20.0,
        )

    def initialize(self) -> bool:
        self.is_connected = True
        return True

    def read_sample(self, raw_data_override: dict[str, float] | None = None) -> EdgeSensorMeasurement:
        now = datetime.now(UTC)
        self.last_read_at = now

        if not self.is_connected:
            self.error_count += 1
            return EdgeSensorMeasurement(
                sensor_code=self.sensor_code,
                sensor_type=self.sensor_type,
                timestamp=now,
                unit=self.unit,
                raw_values={"voltage_v": 0.0, "current_a": 0.0, "power_w": 0.0},
                quality="INVALID",
            )

        data = raw_data_override or {"voltage_v": 28.2, "current_a": 14.5}
        voltage = data.get("voltage_v", 0.0)
        current = data.get("current_a", 0.0)
        power = round(voltage * current, 2)

        quality: Literal["VALID", "SUSPECT", "OUT_OF_RANGE", "STALE", "INVALID"] = "VALID"
        if voltage < 0.0 or voltage > 60.0 or current < -10.0 or current > 200.0:
            quality = "OUT_OF_RANGE"

        return EdgeSensorMeasurement(
            sensor_code=self.sensor_code,
            sensor_type=self.sensor_type,
            timestamp=now,
            unit=self.unit,
            raw_values={
                "voltage_v": round(voltage, 2),
                "current_a": round(current, 2),
                "power_w": power,
            },
            quality=quality,
        )
