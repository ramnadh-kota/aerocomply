import uuid
from unittest.mock import MagicMock
import pytest
from fastapi import HTTPException

from app.core.feature_keys import (
    FeatureKey,
    canonicalize_feature_key,
    get_feature_lookup_aliases,
)
from app.core.deps import require_feature
from app.schemas.auth import CurrentUser
from app.services import entitlement_service


def test_canonical_feature_key_normalization():
    # Canonical string matching
    assert canonicalize_feature_key("DIGITAL_TWIN") == FeatureKey.DIGITAL_TWIN.value
    assert canonicalize_feature_key("digital_twin") == FeatureKey.DIGITAL_TWIN.value
    assert canonicalize_feature_key("DIGITAL_TWIN_BETA") == FeatureKey.DIGITAL_TWIN.value
    assert canonicalize_feature_key("digital_twin_beta") == FeatureKey.DIGITAL_TWIN.value

    assert canonicalize_feature_key("HUMS") == FeatureKey.HUMS.value
    assert canonicalize_feature_key("hums_module") == FeatureKey.HUMS.value
    assert canonicalize_feature_key("HUMS_AI") == FeatureKey.HUMS.value

    assert canonicalize_feature_key("LISA") == FeatureKey.LISA_AI_COPILOT.value
    assert canonicalize_feature_key("lisa_ai_copilot") == FeatureKey.LISA_AI_COPILOT.value

    assert canonicalize_feature_key("MRO_INTELLIGENCE") == FeatureKey.MRO_INTELLIGENCE.value
    assert canonicalize_feature_key("mro_intelligence_module") == FeatureKey.MRO_INTELLIGENCE.value


def test_get_all_feature_key_variants():
    variants = get_feature_lookup_aliases("digital_twin")
    assert "digital_twin" in variants
    assert "DIGITAL_TWIN" in variants
    assert "DIGITAL_TWIN_BETA" in variants
    assert "digital_twin_beta" in variants


from app.services.entitlement_service import EntitlementResolutionStatus, EntitlementResolution
from app.core.errors import ForbiddenError


def test_require_feature_dependency():
    user = CurrentUser(
        id=uuid.uuid4(),
        email="test@example.com",
        full_name="Test User",
        roles=["ENGINEER"],
        organization_id=uuid.uuid4(),
        organization_name="Acme Aero",
    )

    resolved = EntitlementResolution(
        organization_id=user.organization_id,
        resolution_status=EntitlementResolutionStatus.ACTIVE,
        organization_status="ACTIVE",
        subscription_id=uuid.uuid4(),
        subscription_status="ACTIVE",
        plan_id=uuid.uuid4(),
        plan_code="ENTERPRISE",
        effective_features={
            "digital_twin": True,
            "DIGITAL_TWIN_BETA": True,
            "hums": False,
        },
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.core.deps.resolve_entitlements",
            lambda db, organization_id: resolved,
        )

        db = MagicMock()

        # Allowed feature
        check_dt = require_feature("digital_twin")
        res = check_dt(current_user=user, db=db)
        assert res == user

        # Allowed via alias check
        check_dt_beta = require_feature("DIGITAL_TWIN_BETA")
        res_beta = check_dt_beta(current_user=user, db=db)
        assert res_beta == user

        # Disallowed feature raises 403 ForbiddenError
        check_hums = require_feature("hums")
        with pytest.raises(ForbiddenError):
            check_hums(current_user=user, db=db)

        # Unknown feature not in map raises 403 ForbiddenError
        check_unknown = require_feature("unknown_feature")
        with pytest.raises(ForbiddenError):
            check_unknown(current_user=user, db=db)
