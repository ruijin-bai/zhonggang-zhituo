import logging

from celery import Task

from .job_ledger import transition_job_runtime

logger = logging.getLogger("zhituo.tasks")


class TrackedTask(Task):
    abstract = True

    def _organization_id(self, args, kwargs) -> str | None:
        headers = getattr(self.request, "headers", None) or {}
        from_header = headers.get("organization_id")
        if isinstance(from_header, str) and from_header:
            return from_header
        candidate = kwargs.get("organization_id")
        if isinstance(candidate, str) and candidate:
            return candidate
        if args and isinstance(args[-1], str):
            return args[-1]
        return None

    def _transition(self, task_id: str, args, kwargs, *, status: str, error: str | None = None, increment_attempt: bool = False) -> None:
        organization_id = self._organization_id(args, kwargs)
        if not organization_id:
            logger.error("tracked task missing organization context", extra={"job_id": task_id, "status": status})
            return
        transition_job_runtime(
            organization_id=organization_id,
            job_id=task_id,
            status=status,
            error_detail=error,
            increment_attempt=increment_attempt,
        )

    def before_start(self, task_id, args, kwargs):
        self._transition(task_id, args, kwargs, status="running", increment_attempt=True)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        self._transition(task_id, args, kwargs, status="retrying", error=str(exc))
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        self._transition(task_id, args, kwargs, status="succeeded")
        super().on_success(retval, task_id, args, kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        self._transition(task_id, args, kwargs, status="failed", error=str(exc))
        super().on_failure(exc, task_id, args, kwargs, einfo)
