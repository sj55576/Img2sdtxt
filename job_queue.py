"""Background job queue for asynchronous image generation."""

import asyncio
import inspect
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

logger = logging.getLogger("img2sdtxt.jobs")


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    job_type: str
    params: Dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    priority: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status.value,
            "progress": self.progress,
            "priority": self.priority,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d


class JobQueue:
    def __init__(self, max_concurrent: int = 1, max_history: int = 100):
        self._jobs: Dict[str, Job] = {}
        self._pending: List[str] = []
        self._cond = asyncio.Condition()
        self._max_concurrent = max_concurrent
        self._max_history = max_history
        self._running_count = 0
        self._lock = asyncio.Lock()
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._worker_tasks: List[asyncio.Task] = []
        self._job_tasks: Dict[str, asyncio.Task] = {}
        self._durations: Dict[str, Deque[float]] = {}
        self._listeners: List[Callable[[Job], Any]] = []

    def start(self):
        self._worker_tasks = [task for task in self._worker_tasks if not task.done()]
        missing = self._max_concurrent - len(self._worker_tasks)
        for _ in range(max(0, missing)):
            self._worker_tasks.append(asyncio.create_task(self._worker_loop()))
        if missing > 0:
            logger.info("Job queue workers started (max_concurrent=%d)", self._max_concurrent)

    def _pending_sort_key(self, job_id: str):
        job = self._jobs[job_id]
        return (-job.priority, job.created_at)

    async def _worker_loop(self):
        while True:
            try:
                async with self._cond:
                    while not self._pending:
                        await self._cond.wait()
                    job_id = self._pending.pop(0)
            except (asyncio.CancelledError, RuntimeError):
                return

            job = self._jobs.get(job_id)
            if job is None or job.status == JobStatus.CANCELLED:
                continue

            async with self._lock:
                self._running_count += 1

            try:
                task = asyncio.current_task()
                if task is not None:
                    self._job_tasks[job.id] = task
                await self._execute_job(job)
            finally:
                self._job_tasks.pop(job.id, None)
                async with self._lock:
                    self._running_count -= 1
                self._cleanup_old_jobs()

    async def _execute_job(self, job: Job):
        job.status = JobStatus.RUNNING
        job.started_at = time.time()
        await self._notify(job)
        logger.info("Job %s started (type=%s)", job.id, job.job_type)

        try:
            handler = _JOB_HANDLERS.get(job.job_type)
            if handler is None:
                raise ValueError(f"Unknown job type: {job.job_type}")

            result = await handler(job, self._progress_callback(job))
            if job.status == JobStatus.CANCELLED:
                job.completed_at = job.completed_at or time.time()
                logger.info("Job %s finished after cancellation request", job.id)
                await self._fire_listeners(job)
                return
            job.status = JobStatus.COMPLETED
            job.result = result
            job.progress = 1.0
            job.completed_at = time.time()
            elapsed = (job.completed_at - job.started_at) * 1000
            self._record_duration(job)
            logger.info("Job %s completed (%.0fms)", job.id, elapsed)
        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            job.completed_at = time.time()
            logger.info("Job %s cancelled", job.id)
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.completed_at = time.time()
            logger.error("Job %s failed: %s", job.id, e)

        await self._notify(job)
        await self._fire_listeners(job)

    def _record_duration(self, job: Job):
        if job.started_at is None or job.completed_at is None:
            return
        durations = self._durations.setdefault(job.job_type, deque(maxlen=20))
        durations.append(job.completed_at - job.started_at)

    def avg_duration(self, job_type: str) -> Optional[float]:
        durations = self._durations.get(job_type)
        if durations:
            return sum(durations) / len(durations)
        all_durations = [d for dq in self._durations.values() for d in dq]
        if all_durations:
            return sum(all_durations) / len(all_durations)
        return None

    def add_listener(self, callback: Callable[[Job], Any]):
        self._listeners.append(callback)

    async def _fire_listeners(self, job: Job):
        for callback in self._listeners:
            try:
                result = callback(job)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception("Job listener raised an exception for job %s", job.id)

    def _progress_callback(self, job: Job):
        async def update_progress(progress: float):
            job.progress = min(max(progress, 0.0), 1.0)
            await self._notify(job)

        return update_progress

    async def submit(self, job_type: str, params: Dict[str, Any], priority: int = 0) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, job_type=job_type, params=params, priority=priority)
        self._jobs[job_id] = job
        async with self._cond:
            self._pending.append(job_id)
            self._pending.sort(key=self._pending_sort_key)
            self._cond.notify()
        logger.info("Job %s submitted (type=%s, queue_size=%d)", job_id, job_type, len(self._pending))
        self.start()
        return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def job_info(self, job: Job) -> Dict[str, Any]:
        d = job.to_dict()
        if job.status != JobStatus.PENDING:
            return d
        try:
            position = self._pending.index(job.id)
        except ValueError:
            return d
        d["queue_position"] = position + 1
        d["eta_seconds"] = self._estimate_eta(position)
        return d

    def _estimate_eta(self, position: int) -> Optional[float]:
        total = 0.0
        for ahead_id in self._pending[:position]:
            ahead_job = self._jobs.get(ahead_id)
            if ahead_job is None:
                continue
            avg = self.avg_duration(ahead_job.job_type)
            if avg is None:
                return None
            total += avg
        for running_job in self._jobs.values():
            if running_job.status == JobStatus.RUNNING:
                avg = self.avg_duration(running_job.job_type)
                if avg is None:
                    return None
                total += avg * (1 - running_job.progress)
        return total / self._max_concurrent

    def list_jobs(self, limit: int = 20, status: Optional[str] = None) -> List[Dict]:
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        if status:
            try:
                filter_status = JobStatus(status)
                jobs = [j for j in jobs if j.status == filter_status]
            except ValueError:
                pass
        return [self.job_info(j) for j in jobs[:limit]]

    async def cancel_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False
        was_pending = job.status == JobStatus.PENDING
        job.status = JobStatus.CANCELLED
        job.completed_at = time.time()
        if was_pending:
            async with self._cond:
                if job_id in self._pending:
                    self._pending.remove(job_id)
        task = self._job_tasks.get(job_id)
        if task is not None:
            task.cancel()
        await self._notify(job)
        if was_pending:
            await self._fire_listeners(job)
        return True

    async def set_priority(self, job_id: str, priority: int) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status != JobStatus.PENDING:
            return False
        async with self._cond:
            job.priority = priority
            if job_id in self._pending:
                self._pending.sort(key=self._pending_sort_key)
        await self._notify(job)
        return True

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        if job_id not in self._subscribers:
            self._subscribers[job_id] = []
        self._subscribers[job_id].append(q)
        job = self._jobs.get(job_id)
        if job is not None:
            q.put_nowait(job.to_dict())
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue):
        subs = self._subscribers.get(job_id, [])
        if q in subs:
            subs.remove(q)

    async def _notify(self, job: Job):
        msg = job.to_dict()
        for q in self._subscribers.get(job.id, []):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    def _cleanup_old_jobs(self):
        terminal = [
            j for j in self._jobs.values() if j.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
        ]
        if len(terminal) > self._max_history:
            terminal.sort(key=lambda j: j.completed_at or 0)
            for j in terminal[: len(terminal) - self._max_history]:
                self._jobs.pop(j.id, None)
                self._subscribers.pop(j.id, None)

    def stats(self) -> Dict:
        statuses: Dict[str, int] = {}
        for j in self._jobs.values():
            statuses[j.status.value] = statuses.get(j.status.value, 0) + 1
        return {
            "total": len(self._jobs),
            "queue_size": len(self._pending),
            "running": self._running_count,
            "by_status": statuses,
        }


_JOB_HANDLERS: Dict[str, Any] = {}


def register_job_handler(job_type: str):
    def decorator(func):
        _JOB_HANDLERS[job_type] = func
        return func

    return decorator


job_queue = JobQueue()
