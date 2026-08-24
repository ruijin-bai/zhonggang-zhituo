import hmac
import time

from fastapi import HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

from .config import get_settings

HTTP_REQUESTS = Counter(
    "zhituo_http_requests_total",
    "HTTP requests handled by the API",
    ["method", "route", "status"],
)
HTTP_DURATION = Histogram(
    "zhituo_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
HTTP_IN_FLIGHT = Gauge(
    "zhituo_http_requests_in_flight",
    "HTTP requests currently being processed",
)
JOB_TRANSITIONS = Counter(
    "zhituo_background_job_transitions_total",
    "Background job state transitions",
    ["job_type", "status"],
)
JOB_ATTEMPTS = Counter(
    "zhituo_background_job_attempts_total",
    "Background job execution attempts",
    ["job_type"],
)
JOB_FAILURES = Counter(
    "zhituo_background_job_failures_total",
    "Background jobs entering failed state",
    ["job_type"],
)
JOB_RETRIES = Counter(
    "zhituo_background_job_retries_total",
    "Background jobs entering retrying state",
    ["job_type"],
)
JOB_STUCK_RECONCILED = Counter(
    "zhituo_background_jobs_reconciled_stuck_total",
    "Background jobs marked failed by stuck-job reconciliation",
    ["job_type"],
)
JOB_STALE_QUEUED = Gauge(
    "zhituo_background_jobs_stale_queued",
    "Queued jobs older than the configured stuck threshold; observed but not auto-failed",
)
JOB_QUEUE_LATENCY = Histogram(
    "zhituo_background_job_queue_latency_seconds",
    "Time from job submission until first execution attempt",
    ["job_type"],
    buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
)
JOB_DURATION = Histogram(
    "zhituo_background_job_duration_seconds",
    "Background job execution duration",
    ["job_type", "status"],
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 90, 120, 180, 300),
)
DEPENDENCY_UP = Gauge(
    "zhituo_dependency_up",
    "Dependency health observed during metrics scrape",
    ["dependency"],
)
DB_POOL_CHECKED_OUT = Gauge(
    "zhituo_db_pool_checked_out_connections",
    "SQLAlchemy connections currently checked out",
)
DB_POOL_SIZE = Gauge(
    "zhituo_db_pool_size_connections",
    "SQLAlchemy configured pool size when available",
)


def route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    return "unmatched"


def observe_http(request: Request, status_code: int, duration_seconds: float) -> None:
    route = route_template(request)
    HTTP_REQUESTS.labels(request.method, route, str(status_code)).inc()
    HTTP_DURATION.labels(request.method, route).observe(duration_seconds)


def observe_job_transition(job_type: str, status: str, *, increment_attempt: bool = False) -> None:
    JOB_TRANSITIONS.labels(job_type, status).inc()
    if increment_attempt:
        JOB_ATTEMPTS.labels(job_type).inc()
    if status == "failed":
        JOB_FAILURES.labels(job_type).inc()
    elif status == "retrying":
        JOB_RETRIES.labels(job_type).inc()


def observe_job_queue_latency(job_type: str, seconds: float) -> None:
    JOB_QUEUE_LATENCY.labels(job_type).observe(max(0, seconds))


def observe_job_duration(job_type: str, status: str, seconds: float) -> None:
    JOB_DURATION.labels(job_type, status).observe(max(0, seconds))


def observe_stuck_reconciled(job_type: str) -> None:
    JOB_STUCK_RECONCILED.labels(job_type).inc()


def set_stale_queued_jobs(count: int) -> None:
    JOB_STALE_QUEUED.set(max(0, count))


def _check_metrics_token(request: Request) -> None:
    settings = get_settings()
    if settings.app_env != "production":
        return
    expected = settings.metrics_token or ""
    supplied = request.headers.get("X-Metrics-Token", "")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=404, detail="Not found")


def _refresh_dependency_metrics() -> None:
    from redis import Redis
    from sqlalchemy import text

    from .db import engine

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        DEPENDENCY_UP.labels("postgresql").set(1)
    except Exception:
        DEPENDENCY_UP.labels("postgresql").set(0)

    try:
        Redis.from_url(get_settings().redis_url).ping()
        DEPENDENCY_UP.labels("redis").set(1)
    except Exception:
        DEPENDENCY_UP.labels("redis").set(0)

    pool = engine.pool
    checkedout = getattr(pool, "checkedout", None)
    size = getattr(pool, "size", None)
    if callable(checkedout):
        DB_POOL_CHECKED_OUT.set(checkedout())
    if callable(size):
        DB_POOL_SIZE.set(size())


def metrics_response(request: Request) -> Response:
    settings = get_settings()
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    _check_metrics_token(request)
    started = time.perf_counter()
    _refresh_dependency_metrics()
    payload = generate_latest()
    response = Response(content=payload, media_type=CONTENT_TYPE_LATEST)
    response.headers["Server-Timing"] = f"metrics;dur={(time.perf_counter() - started) * 1000:.2f}"
    return response
