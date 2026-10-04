import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.fleet_intelligence import (
    FleetAnomalyPatternCorrelation,
    FleetCorrelationContext,
)
from app.schemas.intelligence import (
    AssetDecision,
    AssetPriorityIntelligence,
    AssetReadinessIntelligence,
    AssetRecommendation,
    AssetRiskIntelligence,
    FleetIntelligenceSummary,
    IntelligenceContext,
)
from app.schemas.intelligence_signal import (
    ProactiveIntelligenceSummary,
    ProactiveSignalResponse,
    SignalAcknowledgeRequest,
    SignalDismissRequest,
    SignalInReviewRequest,
    SignalResolveRequest,
)
from app.services.intelligence import (
    context_service,
    decision_service,
    fleet_intelligence_service,
    priority_intelligence_service,
    proactive_intelligence_service,
    readiness_intelligence_service,
    recommendation_service,
    risk_intelligence_service,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


# ---------------------------------------------------------------------------
# M7 Proactive Intelligence & Early-Warning Signals
# ---------------------------------------------------------------------------


@router.get("/summary", response_model=ProactiveIntelligenceSummary)
def get_proactive_intelligence_summary(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> ProactiveIntelligenceSummary:
    """Returns the Command Center Proactive Intelligence Overview across the fleet."""
    return proactive_intelligence_service.get_proactive_summary(
        db, organization_id=current_user.organization_id
    )


@router.get("/signals", response_model=list[ProactiveSignalResponse])
def list_proactive_signals(
    asset_id: uuid.UUID | None = Query(None, description="Filter signals by asset ID"),
    signal_type: str | None = Query(None, description="Filter by signal type"),
    severity: str | None = Query(None, description="Filter by severity level (CRITICAL, HIGH, MEDIUM, LOW)"),
    status: str | None = Query(None, description="Filter by lifecycle status (OPEN, ACKNOWLEDGED, IN_REVIEW, RESOLVED, DISMISSED)"),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[ProactiveSignalResponse]:
    """Lists deterministic proactive intelligence signals for the tenant."""
    return proactive_intelligence_service.sync_and_get_signals(
        db,
        organization_id=current_user.organization_id,
        asset_id=asset_id,
        signal_type=signal_type,
        severity=severity,
        status=status,
    )


@router.get("/signals/{signal_id}", response_model=ProactiveSignalResponse)
def get_proactive_signal_detail(
    signal_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> ProactiveSignalResponse:
    """Returns details and full evidence provenance for a single intelligence signal."""
    signals = proactive_intelligence_service.sync_and_get_signals(
        db, organization_id=current_user.organization_id
    )
    for s in signals:
        if s.id == signal_id:
            return s
    from app.core.errors import NotFoundError
    raise NotFoundError("Signal not found", code="signal_not_found")


@router.post("/signals/{signal_id}/acknowledge", response_model=ProactiveSignalResponse)
def acknowledge_proactive_signal(
    signal_id: uuid.UUID,
    request: SignalAcknowledgeRequest | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> ProactiveSignalResponse:
    """Records operator acknowledgement of an intelligence signal."""
    return proactive_intelligence_service.acknowledge_signal(
        db,
        organization_id=current_user.organization_id,
        signal_id=signal_id,
        user_id=current_user.id,
    )


@router.post("/signals/{signal_id}/in-review", response_model=ProactiveSignalResponse)
def set_proactive_signal_in_review(
    signal_id: uuid.UUID,
    request: SignalInReviewRequest | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> ProactiveSignalResponse:
    """Transitions an intelligence signal to IN_REVIEW status."""
    return proactive_intelligence_service.set_signal_in_review(
        db,
        organization_id=current_user.organization_id,
        signal_id=signal_id,
        user_id=current_user.id,
        notes=request.notes if request else None,
    )


@router.post("/signals/{signal_id}/resolve", response_model=ProactiveSignalResponse)
def resolve_proactive_signal(
    signal_id: uuid.UUID,
    request: SignalResolveRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> ProactiveSignalResponse:
    """Resolves an intelligence signal following corrective maintenance or verification action."""
    return proactive_intelligence_service.resolve_signal(
        db,
        organization_id=current_user.organization_id,
        signal_id=signal_id,
        user_id=current_user.id,
        resolution_notes=request.resolution_notes,
    )


@router.post("/signals/{signal_id}/dismiss", response_model=ProactiveSignalResponse)
def dismiss_proactive_signal(
    signal_id: uuid.UUID,
    request: SignalDismissRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> ProactiveSignalResponse:
    """Dismisses an intelligence signal with operational justification."""
    return proactive_intelligence_service.dismiss_signal(
        db,
        organization_id=current_user.organization_id,
        signal_id=signal_id,
        user_id=current_user.id,
        dismissal_reason=request.dismissal_reason,
    )


@router.get("/assets/{asset_id}/signals", response_model=list[ProactiveSignalResponse])
def get_asset_proactive_signals(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[ProactiveSignalResponse]:
    """Returns all active and historical proactive intelligence signals for an asset."""
    return proactive_intelligence_service.sync_and_get_signals(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


# ---------------------------------------------------------------------------
# Existing D2.2 Deterministic Intelligence Endpoints (Protected Baseline)
# ---------------------------------------------------------------------------


@router.get("/fleet", response_model=FleetIntelligenceSummary)
def get_fleet_intelligence_summary(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> FleetIntelligenceSummary:
    return fleet_intelligence_service.get_fleet_intelligence_summary(
        db, organization_id=current_user.organization_id
    )


@router.get("/fleet/correlation", response_model=FleetCorrelationContext)
def get_fleet_correlation(
    asset_id: uuid.UUID | None = Query(None, description="Filter correlations containing this asset ID"),
    pattern_type: str | None = Query(None, description="Filter by pattern type"),
    feature_family: str | None = Query(None, description="Filter by feature family (e.g. vibration_rms)"),
    confidence: str | None = Query(None, description="Filter by confidence level (HIGH, MEDIUM, LOW, INSUFFICIENT_EVIDENCE)"),
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> FleetCorrelationContext:
    """Returns deterministic cross-asset HUMS and fleet anomaly pattern correlation (H8.3)."""
    from app.services.intelligence.cross_asset_intelligence_service import get_fleet_correlation_context

    context = get_fleet_correlation_context(
        db, organization_id=current_user.organization_id, lookback_days=days
    )
    if any([asset_id, pattern_type, feature_family, confidence]):
        filtered = context.anomaly_correlations
        if asset_id:
            filtered = [c for c in filtered if asset_id in c.participating_asset_ids]
        if pattern_type:
            filtered = [c for c in filtered if c.pattern_type == pattern_type]
        if feature_family:
            ff = feature_family.lower()
            filtered = [c for c in filtered if ff in c.feature_family.lower() or c.feature_family.lower() in ff]
        if confidence:
            filtered = [c for c in filtered if c.confidence == confidence]
        context.anomaly_correlations = filtered
    return context


@router.get("/fleet/correlation/{correlation_id}", response_model=FleetAnomalyPatternCorrelation)
def get_fleet_correlation_detail(
    correlation_id: uuid.UUID,
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> FleetAnomalyPatternCorrelation:
    """Returns detail and evidence provenance for a single cross-asset correlation record."""
    from app.core.errors import NotFoundError
    from app.services.intelligence.cross_asset_intelligence_service import get_fleet_correlation_context

    context = get_fleet_correlation_context(
        db, organization_id=current_user.organization_id, lookback_days=days
    )
    for corr in context.anomaly_correlations:
        if corr.id == correlation_id:
            return corr
    raise NotFoundError("Fleet correlation not found", code="correlation_not_found")


@router.get("/assets/{asset_id}/readiness", response_model=AssetReadinessIntelligence)
def get_asset_readiness_intelligence(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> AssetReadinessIntelligence:
    return readiness_intelligence_service.get_asset_readiness_intelligence(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/assets/{asset_id}/risk", response_model=AssetRiskIntelligence)
def get_asset_risk_intelligence(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> AssetRiskIntelligence:
    return risk_intelligence_service.get_asset_risk_intelligence(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/assets/{asset_id}/priority", response_model=AssetPriorityIntelligence)
def get_asset_priority_intelligence(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> AssetPriorityIntelligence:
    return priority_intelligence_service.get_asset_priority_intelligence(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/assets/{asset_id}/decision", response_model=AssetDecision)
def get_asset_decision(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> AssetDecision:
    return decision_service.get_asset_decision(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/assets/{asset_id}/recommendations", response_model=AssetRecommendation)
def get_asset_recommendation(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> AssetRecommendation:
    return recommendation_service.get_asset_recommendation(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )


@router.get("/assets/{asset_id}/context", response_model=IntelligenceContext)
def get_asset_intelligence_context(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> IntelligenceContext:
    return context_service.get_asset_intelligence_context(
        db, organization_id=current_user.organization_id, asset_id=asset_id
    )
