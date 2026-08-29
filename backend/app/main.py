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

settings = get_settings()
configure_logging()

if settings.environment != "development" and settings.jwt_secret_key == "CHANGE_ME_IN_PRODUCTION":
    raise RuntimeError(
        "JWT_SECRET_KEY is still the default placeholder outside a development "
        "environment. Set a real secret before starting AeroComply."
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

# Starlette's add_exception_handler() is typed to accept a handler for the base
# Exception class; registering one scoped to a specific subclass (the standard,
# correct FastAPI pattern — FastAPI dispatches by the registered type at
# runtime) doesn't structurally match that signature. Widen the static type
# with an explicit cast rather than weakening each handler's own parameter type.
ExceptionHandler = Callable[[Request, Exception], Awaitable[Response]]

app.add_exception_handler(AeroComplyError, cast(ExceptionHandler, aerocomply_error_handler))
app.add_exception_handler(
    RequestValidationError, cast(ExceptionHandler, validation_error_handler)
)
app.add_exception_handler(Exception, unhandled_error_handler)

app.include_router(api_router, prefix=settings.api_v1_prefix)
