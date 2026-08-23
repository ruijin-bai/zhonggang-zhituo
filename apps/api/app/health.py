from fastapi import APIRouter, HTTPException
from redis import Redis
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .db import engine

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Process-level liveness probe.

    This endpoint intentionally avoids external dependencies so an orchestrator can
    distinguish a dead process from a temporarily unavailable dependency.
    """
    return {"status": "ok", "service": "zhituo-api"}


@router.get("/health/ready")
def readiness() -> dict:
    """Dependency-aware readiness probe for production traffic."""
    checks: dict[str, str] = {}

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except SQLAlchemyError as exc:
        checks["database"] = "failed"
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "checks": checks, "error": type(exc).__name__},
        ) from exc

    if settings.job_mode == "queue":
        try:
            client = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
            client.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = "failed"
            raise HTTPException(
                status_code=503,
                detail={"status": "not_ready", "checks": checks, "error": type(exc).__name__},
            ) from exc
    else:
        checks["redis"] = "not_required"

    return {"status": "ready", "checks": checks, "job_mode": settings.job_mode}
