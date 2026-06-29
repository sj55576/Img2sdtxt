"""tests/test_retry.py — retry_with_backoff のユニットテスト"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retry import retry_with_backoff


def test_no_retry_on_success():
    call_count = 0

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def always_succeed():
        nonlocal call_count
        call_count += 1
        return "ok"

    assert always_succeed() == "ok"
    assert call_count == 1


def test_retry_on_connection_error():
    call_count = 0

    @retry_with_backoff(max_retries=2, base_delay=0.01, max_delay=0.05)
    def fail_then_succeed():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("test")
        return "ok"

    assert fail_then_succeed() == "ok"
    assert call_count == 3


def test_retry_exhausted_raises():
    @retry_with_backoff(max_retries=2, base_delay=0.01, max_delay=0.05)
    def always_fail():
        raise TimeoutError("test")

    with pytest.raises(TimeoutError):
        always_fail()


def test_no_retry_on_non_retryable():
    call_count = 0

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def raise_value_error():
        nonlocal call_count
        call_count += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        raise_value_error()
    assert call_count == 1


@pytest.mark.asyncio
async def test_async_retry():
    call_count = 0

    @retry_with_backoff(max_retries=2, base_delay=0.01, max_delay=0.05)
    async def async_fail_then_succeed():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("test")
        return "async_ok"

    result = await async_fail_then_succeed()
    assert result == "async_ok"
    assert call_count == 2
