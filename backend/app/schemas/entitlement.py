"""Response schemas for the M3 entitlement API layer.

These are pure serialization shapes over
``app.services.entitlement_service.EntitlementResolution`` /
``UsageLimitConfiguration`` (both frozen dataclasses, not ORM models) --
no entitlement logic lives here, only field-by-field mapping.
"""
import uuid

from pydantic import BaseModel

from app.services.entitlement_service import EntitlementResolution, UsageLimitConfiguration


class UsageLimitConfigurationResponse(BaseModel):
    """Configuration only -- no consumption/usage counter exists anywhere in
    this codebase yet (see entitlement_service module docstring), so this
    intentionally carries no "remaining"/"used" field.
    """

    feature_key: str
    limit_key: str
    limit_value: int | None
    is_unlimited: bool

    @classmethod
    def from_configuration(
        cls, limit: UsageLimitConfiguration
    ) -> "UsageLimitConfigurationResponse":
        return cls(
            feature_key=limit.feature_key,
            limit_key=limit.limit_key,
            limit_value=limit.limit_value,
            is_unlimited=limit.is_unlimited,
        )


class EntitlementResolutionResponse(BaseModel):
    organization_id: uuid.UUID
    resolution_status: str
    organization_status: str
    subscription_id: uuid.UUID | None
    subscription_status: str | None
    suite_id: uuid.UUID | None = None
    suite_code: str | None = None
    suite_name: str | None = None
    plan_id: uuid.UUID | None
    plan_code: str | None
    plan_name: str | None = None
    modules: list[str] = []
    pages: list[str] = []
    effective_features: dict[str, bool]
    usage_limits: list[UsageLimitConfigurationResponse]
    active_suites: list[dict] = []
    reason: str

    @classmethod
    def from_resolution(
        cls, result: EntitlementResolution, *, plan_name: str | None = None
    ) -> "EntitlementResolutionResponse":
        return cls(
            organization_id=result.organization_id,
            resolution_status=str(result.resolution_status),
            organization_status=result.organization_status,
            subscription_id=result.subscription_id,
            subscription_status=result.subscription_status,
            suite_id=getattr(result, "suite_id", None),
            suite_code=getattr(result, "suite_code", None),
            suite_name=getattr(result, "suite_name", None),
            plan_id=result.plan_id,
            plan_code=result.plan_code,
            plan_name=plan_name or getattr(result, "plan_name", None),
            modules=getattr(result, "modules", []),
            pages=getattr(result, "pages", []),
            effective_features=result.effective_features,
            usage_limits=[
                UsageLimitConfigurationResponse.from_configuration(limit)
                for limit in result.usage_limits
            ],
            active_suites=getattr(result, "active_suites", []),
            reason=result.reason,
        )
