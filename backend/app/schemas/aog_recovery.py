from pydantic import BaseModel, ConfigDict


class RecoveryBlockerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str
    description: str
    record_type: str
    record_id: str | None
    who_should_act: str
    dependency: str


class CriticalPathStageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    status: str
    reason: str
    record_type: str | None
    record_id: str | None
    next_action: str | None


class AogRecoveryStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    aircraft_id: str
    registration: str
    is_aog: bool
    aog_event_id: str | None
    aog_status: str | None
    severity: str | None
    work_order_id: str | None
    release_readiness_status: str | None
    tat_status: str | None
    tat_reason: str | None
    blockers: list[RecoveryBlockerResponse]
    next_best_action: RecoveryBlockerResponse | None
    critical_path: list[CriticalPathStageResponse]
    technician_authorization: str
    eta: str
    compliance_status: str
    data_completeness: str
