"""Tests for job_queue module."""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_queue import _JOB_HANDLERS, JobQueue, JobStatus


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

    await queue.submit("test_slow", {})
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


@pytest.mark.asyncio
async def test_priority_field_defaults_and_in_dict(queue):
    job = await queue.submit("test_echo", {"msg": "p"})
    assert job.priority == 0
    assert job.to_dict()["priority"] == 0
    await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_higher_priority_job_runs_before_lower_priority(queue):
    order = []
    started = asyncio.Event()
    blocker_gate = asyncio.Event()

    async def _blocker(job, update_progress):
        started.set()
        await blocker_gate.wait()
        return {}

    async def _track(job, update_progress):
        order.append(job.id)
        return {}

    _JOB_HANDLERS["test_blocker"] = _blocker
    _JOB_HANDLERS["test_track"] = _track

    await queue.submit("test_blocker", {})  # occupies the single worker
    await asyncio.wait_for(started.wait(), timeout=1.0)

    low = await queue.submit("test_track", {}, priority=0)
    high = await queue.submit("test_track", {}, priority=5)

    assert queue.stats()["queue_size"] == 2

    blocker_gate.set()
    await asyncio.sleep(0.2)

    assert order == [high.id, low.id]

    _JOB_HANDLERS.pop("test_blocker", None)
    _JOB_HANDLERS.pop("test_track", None)


@pytest.mark.asyncio
async def test_equal_priority_is_fifo(queue):
    order = []
    started = asyncio.Event()
    blocker_gate = asyncio.Event()

    async def _blocker(job, update_progress):
        started.set()
        await blocker_gate.wait()
        return {}

    async def _track(job, update_progress):
        order.append(job.id)
        return {}

    _JOB_HANDLERS["test_blocker"] = _blocker
    _JOB_HANDLERS["test_track"] = _track

    await queue.submit("test_blocker", {})
    await asyncio.wait_for(started.wait(), timeout=1.0)

    first = await queue.submit("test_track", {})
    second = await queue.submit("test_track", {})

    blocker_gate.set()
    await asyncio.sleep(0.2)

    assert order == [first.id, second.id]

    _JOB_HANDLERS.pop("test_blocker", None)
    _JOB_HANDLERS.pop("test_track", None)


@pytest.mark.asyncio
async def test_set_priority_repositions_pending_job(queue):
    order = []
    started = asyncio.Event()
    blocker_gate = asyncio.Event()

    async def _blocker(job, update_progress):
        started.set()
        await blocker_gate.wait()
        return {}

    async def _track(job, update_progress):
        order.append(job.id)
        return {}

    _JOB_HANDLERS["test_blocker"] = _blocker
    _JOB_HANDLERS["test_track"] = _track

    await queue.submit("test_blocker", {})
    await asyncio.wait_for(started.wait(), timeout=1.0)

    a = await queue.submit("test_track", {})
    b = await queue.submit("test_track", {})

    assert await queue.set_priority(b.id, 10) is True

    blocker_gate.set()
    await asyncio.sleep(0.2)

    assert order == [b.id, a.id]

    _JOB_HANDLERS.pop("test_blocker", None)
    _JOB_HANDLERS.pop("test_track", None)


@pytest.mark.asyncio
async def test_set_priority_false_for_running_finished_and_unknown(queue):
    started = asyncio.Event()
    gate = asyncio.Event()

    async def _slow(job, update_progress):
        started.set()
        await gate.wait()
        return {}

    _JOB_HANDLERS["test_slow_prio"] = _slow

    job = await queue.submit("test_slow_prio", {})
    await asyncio.wait_for(started.wait(), timeout=1.0)

    assert await queue.set_priority(job.id, 5) is False  # running

    gate.set()
    await asyncio.sleep(0.1)
    assert await queue.set_priority(job.id, 5) is False  # already finished

    assert await queue.set_priority("nonexistent", 5) is False  # unknown

    _JOB_HANDLERS.pop("test_slow_prio", None)


