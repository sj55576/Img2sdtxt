"""
IP-based sliding window rate limiter middleware for FastAPI.

Two tiers:
  - generation: paths starting with /api/sd/generate, /api/sd/img2img,
                /api/sd/inpaint, /api/generate-prompts  → RATE_LIMIT_GENERATION rpm
  - api:        all other /api/* paths                  → RATE_LIMIT_API rpm
  - other:      static files, non-API paths             → no limit
"""

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

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

DB_PATH = Path(__file__).parent / "data" / "rate_limit.db"


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
    Sliding-window rate limiter backed by SQLite.

    Table: rate_limit_entries(ip TEXT, tier TEXT, timestamp REAL)
    """

    def __init__(self, app):
        super().__init__(app)
        self._lock = threading.Lock()
        self._last_cleanup = time.time()
        DB_PATH.parent.mkdir(exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limit_entries (
                    ip TEXT NOT NULL,
                    tier TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ip_tier ON rate_limit_entries (ip, tier)")
            conn.commit()

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
        limit = config.RATE_LIMIT_GENERATION if tier == "generation" else config.RATE_LIMIT_API

        allowed, retry_after = self._check_and_record(ip, tier, limit)

        if not allowed:
            logger.warning(
                "Rate limit hit: ip=%s tier=%s path=%s retry_after=%ds",
                ip,
                tier,
                request.url.path,
                retry_after,
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

            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "DELETE FROM rate_limit_entries WHERE ip = ? AND tier = ? AND timestamp <= ?",
                    (ip, tier, window_start),
                )

                count = conn.execute(
                    "SELECT COUNT(*) FROM rate_limit_entries WHERE ip = ? AND tier = ?",
                    (ip, tier),
                ).fetchone()[0]

                if count >= limit:
                    oldest = conn.execute(
                        "SELECT MIN(timestamp) FROM rate_limit_entries WHERE ip = ? AND tier = ?",
                        (ip, tier),
                    ).fetchone()[0]
                    retry_after = int(oldest + WINDOW_SECONDS - now) + 1
                    return False, max(retry_after, 1)

                conn.execute(
                    "INSERT INTO rate_limit_entries (ip, tier, timestamp) VALUES (?, ?, ?)",
                    (ip, tier, now),
                )
                conn.commit()
                return True, 0

    # ------------------------------------------------------------------ #
    # Periodic cleanup
    # ------------------------------------------------------------------ #

    def _maybe_cleanup(self, now: float) -> None:
        """Remove stale entries. Must be called while holding self._lock."""
        if now - self._last_cleanup < CLEANUP_INTERVAL:
            return

        window_start = now - WINDOW_SECONDS
        with sqlite3.connect(DB_PATH) as conn:
            result = conn.execute(
                "DELETE FROM rate_limit_entries WHERE timestamp <= ?",
                (window_start,),
            )
            conn.commit()

        if result.rowcount:
            logger.debug("Rate-limit cleanup: removed %d stale entries", result.rowcount)

        self._last_cleanup = now
