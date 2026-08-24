import json
import logging
import re
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Request

from .config import get_settings
from .http_security import SecurityBoundaryMiddleware
from .metrics import HTTP_IN_FLIGHT, metrics_response, observe_http

SAFE_ID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "event",
            "request_id",
            "correlation_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "organization_id",
            "user_id",
            "job_id",
            "job_type",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())


def _safe_external_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized if SAFE_ID.fullmatch(normalized) else None


def install_observability(app: FastAPI) -> None:
    settings = get_settings()
    logger = logging.getLogger("zhituo.request")
    app.add_middleware(SecurityBoundaryMiddleware)

    @app.get("/internal/metrics", include_in_schema=False)
    def internal_metrics(request: Request):
        return metrics_response(request)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = _safe_external_id(request.headers.get(settings.request_id_header)) or str(uuid4())
        correlation_id = (
            _safe_external_id(request.headers.get(settings.correlation_id_header))
            or request_id
        )
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        started = time.perf_counter()
        status_code = 500
        HTTP_IN_FLIGHT.inc()
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[settings.request_id_header] = request_id
            response.headers[settings.correlation_id_header] = correlation_id
            return response
        except Exception:
            principal = getattr(request.state, "principal", None)
            logger.exception(
                "request_failed",
                extra={
                    "event": "http.request.failed",
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    "organization_id": getattr(principal, "organization_id", None),
                    "user_id": getattr(principal, "user_id", None),
                },
            )
            raise
        finally:
            duration_seconds = time.perf_counter() - started
            HTTP_IN_FLIGHT.dec()
            observe_http(request, status_code, duration_seconds)
            if status_code != 500:
                principal = getattr(request.state, "principal", None)
                logger.info(
                    "request_complete",
                    extra={
                        "event": "http.request.complete",
                        "request_id": request_id,
                        "correlation_id": correlation_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": round(duration_seconds * 1000, 2),
                        "organization_id": getattr(principal, "organization_id", None),
                        "user_id": getattr(principal, "user_id", None),
                    },
                )
