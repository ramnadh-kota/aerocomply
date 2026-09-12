import uuid

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_db_session, require_permission
from app.core.permissions import Permission
from app.schemas.auth import CurrentUser
from app.schemas.data_import import ImportJobDetailResponse, ImportJobResponse
from app.services import import_service

router = APIRouter(prefix="/data-import", tags=["data-import"])


@router.post("/{domain}/validate", response_model=ImportJobDetailResponse, status_code=201)
async def validate_import(
    domain: str,
    file: UploadFile,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> ImportJobDetailResponse:
    content = await file.read()
    job = import_service.create_import_job(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        domain=domain.upper(),
        filename=file.filename or "upload.csv",
        file_content=content,
    )
    return ImportJobDetailResponse.model_validate(job)


@router.get("/jobs", response_model=list[ImportJobResponse])
def list_jobs(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> list[ImportJobResponse]:
    jobs = import_service.list_import_jobs(db, organization_id=current_user.organization_id)
    return [ImportJobResponse.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=ImportJobDetailResponse)
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_READ)),
) -> ImportJobDetailResponse:
    job = import_service.get_import_job(
        db, organization_id=current_user.organization_id, job_id=job_id
    )
    return ImportJobDetailResponse.model_validate(job)


@router.post("/jobs/{job_id}/commit", response_model=ImportJobDetailResponse)
def commit_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_permission(Permission.AIRCRAFT_WRITE)),
) -> ImportJobDetailResponse:
    job = import_service.commit_import_job(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        job_id=job_id,
    )
    return ImportJobDetailResponse.model_validate(job)
