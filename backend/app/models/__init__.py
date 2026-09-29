from app.models.aircraft import Aircraft
from app.models.aircraft_detail import AircraftDetail
from app.models.applicability import (
    ApplicabilityCondition,
    ApplicabilityEvaluation,
    ApplicabilityRule,
    ConditionType,
    EvaluationResult,
)
from app.models.approval_request import (
    ALL_APPROVAL_REQUEST_TYPES,
    ALL_APPROVAL_STATUSES,
    ApprovalRequest,
    ApprovalRequestStatus,
    ApprovalRequestType,
)
from app.models.assessment import (
    Assessment,
    AssessmentFinding,
    AssessmentGap,
    AssessmentMetric,
    AssessmentRecommendation,
    AssessmentRisk,
    AssessmentRoadmapItem,
    AssessmentSnapshot,
)
from app.models.asset import Asset, AssetType
from app.models.asset_baseline import AssetHistoricalBaseline
from app.models.audit_event import AuditEvent
from app.models.auth_verification import AuthVerificationCode, VerificationPurpose
from app.models.battery import Battery, BatteryStatus
from app.models.compliance import (
    ComplianceAssessment,
    ComplianceAssessmentStatus,
    ComplianceObligation,
    ComplianceState,
    RegulatoryRequirement,
)
from app.models.component import Component, ComponentStatus, ComponentType
from app.models.evidence import Evidence, EvidenceFile, EvidenceFileStatus, EvidenceStatus
from app.models.facility import Facility, FacilityStatus, FacilityType
from app.models.finding import (
    ALL_DISPOSITION_TYPES,
    ALL_FINDING_SEVERITIES,
    ALL_FINDING_STATUSES,
    DispositionType,
    Finding,
    FindingDisposition,
    FindingSeverity,
    FindingStatus,
)
from app.models.flight import Flight
from app.models.hums import (
    HUMSBaseline,
    HUMSDegradationModel,
    HUMSDiagnosticCandidate,
    HUMSExceedance,
    HUMSFeature,
    HUMSPrognosticRecord,
    HUMSSensor,
    HUMSSensorReading,
)
from app.models.import_job import ImportDomain, ImportJob, ImportJobStatus
from app.models.import_mapping import TenantImportMapping
from app.models.inspection_requirement import InspectionRequirement
from app.models.installation_history import BatteryInstallation, ComponentInstallation
from app.models.lisa_conversation_context import LisaConversationContext
from app.models.mro_intelligence import (
    ALLOWED_CANDIDATE_TRANSITIONS,
    MaintenanceIntelligenceCandidate,
    MROCandidatePriority,
    MROCandidateStatus,
    MROCandidateType,
)
from app.models.organization import (
    OnboardingStage,
    Organization,
    OrganizationIndustry,
    OrganizationStatus,
    TenantRetentionPolicy,
)
from app.models.part import Part
from app.models.plan import Plan, PlanFeature, PlanLimit
from app.models.proactive_signal import ProactiveSignalRecord
from app.models.product_catalog import ProductFeature, ProductModule, ProductPage, ProductSuite
from app.models.sso import (
    ExternalIdentityMapping,
    IncidentSeverity,
    IncidentStatus,
    OperationalIncident,
    SSOConfiguration,
    SSOProviderType,
)
from app.models.subscription import Subscription, SubscriptionStatus
from app.models.task import Task
from app.models.technician_qualification import TechnicianQualification
from app.models.data_source import DataSource, DataSourceConnectorType, DataSourceStatus
from app.models.telemetry import (
    EdgeDevice,
    ExternalAssetMapping,
    TelemetryEventLog,
    TelemetryFreshnessPolicy,
    TelemetryProcessingStatus,
)
from app.models.tenant_entitlement import TenantFeatureOverride, TenantUsageLimit
from app.models.user import User, UserRole
from app.models.vendor import Vendor
from app.models.warehouse import Location, Warehouse
from app.models.work_order import WorkOrder

