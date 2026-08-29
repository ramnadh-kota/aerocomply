"""Request correlation ID middleware and structured-log context binding.

Every request gets a request_id (from the client's X-Request-ID header if
present, otherwise generated). It is bound into structlog's contextvars for
the duration of the request so every log line emitted while handling that
request carries request_id, organization_id, user_id, endpoint, and — on
completion — status_code and duration_ms, without every log call site having
to pass them explicitly.
"""
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid.uuid4()))
        start = time.perf_counter()

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            endpoint=request.url.path,
        )

        # organization_id / user_id are bound by get_current_user (app.core.deps)
        # once the bearer token is decoded, via bind_request_identity() below —
        # this middleware only guarantees request_id/endpoint are always present,
        # even for unauthenticated requests (e.g. failed logins, health checks).

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "request_completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def bind_request_identity(organization_id: str, user_id: str) -> None:
    """Call from an auth dependency once the token is decoded, so subsequent
    log lines in the same request (including the completion log above) carry
    organization_id/user_id without threading them through every function call.
    """
    structlog.contextvars.bind_contextvars(organization_id=organization_id, user_id=user_id)
