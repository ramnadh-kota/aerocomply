"""M15/M16/M18 Physical Edge & UAV Data Acquisition Module."""

from app.services.edge.acquisition_engine import PhysicalEdgeAcquisitionEngine
from app.services.edge.connector_base import (
    ConnectorState,
    ConnectorStats,
    TelemetryConnector,
)
from app.services.edge.gateway_service import (
    GatewayMetrics,
    KotaTelemetryGateway,
)
from app.services.edge.mavlink_connector import (
    MAVLinkConnector,
    MAVLinkVehicleState,
)
from app.services.edge.sensor_adapters import (
    ElectricalSensorAdapter,
    PhysicalSensorAdapter,
    PressureSensorAdapter,
    TemperatureSensorAdapter,
    VibrationSensorAdapter,
)

__all__ = [
    "PhysicalEdgeAcquisitionEngine",
    "PhysicalSensorAdapter",
    "VibrationSensorAdapter",
    "TemperatureSensorAdapter",
    "PressureSensorAdapter",
    "ElectricalSensorAdapter",
    "TelemetryConnector",
    "ConnectorState",
    "ConnectorStats",
    "MAVLinkConnector",
    "MAVLinkVehicleState",
    "KotaTelemetryGateway",
    "GatewayMetrics",
]
