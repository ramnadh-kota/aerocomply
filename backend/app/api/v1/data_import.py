import uuid

from fastapi import APIRouter, Depends, Form, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session
from app.core.errors import ForbiddenError
from app.core.permissions import Permission, permissions_for_roles
from app.schemas.auth import CurrentUser
from app.schemas.data_import import (
    ImportConfigureRequest,
    ImportJobDetailResponse,
    ImportJobResponse,
    ImportMappingCreateRequest,
    ImportMappingResponse,
)
from app.services import import_service

router = APIRouter(prefix="/data-import", tags=["data-import"])


def require_import_read(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    granted = permissions_for_roles(current_user.roles)
    if (
        Permission.AIRCRAFT_READ.value not in granted
        and Permission.DRONE_READ.value not in granted
        and Permission.ORG_MANAGE.value not in granted
    ):
        raise ForbiddenError("Missing required import read permission")
    return current_user


def require_import_write(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    granted = permissions_for_roles(current_user.roles)
    if (
        Permission.AIRCRAFT_WRITE.value not in granted
        and Permission.DRONE_WRITE.value not in granted
        and Permission.ORG_MANAGE.value not in granted
    ):
        raise ForbiddenError("Missing required import write permission")
    return current_user


@router.post("/{domain}/validate", response_model=ImportJobDetailResponse, status_code=status.HTTP_201_CREATED)
async def validate_import(
    domain: str,
    file: UploadFile,
    sheet_name: str | None = Form(default=None),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_import_write),
) -> ImportJobDetailResponse:
    content = await file.read()
    job = import_service.create_import_job(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        domain=domain.upper(),
        filename=file.filename or "upload.csv",
        file_content=content,
        sheet_name=sheet_name,
    )
    return ImportJobDetailResponse.model_validate(job)


@router.post("/jobs/{job_id}/configure", response_model=ImportJobDetailResponse)
def configure_job(
    job_id: uuid.UUID,
    payload: ImportConfigureRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_import_write),
) -> ImportJobDetailResponse:
    job = import_service.configure_import_job(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        job_id=job_id,
        column_mapping=payload.column_mapping,
        match_strategy=payload.match_strategy,
    )
    return ImportJobDetailResponse.model_validate(job)


@router.get("/jobs", response_model=list[ImportJobResponse])
def list_jobs(
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_import_read),
) -> list[ImportJobResponse]:
    jobs = import_service.list_import_jobs(db, organization_id=current_user.organization_id)
    return [ImportJobResponse.model_validate(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=ImportJobDetailResponse)
def get_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_import_read),
) -> ImportJobDetailResponse:
    job = import_service.get_import_job(
        db, organization_id=current_user.organization_id, job_id=job_id
    )
    return ImportJobDetailResponse.model_validate(job)


@router.post("/jobs/{job_id}/commit", response_model=ImportJobDetailResponse)
def commit_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_import_write),
) -> ImportJobDetailResponse:
    job = import_service.commit_import_job(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        job_id=job_id,
    )
    return ImportJobDetailResponse.model_validate(job)


# ---------------------------------------------------------------------------
# Saved Column Mappings API
# ---------------------------------------------------------------------------


@router.post("/mappings", response_model=ImportMappingResponse, status_code=status.HTTP_201_CREATED)
def create_mapping(
    payload: ImportMappingCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_import_write),
) -> ImportMappingResponse:
    mapping = import_service.create_import_mapping(
        db,
        organization_id=current_user.organization_id,
        actor_user_id=current_user.id,
        domain=payload.domain,
        name=payload.name,
        mapping=payload.mapping,
        is_default=payload.is_default,
    )
    return ImportMappingResponse.model_validate(mapping)


@router.get("/mappings", response_model=list[ImportMappingResponse])
def list_mappings(
    domain: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_import_read),
) -> list[ImportMappingResponse]:
    mappings = import_service.list_import_mappings(
        db, organization_id=current_user.organization_id, domain=domain
    )
    return [ImportMappingResponse.model_validate(m) for m in mappings]


@router.get("/mappings/{mapping_id}", response_model=ImportMappingResponse)
def get_mapping(
    mapping_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_import_read),
) -> ImportMappingResponse:
    mapping = import_service.get_import_mapping(
        db, organization_id=current_user.organization_id, mapping_id=mapping_id
    )
    return ImportMappingResponse.model_validate(mapping)


@router.delete("/mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mapping(
    mapping_id: uuid.UUID,
    db: Session = Depends(get_db_session),
    current_user: CurrentUser = Depends(require_import_write),
) -> None:
    import_service.delete_import_mapping(
        db, organization_id=current_user.organization_id, mapping_id=mapping_id
    )
