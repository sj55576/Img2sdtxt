"""
IP-based sliding window rate limiter middleware for FastAPI.

Two tiers:
  - generation: paths starting with /api/sd/generate, /api/sd/img2img,
                /api/sd/inpaint, /api/generate-prompts  → RATE_LIMIT_GENERATION rpm
  - api:        all other /api/* paths                  → RATE_LIMIT_API rpm
  - other:      static files, non-API paths             → no limit
"""

import time
import threading
import logging
from typing import Dict, List, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

import config

logger = logging.getLogger("img2sdtxt.rate_limit")

WINDOW_SECONDS = 60  # sliding window duration
CLEANUP_INTERVAL = 60  # seconds between background cleanup passes

GENERATION_PREFIXES = (
    "/api/sd/generate",
    "/api/sd/img2img",
    "/api/sd/inpaint",
    "/api/generate-prompts",
)



def _classify_path(path: str) -> Optional[str]:
    """
    Return the rate-limit tier for a request path.
    Returns "generation", "api", or None (no limit).
    """
    for prefix in GENERATION_PREFIXES:
        if path.startswith(prefix):
            return "generation"
    if path.startswith("/api/"):
        return "api"
    return None


def _get_client_ip(request: Request) -> str:
    """Return the real client IP, honouring X-Forwarded-For."""
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiter.

    Internal state:
        _store: {ip: {"generation": [t1, t2, …], "api": [t1, t2, …]}}
    """

    def __init__(self, app):
        super().__init__(app)
        self._store: Dict[str, Dict[str, List[float]]] = {}
        self._lock = threading.Lock()
        self._last_cleanup = time.time()

    # ------------------------------------------------------------------ #
    # Middleware entry point
    # ------------------------------------------------------------------ #

    async def dispatch(self, request: Request, call_next):
        if not config.RATE_LIMIT_ENABLED:
            return await call_next(request)

        tier = _classify_path(request.url.path)
        if tier is None:
            return await call_next(request)

        ip = _get_client_ip(request)
        limit = (
            config.RATE_LIMIT_GENERATION if tier == "generation" else config.RATE_LIMIT_API
        )

        allowed, retry_after = self._check_and_record(ip, tier, limit)

        if not allowed:
            logger.warning(
                "Rate limit hit: ip=%s tier=%s path=%s retry_after=%ds",
                ip, tier, request.url.path, retry_after,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded. Try again in {retry_after} seconds."},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)

    # ------------------------------------------------------------------ #
    # Core rate-limit logic (thread-safe)
    # ------------------------------------------------------------------ #

    def _check_and_record(self, ip: str, tier: str, limit: int):
        """
        Returns (allowed: bool, retry_after: int).
        Prunes expired timestamps, records the current request if allowed.
        """
        now = time.time()
        window_start = now - WINDOW_SECONDS

        with self._lock:
            self._maybe_cleanup(now)

            ip_data = self._store.setdefault(ip, {"generation": [], "api": []})
            timestamps: List[float] = ip_data[tier]

            # Drop timestamps outside the sliding window
            pruned = [t for t in timestamps if t > window_start]

            if len(pruned) >= limit:
                # Oldest request in window determines when a slot frees up
                oldest = pruned[0]
                retry_after = int(oldest + WINDOW_SECONDS - now) + 1
                ip_data[tier] = pruned
                return False, max(retry_after, 1)

            pruned.append(now)
            ip_data[tier] = pruned
            return True, 0

    # ------------------------------------------------------------------ #
    # Periodic cleanup
    # ------------------------------------------------------------------ #

    def _maybe_cleanup(self, now: float) -> None:
        """Remove stale IP entries. Must be called while holding self._lock."""
        if now - self._last_cleanup < CLEANUP_INTERVAL:
            return

        window_start = now - WINDOW_SECONDS
        stale_ips = [
            ip
            for ip, data in self._store.items()
            if not any(t > window_start for ts in data.values() for t in ts)
        ]
        for ip in stale_ips:
            del self._store[ip]

        if stale_ips:
            logger.debug("Rate-limit cleanup: removed %d stale IP entries", len(stale_ips))

        self._last_cleanup = now
