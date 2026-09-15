"""M17.2: minimal, standards-aligned security response headers.

Deliberately conservative -- only headers that cannot break this API's own
clients (JSON REST responses, multipart uploads, presigned-URL redirects)
or the Next.js frontend that consumes it:

- X-Content-Type-Options: nosniff -- stops a browser from MIME-sniffing a
  response into executing as something other than its declared Content-Type.
- X-Frame-Options: DENY -- this API serves no page meant to be framed.
- Referrer-Policy: strict-origin-when-cross-origin -- avoids leaking full
  request paths (which can contain resource ids) to third-party origins on
  cross-origin navigation, while keeping same-origin referrers intact.
- Permissions-Policy: a minimal explicit deny-list for browser features this
  API has no reason to grant to any embedding context.

Content-Security-Policy and Strict-Transport-Security are deliberately NOT
added here: CSP requires knowing the frontend's actual asset/script origins
to avoid breaking it, and HSTS is only safe to promise once the production
TLS/proxy topology (e.g. whether the deployment always terminates behind
HTTPS) has been directly verified -- neither has been done for this
milestone, so this does not claim behavior it hasn't confirmed.
"""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=(), payment=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response
