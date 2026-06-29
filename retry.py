import asyncio
import functools
import logging
import random
import time
from typing import Tuple, Type

import requests

logger = logging.getLogger("img2sdtxt.retry")

DEFAULT_RETRYABLE = (
    ConnectionError,
    TimeoutError,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: Tuple[Type[BaseException], ...] = DEFAULT_RETRYABLE,
):
    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                for attempt in range(max_retries + 1):
                    try:
                        return await func(*args, **kwargs)
                    except retryable_exceptions as e:
                        if attempt == max_retries:
                            raise
                        delay = min(base_delay * (2**attempt) + random.uniform(0, 1), max_delay)
                        logger.warning(
                            "Retry %d/%d for %s after %.2fs (reason: %s)",
                            attempt + 1,
                            max_retries,
                            func.__qualname__,
                            delay,
                            e,
                        )
                        await asyncio.sleep(delay)

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                for attempt in range(max_retries + 1):
                    try:
                        return func(*args, **kwargs)
                    except retryable_exceptions as e:
                        if attempt == max_retries:
                            raise
                        delay = min(base_delay * (2**attempt) + random.uniform(0, 1), max_delay)
                        logger.warning(
                            "Retry %d/%d for %s after %.2fs (reason: %s)",
                            attempt + 1,
                            max_retries,
                            func.__qualname__,
                            delay,
                            e,
                        )
                        time.sleep(delay)

            return sync_wrapper

    return decorator
