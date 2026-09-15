from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db_session
from app.core.rate_limit import rate_limit
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    RefreshRequest,
    RegisterOrganizationRequest,
    TokenResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

# M17.2: the three highest-risk unauthenticated endpoints in this router --
# credential-stuffing/brute-force against login, refresh-token guessing, and
# registration abuse -- each get their own independent per-IP budget. See
# app/core/rate_limit.py for the process-local-only limitation.
_AUTH_RATE_LIMIT = 20
_AUTH_RATE_WINDOW_SECONDS = 60


@router.post(
    "/register-organization",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[
        Depends(
            rate_limit(
                "auth_register", limit=_AUTH_RATE_LIMIT, window_seconds=_AUTH_RATE_WINDOW_SECONDS
            )
        )
    ],
)
def register_organization(
    payload: RegisterOrganizationRequest, db: Session = Depends(get_db_session)
) -> TokenResponse:
    return auth_service.register_organization(db, payload)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_login", limit=_AUTH_RATE_LIMIT, window_seconds=_AUTH_RATE_WINDOW_SECONDS
            )
        )
    ],
)
def login(payload: LoginRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    return auth_service.authenticate(db, payload.email, payload.password)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[
        Depends(
            rate_limit(
                "auth_refresh", limit=_AUTH_RATE_LIMIT, window_seconds=_AUTH_RATE_WINDOW_SECONDS
            )
        )
    ],
)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db_session)) -> TokenResponse:
    return auth_service.refresh_access_token(db, payload.refresh_token)


@router.get("/me", response_model=CurrentUser)
def me(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    return current_user
