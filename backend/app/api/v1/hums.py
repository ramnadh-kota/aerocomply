"""H1 + H2 + H3 + H4: HUMS API.

H1: sensors, readings, asset-level health (simple RMS-threshold), exceedances.
H2: feature history, spectrum.
H3: baseline, deviation, trend, and explainable component/asset health
    intelligence (separate from H1's simpler `/health`).
H4: rule-based diagnostic candidates and fault isolation — never a
    confirmed fault except via the explicit, authorized confirm/reject
    actions below.

Prognostics/RUL/digital-twin/fleet endpoints described in the full HUMS
spec are not yet implemented.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_feature, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.hums import (
    HUMSAssetHealthIntelligence,
    HUMSAssetHealthSummary,
    HUMSBaselineResponse,
    HUMSComponentHealthIntelligence,
    HUMSDegradationModelResponse,
    HUMSDeviationResponse,
    HUMSDiagnosticCandidateResponse,
    HUMSDiagnosticRejectRequest,
    HUMSExceedanceResponse,
    HUMSFeatureResponse,
    HUMSPrognosticRecordResponse,
    HUMSReadingBatchCreate,
    HUMSSensorCreate,
    HUMSSensorThresholdUpdate,
    HUMSSensorReadingResponse,
    HUMSSensorResponse,
    HUMSSpectrumResponse,
    HUMSTrendResponse,
)
from app.services import hums_service

router = APIRouter(
    prefix="/hums",
    tags=["hums"],
    dependencies=[Depends(require_feature("hums"))],
)


@router.post("/sensors", response_model=HUMSSensorResponse)
def create_sensor(
    payload: HUMSSensorCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_WRITE)),
) -> HUMSSensorResponse:
    sensor = hums_service.create_sensor(
        db, organization_id=current_user.organization_id, user_id=current_user.id, payload=payload
    )
    db.commit()
    return HUMSSensorResponse.model_validate(sensor)


@router.put("/sensors/{sensor_id}/thresholds", response_model=HUMSSensorResponse)
def set_sensor_thresholds(
    sensor_id: uuid.UUID,
    payload: HUMSSensorThresholdUpdate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_WRITE)),
) -> HUMSSensorResponse:
    """Configure the vibration RMS warning/critical limits for one sensor (OEM / maintenance-manual values), or send
    both as null to return to the platform defaults. Audited with the previous values."""
    sensor = hums_service.set_sensor_thresholds(
        db, organization_id=current_user.organization_id, user_id=current_user.id, sensor_id=sensor_id,
        warning_threshold=payload.warning_threshold, critical_threshold=payload.critical_threshold,
    )
    db.commit()
    return HUMSSensorResponse.model_validate(sensor)


@router.get("/sensors", response_model=list[HUMSSensorResponse])
def list_sensors(
    asset_id: uuid.UUID | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSSensorResponse]:
    sensors = hums_service.list_sensors(db, organization_id=current_user.organization_id, asset_id=asset_id)
    return [HUMSSensorResponse.model_validate(s) for s in sensors]


@router.post("/sensors/{sensor_id}/readings", response_model=list[HUMSSensorReadingResponse])
def ingest_readings(
    sensor_id: uuid.UUID,
    payload: HUMSReadingBatchCreate,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_WRITE)),
) -> list[HUMSSensorReadingResponse]:
    readings = hums_service.ingest_readings(
        db,
        organization_id=current_user.organization_id,
        sensor_id=sensor_id,
        readings=payload.readings,
        ingestion_batch=payload.ingestion_batch,
    )
    exceedance = hums_service.detect_and_record_exceedances(
        db, organization_id=current_user.organization_id, sensor_id=sensor_id, user_id=current_user.id
    )
    db.commit()
    _ = exceedance  # evaluated as a side effect of ingestion; returned via the exceedances endpoint
    return [HUMSSensorReadingResponse.model_validate(r) for r in readings]


@router.get("/assets/{asset_id}/health", response_model=HUMSAssetHealthSummary)
def get_asset_health(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> HUMSAssetHealthSummary:
    return hums_service.get_asset_health(db, organization_id=current_user.organization_id, asset_id=asset_id)


@router.get("/assets/{asset_id}/exceedances", response_model=list[HUMSExceedanceResponse])
def list_asset_exceedances(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSExceedanceResponse]:
    from sqlalchemy import select

    from app.models.hums import HUMSExceedance

    rows = db.execute(
        select(HUMSExceedance)
        .where(HUMSExceedance.organization_id == current_user.organization_id, HUMSExceedance.asset_id == asset_id)
        .order_by(HUMSExceedance.created_at.desc())
    ).scalars().all()
    return [HUMSExceedanceResponse.model_validate(r) for r in rows]


@router.get("/assets/{asset_id}/features", response_model=list[HUMSFeatureResponse])
def list_asset_features(
    asset_id: uuid.UUID,
    feature_type: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSFeatureResponse]:
    rows = hums_service.list_features(
        db, organization_id=current_user.organization_id, asset_id=asset_id, feature_type=feature_type
    )
    return [HUMSFeatureResponse.model_validate(r) for r in rows]


@router.get("/assets/{asset_id}/features/{feature_type}", response_model=list[HUMSFeatureResponse])
def list_asset_features_by_type(
    asset_id: uuid.UUID,
    feature_type: str,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSFeatureResponse]:
    rows = hums_service.list_features(
        db, organization_id=current_user.organization_id, asset_id=asset_id, feature_type=feature_type
    )
    return [HUMSFeatureResponse.model_validate(r) for r in rows]


@router.get("/components/{component_id}/features", response_model=list[HUMSFeatureResponse])
def list_component_features(
    component_id: uuid.UUID,
    feature_type: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSFeatureResponse]:
    rows = hums_service.list_features(
        db, organization_id=current_user.organization_id, component_id=component_id, feature_type=feature_type
    )
    return [HUMSFeatureResponse.model_validate(r) for r in rows]


@router.get("/sensors/{sensor_id}/features", response_model=list[HUMSFeatureResponse])
def list_sensor_features(
    sensor_id: uuid.UUID,
    feature_type: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSFeatureResponse]:
    rows = hums_service.list_features(
        db, organization_id=current_user.organization_id, sensor_id=sensor_id, feature_type=feature_type
    )
    return [HUMSFeatureResponse.model_validate(r) for r in rows]


@router.get("/sensors/{sensor_id}/spectrum", response_model=HUMSSpectrumResponse)
def get_sensor_spectrum(
    sensor_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> HUMSSpectrumResponse:
    spectrum = hums_service.get_sensor_spectrum(db, organization_id=current_user.organization_id, sensor_id=sensor_id)
    return HUMSSpectrumResponse.model_validate(spectrum)


# --- H3: Baseline & Health Intelligence ------------------------------------


@router.get("/assets/{asset_id}/baseline", response_model=list[HUMSBaselineResponse])
def get_asset_baseline(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSBaselineResponse]:
    result = hums_service.get_asset_baselines(db, organization_id=current_user.organization_id, asset_id=asset_id)
    db.commit()
    return result


@router.get("/assets/{asset_id}/trends", response_model=list[HUMSTrendResponse])
def get_asset_trends(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSTrendResponse]:
    result = hums_service.get_asset_trends(db, organization_id=current_user.organization_id, asset_id=asset_id)
    db.commit()
    return result


@router.get("/assets/{asset_id}/deviations", response_model=list[HUMSDeviationResponse])
def get_asset_deviations(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSDeviationResponse]:
    result = hums_service.get_asset_deviations(db, organization_id=current_user.organization_id, asset_id=asset_id)
    db.commit()
    return result


@router.get("/assets/{asset_id}/health-intelligence", response_model=HUMSAssetHealthIntelligence)
def get_asset_health_intelligence(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> HUMSAssetHealthIntelligence:
    result = hums_service.get_asset_health_intelligence(
        db, organization_id=current_user.organization_id, asset_id=asset_id, user_id=current_user.id
    )
    db.commit()  # may have created/updated a baseline row, ProactiveSignalRecord, and/or diagnostic candidates as a side effect
    return result


@router.get("/components/{component_id}/health", response_model=HUMSComponentHealthIntelligence)
def get_component_health(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> HUMSComponentHealthIntelligence:
    result = hums_service.get_component_health_intelligence(
        db, organization_id=current_user.organization_id, component_id=component_id, user_id=current_user.id
    )
    db.commit()
    return result


# --- H4: Diagnostics & Fault Isolation --------------------------------------


@router.get("/assets/{asset_id}/diagnostics", response_model=list[HUMSDiagnosticCandidateResponse])
def list_asset_diagnostics(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSDiagnosticCandidateResponse]:
    rows = hums_service.list_asset_diagnostics(db, organization_id=current_user.organization_id, asset_id=asset_id)
    return [HUMSDiagnosticCandidateResponse.model_validate(r) for r in rows]


@router.get("/assets/{asset_id}/diagnostics/{diagnostic_id}", response_model=HUMSDiagnosticCandidateResponse)
def get_asset_diagnostic(
    asset_id: uuid.UUID,
    diagnostic_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> HUMSDiagnosticCandidateResponse:
    row = hums_service.get_diagnostic(db, organization_id=current_user.organization_id, candidate_id=diagnostic_id)
    return HUMSDiagnosticCandidateResponse.model_validate(row)


@router.get("/components/{component_id}/diagnostics", response_model=list[HUMSDiagnosticCandidateResponse])
def list_component_diagnostics(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSDiagnosticCandidateResponse]:
    rows = hums_service.list_component_diagnostics(db, organization_id=current_user.organization_id, component_id=component_id)
    return [HUMSDiagnosticCandidateResponse.model_validate(r) for r in rows]


@router.post("/diagnostics/{diagnostic_id}/confirm", response_model=HUMSDiagnosticCandidateResponse)
def confirm_diagnostic(
    diagnostic_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_WRITE)),
) -> HUMSDiagnosticCandidateResponse:
    """Authorized-human-only action — HUMS never confirms its own diagnosis."""
    row = hums_service.confirm_diagnostic(
        db, organization_id=current_user.organization_id, candidate_id=diagnostic_id, user_id=current_user.id
    )
    db.commit()
    return HUMSDiagnosticCandidateResponse.model_validate(row)


@router.post("/diagnostics/{diagnostic_id}/reject", response_model=HUMSDiagnosticCandidateResponse)
def reject_diagnostic(
    diagnostic_id: uuid.UUID,
    payload: HUMSDiagnosticRejectRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_WRITE)),
) -> HUMSDiagnosticCandidateResponse:
    row = hums_service.reject_diagnostic(
        db, organization_id=current_user.organization_id, candidate_id=diagnostic_id, user_id=current_user.id, reason=payload.reason
    )
    db.commit()
    return HUMSDiagnosticCandidateResponse.model_validate(row)


# --- H5: Prognostics & Remaining Useful Life --------------------------------


@router.get("/assets/{asset_id}/prognostics", response_model=list[HUMSPrognosticRecordResponse], dependencies=[Depends(require_feature("predictive_maintenance"))])
def list_asset_prognostics(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSPrognosticRecordResponse]:
    rows = hums_service.list_asset_prognostics(db, organization_id=current_user.organization_id, asset_id=asset_id)
    return [HUMSPrognosticRecordResponse.model_validate(r) for r in rows]


@router.get("/assets/{asset_id}/prognostics/{prognostic_id}", response_model=HUMSPrognosticRecordResponse, dependencies=[Depends(require_feature("predictive_maintenance"))])
def get_asset_prognostic(
    asset_id: uuid.UUID,
    prognostic_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> HUMSPrognosticRecordResponse:
    row = hums_service.get_prognostic(db, organization_id=current_user.organization_id, prognostic_id=prognostic_id)
    return HUMSPrognosticRecordResponse.model_validate(row)


@router.get("/components/{component_id}/prognostics", response_model=list[HUMSPrognosticRecordResponse], dependencies=[Depends(require_feature("predictive_maintenance"))])
def list_component_prognostics(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSPrognosticRecordResponse]:
    rows = hums_service.list_component_prognostics(db, organization_id=current_user.organization_id, component_id=component_id)
    return [HUMSPrognosticRecordResponse.model_validate(r) for r in rows]


@router.get("/assets/{asset_id}/degradation", response_model=list[HUMSDegradationModelResponse])
def list_asset_degradation(
    asset_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSDegradationModelResponse]:
    rows = hums_service.list_asset_degradation_models(db, organization_id=current_user.organization_id, asset_id=asset_id)
    return [HUMSDegradationModelResponse.model_validate(r) for r in rows]


@router.get("/components/{component_id}/degradation", response_model=list[HUMSDegradationModelResponse])
def list_component_degradation(
    component_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.HUMS_READ)),
) -> list[HUMSDegradationModelResponse]:
    rows = hums_service.list_component_degradation_models(db, organization_id=current_user.organization_id, component_id=component_id)
    return [HUMSDegradationModelResponse.model_validate(r) for r in rows]
