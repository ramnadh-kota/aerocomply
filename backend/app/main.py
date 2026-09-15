from collections.abc import Awaitable, Callable
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import (
    AeroComplyError,
    aerocomply_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging
from app.core.request_context import RequestContextMiddleware
from app.core.security_headers import SecurityHeadersMiddleware

settings = get_settings()
configure_logging()

if settings.environment != "development" and settings.jwt_secret_key == "CHANGE_ME_IN_PRODUCTION":
    raise RuntimeError(
        "JWT_SECRET_KEY is still the default placeholder outside a development "
        "environment. Set a real secret before starting AeroComply."
    )

_DEFAULT_LOCAL_DATABASE_URL = "postgresql+psycopg://aerocomply:aerocomply@localhost:5432/aerocomply"
if settings.environment != "development" and settings.database_url == _DEFAULT_LOCAL_DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is still the default local-development placeholder outside a "
        "development environment. Set a real production DATABASE_URL before "
        "starting AeroComply — otherwise it would silently try to reach a "
        "localhost Postgres that does not exist in production."
    )

# M17.2: a wildcard origin combined with credentialed CORS is never a valid
# configuration for this API (every real client authenticates with a bearer
# token sent from a specific, known origin) -- browsers already refuse to
# honor `Access-Control-Allow-Origin: *` alongside credentialed requests,
# but failing fast here means a misconfigured CORS_ALLOW_ORIGINS is caught
# at startup instead of silently producing CORS errors (or worse, being
# relied upon by a non-browser client that doesn't enforce that rule).
if "*" in settings.cors_allow_origins:
    raise RuntimeError(
        "CORS_ALLOW_ORIGINS must not include '*' -- this API always sends "
        "credentialed (bearer-token) requests, and a wildcard origin combined "
        "with credentials is never a safe or valid configuration. List the "
        "actual allowed frontend origin(s) explicitly."
    )

app = FastAPI(
    title=settings.app_name,
    description="AeroComply — Aviation Compliance Intelligence Platform API",
    version="0.1.0",
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)

# Starlette's add_exception_handler() is typed to accept a handler for the base
# Exception class; registering one scoped to a specific subclass (the standard,
# correct FastAPI pattern — FastAPI dispatches by the registered type at
# runtime) doesn't structurally match that signature. Widen the static type
# with an explicit cast rather than weakening each handler's own parameter type.
ExceptionHandler = Callable[[Request, Exception], Awaitable[Response]]

app.add_exception_handler(AeroComplyError, cast(ExceptionHandler, aerocomply_error_handler))
app.add_exception_handler(RequestValidationError, cast(ExceptionHandler, validation_error_handler))
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(api_router, prefix=settings.api_v1_prefix)