# Register every remaining model module so Base.metadata is complete for Alembic
# autogenerate / create_all (these were previously only imported indirectly via services).
from app.models import aog_event as _aog_event  # noqa: F401
from app.models import billing as _billing  # noqa: F401
from app.models import deferred_item as _deferred_item  # noqa: F401
from app.models import inventory_transaction as _inventory_transaction  # noqa: F401
from app.models import maintenance_requirement as _maintenance_requirement  # noqa: F401
from app.models import mission as _mission  # noqa: F401
from app.models import part_requirement as _part_requirement  # noqa: F401
from app.models import procurement_request as _procurement_request  # noqa: F401
from app.models import purchase_order as _purchase_order  # noqa: F401
from app.models import regulatory_document as _regulatory_document  # noqa: F401
from app.models import vendor_part_availability as _vendor_part_availability  # noqa: F401

__all__ = [
    "Organization",
    "OrganizationStatus",
    "OrganizationIndustry",
    "OnboardingStage",
    "TenantRetentionPolicy",
    "EdgeDevice",
    "User",
    "UserRole",
    "AuditEvent",
    "Battery",
    "Mission",
    "MissionStatus",
    "BatteryStatus",
    "Component",
    "ComponentStatus",
    "ComponentType",
    "Flight",
    "BatteryInstallation",
    "ComponentInstallation",
    "AuthVerificationCode",
    "VerificationPurpose",
    "Aircraft",
    "AircraftDetail",
    "Asset",
    "AssetType",
    "WorkOrder",
    "Task",
    "Evidence",
    "EvidenceStatus",
    "EvidenceFile",
    "Facility",
    "FacilityStatus",
    "FacilityType",
    "EvidenceFileStatus",
    "InspectionRequirement",
    "Part",
    "Vendor",
    "TechnicianQualification",
    "LisaConversationContext",
    "Assessment",
    "AssessmentSnapshot",
    "AssessmentFinding",
    "AssessmentRisk",
    "AssessmentGap",
    "AssessmentRecommendation",
    "AssessmentRoadmapItem",
    "AssessmentMetric",
    "ImportJob",
    "ImportDomain",
    "ImportJobStatus",
    "Plan",
    "ProductSuite",
    "ProductModule",
    "ProductPage",
    "ProductFeature",
    "PlanFeature",
    "PlanLimit",
    "Subscription",
    "SubscriptionStatus",
    "TenantFeatureOverride",
    "TenantUsageLimit",
    "Warehouse",
    "Location",
    "ApprovalRequest",
    "ApprovalRequestStatus",
    "ApprovalRequestType",
    "ALL_APPROVAL_STATUSES",
    "ALL_APPROVAL_REQUEST_TYPES",
    "Finding",
    "FindingDisposition",
    "FindingSeverity",
    "FindingStatus",
    "DispositionType",
    "ALL_FINDING_SEVERITIES",
    "ALL_FINDING_STATUSES",
    "ALL_DISPOSITION_TYPES",
    "ApplicabilityRule",
    "ApplicabilityCondition",
    "ApplicabilityEvaluation",
    "ConditionType",
    "EvaluationResult",
    "ComplianceObligation",
    "ComplianceState",
    "ComplianceAssessment",
    "ComplianceAssessmentStatus",
    "RegulatoryRequirement",
    "AssetHistoricalBaseline",
    "TenantImportMapping",
    "ProactiveSignalRecord",
    "HUMSSensor",
    "HUMSSensorReading",
    "HUMSExceedance",
    "HUMSFeature",
    "HUMSBaseline",
    "HUMSDiagnosticCandidate",
    "HUMSDegradationModel",
    "HUMSPrognosticRecord",
    "DataSource",
    "DataSourceConnectorType",
    "DataSourceStatus",
    "ExternalAssetMapping",
    "TelemetryEventLog",
    "TelemetryFreshnessPolicy",
    "TelemetryProcessingStatus",
    "SSOConfiguration",
    "SSOProviderType",
    "ExternalIdentityMapping",
    "OperationalIncident",
    "IncidentSeverity",
    "IncidentStatus",
    "MaintenanceIntelligenceCandidate",
    "MROCandidateType",
    "MROCandidateStatus",
    "MROCandidatePriority",
    "ALLOWED_CANDIDATE_TRANSITIONS",
]

