"""LLM プロバイダーの死活監視を行うバックグラウンドスレッド。"""

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict

from llm_provider import LLMProvider

logger = logging.getLogger("img2sdtxt.health_monitor")

STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_UNAVAILABLE = "unavailable"

# is_available() の応答時間がこの閾値(秒)を超えたら "degraded" とみなす
DEGRADED_THRESHOLD_SECONDS = 3.0


@dataclass
class HealthStatus:
    status: str
    last_check: datetime
    response_time_ms: float


class HealthMonitor:
    """登録されたプロバイダーを定期的に is_available() でチェックし、状態を保持する。"""

    def __init__(self, providers: Dict[str, LLMProvider], check_interval: int = 60):
        self.providers = providers
        self.check_interval = check_interval
        self._status: Dict[str, HealthStatus] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def _check_provider(self, name: str, provider: LLMProvider) -> HealthStatus:
        t0 = time.monotonic()
        try:
            available = provider.is_available()
        except Exception as e:
            logger.warning("Health check for provider %s raised: %s", name, e)
            available = False
        elapsed_ms = (time.monotonic() - t0) * 1000

        if not available:
            status = STATUS_UNAVAILABLE
        elif elapsed_ms > DEGRADED_THRESHOLD_SECONDS * 1000:
            status = STATUS_DEGRADED
        else:
            status = STATUS_HEALTHY

        return HealthStatus(
            status=status,
            last_check=datetime.now(timezone.utc),
            response_time_ms=elapsed_ms,
        )

    def check_all(self) -> None:
        """全プロバイダーを即座にチェックし、状態を更新する。"""
        for name, provider in self.providers.items():
            result = self._check_provider(name, provider)
            with self._lock:
                self._status[name] = result

    def get_status(self) -> Dict[str, HealthStatus]:
        with self._lock:
            return dict(self._status)

    def _run(self) -> None:
        # 起動直後に一度チェックしてから、以降は check_interval 間隔で繰り返す
        self.check_all()
        while not self._stop_event.wait(self.check_interval):
            self.check_all()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="health-monitor", daemon=True)
        self._thread.start()
        logger.info("HealthMonitor started (interval=%ds, providers=%s)", self.check_interval, list(self.providers))

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info("HealthMonitor stopped")
