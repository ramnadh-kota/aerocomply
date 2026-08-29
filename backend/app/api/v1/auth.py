from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    RefreshRequest,
    RegisterOrganizationRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register-organization", response_model=TokenResponse, status_code=201)
def register_organization(
    payload: RegisterOrganizationRequest, db: Session = Depends(get_db_session)
) -> TokenResponse:
    return auth_service.register_organization(db, payload)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    return auth_service.authenticate(db, payload.email, payload.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    return auth_service.refresh_access_token(db, payload.refresh_token)


@router.get("/me", response_model=CurrentUser)
def me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return current_user
