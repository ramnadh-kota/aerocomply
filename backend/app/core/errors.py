from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

logger = get_logger(__name__)


class AeroComplyError(Exception):
    """Base application error with an HTTP status and a machine-readable code."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "error"

    def __init__(self, message: str, code: str | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class NotFoundError(AeroComplyError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ForbiddenError(AeroComplyError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class UnauthorizedError(AeroComplyError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ConflictError(AeroComplyError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


def _error_body(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


async def aerocomply_error_handler(request: Request, exc: AeroComplyError) -> JSONResponse:
    logger.info("request_error", code=exc.code, message=exc.message, path=str(request.url))
    return JSONResponse(status_code=exc.status_code, content=_error_body(exc.code, exc.message))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_error_body("validation_error", str(exc.errors())),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", path=str(request.url), exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("internal_error", "An unexpected error occurred."),
    )
