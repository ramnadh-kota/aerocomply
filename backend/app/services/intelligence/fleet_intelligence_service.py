"""M4.2 -- Fleet Intelligence Control Center backend support.

Consumes -- never re-derives -- the existing per-asset D2.2 services
(readiness, risk, priority, decision, recommendation) plus Developer 1's own
asset lister (app/services/asset_service.py::list_assets, already
tenant-scoped, already the canonical cross-asset-type listing used
elsewhere). This module adds no new intelligence rule: it only calls
get_asset_readiness_intelligence and get_asset_recommendation once per
asset and reshapes their existing output into one fleet-wide response, so
the frontend can render a Control Center without making
N (assets) x 5 (endpoints) requests from the browser.

Why two calls per asset (not five): get_asset_recommendation already
cascades through decision -> priority -> risk -> readiness internally, so
it alone yields readiness_state, risk_level, priority_level, decision_state,
blockers, and warnings. The only fields it does not carry are
operational_state and aerospace_intelligence_status (readiness-only
fields not echoed onto AssetDecision/AssetRecommendation), which requires
one additional call to get_asset_readiness_intelligence. No third or
fourth call is needed.
"""

import datetime
import uuid

from sqlalchemy.orm import Session

from app.schemas.intelligence import FleetAssetIntelligence, FleetIntelligenceSummary
from app.services import asset_service
from app.services.intelligence.readiness_intelligence_service import (
    get_asset_readiness_intelligence,
)
from app.services.intelligence.recommendation_service import get_asset_recommendation


def get_fleet_intelligence_summary(
    db: Session, *, organization_id: uuid.UUID
) -> FleetIntelligenceSummary:
    assets = asset_service.list_assets(db, organization_id=organization_id)

    summaries: list[FleetAssetIntelligence] = []
    for asset in assets:
        readiness = get_asset_readiness_intelligence(
            db, organization_id=organization_id, asset_id=asset.id
        )
        recommendation = get_asset_recommendation(
            db, organization_id=organization_id, asset_id=asset.id
        )
        top_action = recommendation.items[0].action if recommendation.items else None

        summaries.append(
            FleetAssetIntelligence(
                asset_id=asset.id,
                registration=asset.registration,
                asset_type=asset.asset_type,
                operational_state=readiness.operational_state,
                aerospace_intelligence_status=str(
                    readiness.contributing_factors.get("aerospace_intelligence_status", "UNKNOWN")
                ),
                readiness_state=recommendation.readiness_state,
                risk_level=recommendation.risk_level,
                priority_level=recommendation.priority_level,
                decision_state=recommendation.recommendation_state,
                decision_reason=recommendation.explanation[0] if recommendation.explanation else "",
                top_recommendation_action=top_action,
                blocker_count=len(recommendation.blockers),
                warning_count=len(recommendation.warnings),
                blockers=recommendation.blockers,
                warnings=recommendation.warnings,
                evaluated_at=recommendation.evaluated_at,
            )
        )

    return FleetIntelligenceSummary(
        total_assets=len(summaries),
        assets=summaries,
        evaluated_at=datetime.datetime.now(datetime.UTC),
    )