@pytest.mark.asyncio
async def test_queue_position_and_eta(queue):
    block_event = asyncio.Event()

    async def _blocking(job, update_progress):
        await block_event.wait()
        return {}

    _JOB_HANDLERS["test_eta_block"] = _blocking

    running = await queue.submit("test_eta_block", {})
    pending = await queue.submit("test_eta_block", {})
    await asyncio.sleep(0.05)

    info = queue.job_info(queue.get_job(pending.id))
    assert info["queue_position"] == 1
    assert info["eta_seconds"] is None  # no duration history yet

    running_info = queue.job_info(queue.get_job(running.id))
    assert "queue_position" not in running_info
    assert "eta_seconds" not in running_info

    block_event.set()
    await asyncio.sleep(0.2)
    assert queue.get_job(running.id).status == JobStatus.COMPLETED
    assert queue.get_job(pending.id).status == JobStatus.COMPLETED

    # Duration history now exists for this job type; a new pending job should get a float ETA.
    block_event.clear()
    running2 = await queue.submit("test_eta_block", {})
    pending2 = await queue.submit("test_eta_block", {})
    await asyncio.sleep(0.05)

    info2 = queue.job_info(queue.get_job(pending2.id))
    assert info2["queue_position"] == 1
    assert isinstance(info2["eta_seconds"], float)

    block_event.set()
    await asyncio.sleep(0.1)
    assert queue.get_job(running2.id).status == JobStatus.COMPLETED
    assert queue.get_job(pending2.id).status == JobStatus.COMPLETED

    _JOB_HANDLERS.pop("test_eta_block", None)


@pytest.mark.asyncio
async def test_cancel_pending_job_drops_queue_size(queue):
    gate = asyncio.Event()

    async def _slow(job, update_progress):
        await gate.wait()
        return {}

    _JOB_HANDLERS["test_cancel_slow"] = _slow

    await queue.submit("test_cancel_slow", {})
    j2 = await queue.submit("test_cancel_slow", {})

    await asyncio.sleep(0.05)
    assert queue.stats()["queue_size"] == 1

    cancelled = await queue.cancel_job(j2.id)
    assert cancelled
    assert queue.stats()["queue_size"] == 0

    gate.set()
    await asyncio.sleep(0.1)
    _JOB_HANDLERS.pop("test_cancel_slow", None)


@pytest.mark.asyncio
async def test_listener_fires_on_completed_and_failed(queue):
    seen = []

    def sync_listener(job):
        seen.append((job.id, job.status))

    async def failing_listener(job):
        raise RuntimeError("listener boom")

    async_calls = []

    async def async_listener(job):
        await asyncio.sleep(0)
        async_calls.append(job.id)

    queue.add_listener(sync_listener)
    queue.add_listener(failing_listener)
    queue.add_listener(async_listener)

    async def _fail(job, update_progress):
        raise ValueError("bad")

    _JOB_HANDLERS["test_listener_fail"] = _fail

    ok = await queue.submit("test_echo", {"msg": "x"})
    await asyncio.sleep(0.2)
    bad = await queue.submit("test_listener_fail", {})
    await asyncio.sleep(0.2)

    assert (ok.id, JobStatus.COMPLETED) in seen
    assert (bad.id, JobStatus.FAILED) in seen
    assert ok.id in async_calls
    assert bad.id in async_calls

    # A raising listener must not affect job outcomes.
    assert queue.get_job(ok.id).status == JobStatus.COMPLETED
    assert queue.get_job(bad.id).status == JobStatus.FAILED

    _JOB_HANDLERS.pop("test_listener_fail", None)


@pytest.mark.asyncio
async def test_listener_fires_on_cancel_of_pending_job(queue):
    seen = []
    queue.add_listener(lambda job: seen.append((job.id, job.status)))

    gate = asyncio.Event()

    async def _slow(job, update_progress):
        await gate.wait()
        return {}

    _JOB_HANDLERS["test_listener_cancel_slow"] = _slow

    await queue.submit("test_listener_cancel_slow", {})
    j2 = await queue.submit("test_listener_cancel_slow", {})

    await asyncio.sleep(0.05)
    assert await queue.cancel_job(j2.id) is True
    assert (j2.id, JobStatus.CANCELLED) in seen

    gate.set()
    await asyncio.sleep(0.1)
    _JOB_HANDLERS.pop("test_listener_cancel_slow", None)
