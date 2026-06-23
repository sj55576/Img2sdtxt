"""Tests for job_queue module."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_queue import JobQueue, JobStatus, register_job_handler, _JOB_HANDLERS


@pytest.fixture
def queue():
    q = JobQueue(max_concurrent=1, max_history=10)
    return q


@pytest.fixture(autouse=True)
def register_test_handler():
    async def _echo(job, update_progress):
        await update_progress(0.5)
        return {"echo": job.params.get("msg", "hello")}

    _JOB_HANDLERS["test_echo"] = _echo
    yield
    _JOB_HANDLERS.pop("test_echo", None)


@pytest.mark.asyncio
async def test_submit_and_complete(queue):
    job = await queue.submit("test_echo", {"msg": "hi"})
    assert job.status == JobStatus.PENDING
    assert job.id

    await asyncio.sleep(0.3)

    completed = queue.get_job(job.id)
    assert completed is not None
    assert completed.status == JobStatus.COMPLETED
    assert completed.result == {"echo": "hi"}
    assert completed.progress == 1.0


@pytest.mark.asyncio
async def test_list_jobs(queue):
    j1 = await queue.submit("test_echo", {"msg": "a"})
    j2 = await queue.submit("test_echo", {"msg": "b"})

    await asyncio.sleep(0.5)

    jobs = queue.list_jobs(limit=10)
    ids = [j["id"] for j in jobs]
    assert j1.id in ids
    assert j2.id in ids


@pytest.mark.asyncio
async def test_cancel_pending_job(queue):
    gate = asyncio.Event()

    async def _slow(job, update_progress):
        await gate.wait()
        return {}

    _JOB_HANDLERS["test_slow"] = _slow

    j1 = await queue.submit("test_slow", {})
    j2 = await queue.submit("test_slow", {})

    await asyncio.sleep(0.1)
    cancelled = await queue.cancel_job(j2.id)
    assert cancelled

    j2_state = queue.get_job(j2.id)
    assert j2_state.status == JobStatus.CANCELLED

    gate.set()
    await asyncio.sleep(0.1)
    _JOB_HANDLERS.pop("test_slow", None)


@pytest.mark.asyncio
async def test_cancel_running_job_stays_cancelled(queue):
    gate = asyncio.Event()
    started = asyncio.Event()

    async def _slow_running(job, update_progress):
        started.set()
        await gate.wait()
        return {"should_not": "complete"}

    _JOB_HANDLERS["test_slow_running"] = _slow_running

    job = await queue.submit("test_slow_running", {})
    await asyncio.wait_for(started.wait(), timeout=1.0)

    cancelled = await queue.cancel_job(job.id)
    assert cancelled

    gate.set()
    await asyncio.sleep(0.1)

    result = queue.get_job(job.id)
    assert result.status == JobStatus.CANCELLED
    assert result.result is None

    _JOB_HANDLERS.pop("test_slow_running", None)


@pytest.mark.asyncio
async def test_max_concurrent_allows_parallel_jobs():
    queue = JobQueue(max_concurrent=2, max_history=10)
    gate = asyncio.Event()
    started = 0
    started_event = asyncio.Event()

    async def _parallel(job, update_progress):
        nonlocal started
        started += 1
        if started == 2:
            started_event.set()
        await gate.wait()
        return {"ok": True}

    _JOB_HANDLERS["test_parallel"] = _parallel

    j1 = await queue.submit("test_parallel", {})
    j2 = await queue.submit("test_parallel", {})

    await asyncio.wait_for(started_event.wait(), timeout=1.0)
    stats = queue.stats()
    assert stats["running"] == 2

    gate.set()
    await asyncio.sleep(0.1)

    assert queue.get_job(j1.id).status == JobStatus.COMPLETED
    assert queue.get_job(j2.id).status == JobStatus.COMPLETED

    _JOB_HANDLERS.pop("test_parallel", None)


@pytest.mark.asyncio
async def test_failed_job(queue):
    async def _fail(job, update_progress):
        raise ValueError("test error")

    _JOB_HANDLERS["test_fail"] = _fail

    job = await queue.submit("test_fail", {})
    await asyncio.sleep(0.3)

    result = queue.get_job(job.id)
    assert result.status == JobStatus.FAILED
    assert "test error" in result.error

    _JOB_HANDLERS.pop("test_fail", None)


@pytest.mark.asyncio
async def test_stats(queue):
    await queue.submit("test_echo", {})
    await asyncio.sleep(0.3)

    stats = queue.stats()
    assert stats["total"] >= 1
    assert "by_status" in stats


@pytest.mark.asyncio
async def test_subscribe_receives_updates(queue):
    job = await queue.submit("test_echo", {"msg": "sub"})
    sub = await queue.subscribe(job.id)

    await asyncio.sleep(0.5)

    messages = []
    while not sub.empty():
        messages.append(await sub.get())

    assert len(messages) > 0
    assert any(m.get("status") == "completed" for m in messages)

    queue.unsubscribe(job.id, sub)


@pytest.mark.asyncio
async def test_get_nonexistent_job(queue):
    assert queue.get_job("nonexistent") is None
