from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from .config import get_settings

PRODUCTION_HIDDEN_PATHS = {"/docs", "/redoc", "/openapi.json"}


class SecurityBoundaryMiddleware(BaseHTTPMiddleware):
    """Small application-side guardrail layer; ingress/WAF controls remain mandatory."""

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()

        if settings.app_env == "production" and request.url.path in PRODUCTION_HIDDEN_PATHS:
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        content_length = request.headers.get("content-length")
        if content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
            if declared_size < 0:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
            if declared_size > settings.max_request_body_bytes:
                return JSONResponse(
                    status_code=413,
                    content={"detail": "Request body exceeds configured application limit"},
                )

        response = await call_next(request)
        if not settings.security_headers_enabled:
            return response

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"
        response.headers["Cache-Control"] = "no-store"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = (
                f"max-age={settings.hsts_max_age_seconds}; includeSubDomains"
            )
        return response


def install_http_security(app) -> None:
    app.add_middleware(SecurityBoundaryMiddleware)
