"""webhook.py — Outbound webhook notifications for job and batch completion events."""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set

import requests

import config
from job_queue import Job, JobStatus

logger = logging.getLogger("img2sdtxt.webhook")

# Maps a terminal job status to the webhook event name it triggers.
# Note: "job_cancelled" is intentionally absent from the default WEBHOOK_EVENTS
# so it stays off unless a user explicitly opts in.
_STATUS_EVENT_MAP = {
    JobStatus.COMPLETED: "job_completed",
    JobStatus.FAILED: "job_failed",
    JobStatus.CANCELLED: "job_cancelled",
}


def _parse_events(events: str) -> Set[str]:
    """Parse a comma-separated event list into a set, stripping whitespace and empties."""
    return {e.strip() for e in events.split(",") if e.strip()}


def _format_text(event: str, data: Dict[str, Any]) -> str:
    """Build a compact, human-readable one-line summary for chat-style webhooks."""
    if "job_id" in data:
        parts = [f"type={data.get('job_type')}", f"id={data.get('job_id')}"]
        duration = data.get("duration_seconds")
        if duration is not None:
            parts.append(f"duration={duration:.1f}s")
        if data.get("error"):
            parts.append(f"error={data['error']}")
        return f"[img2sdtxt] {event}: " + " ".join(parts)
    if "total" in data:
        return (
            f"[img2sdtxt] {event}: {data.get('succeeded', 0)} succeeded, "
            f"{data.get('skipped', 0)} skipped, {data.get('failed', 0)} failed "
            f"(total {data.get('total', 0)})"
        )
    return f"[img2sdtxt] {event}: {data}"


class WebhookNotifier:
    """Sends outbound HTTP notifications for job and batch lifecycle events."""

    def __init__(
        self,
        url: Optional[str] = None,
        events: Optional[str] = None,
        fmt: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.url = config.WEBHOOK_URL if url is None else url
        self.events = _parse_events(config.WEBHOOK_EVENTS if events is None else events)
        self.fmt = config.WEBHOOK_FORMAT if fmt is None else fmt
        self.timeout = config.WEBHOOK_TIMEOUT if timeout is None else timeout

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def _build_payload(self, event: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if self.fmt == "discord":
            return {"content": _format_text(event, data)}
        if self.fmt == "slack":
            return {"text": _format_text(event, data)}
        return {"event": event, "timestamp": time.time(), "data": data}

    def send(self, event: str, data: Dict[str, Any]) -> bool:
        """Send a webhook notification. Returns True on a 2xx response, False otherwise.

        Never raises — any error (disabled, unconfigured event, network failure,
        non-2xx response) is logged (where applicable) and results in False.
        """
        if not self.enabled or event not in self.events:
            return False

        payload = self._build_payload(event, data)
        try:
            response = requests.post(self.url, json=payload, timeout=self.timeout)
        except Exception as exc:
            logger.warning("Webhook delivery failed for event %s: %s", event, exc)
            return False

        if 200 <= response.status_code < 300:
            return True
        logger.warning("Webhook returned status %d for event %s", response.status_code, event)
        return False

    async def job_listener(self, job: Job) -> None:
        """Job-queue listener hook: maps a terminal job to a webhook event and sends it."""
        event = _STATUS_EVENT_MAP.get(job.status)
        if event is None or not self.enabled or event not in self.events:
            return

        data: Dict[str, Any] = {
            "job_id": job.id,
            "job_type": job.job_type,
            "status": job.status.value,
        }
        if job.error:
            data["error"] = job.error
        if job.started_at is not None and job.completed_at is not None:
            data["duration_seconds"] = job.completed_at - job.started_at

        await asyncio.to_thread(self.send, event, data)

    def notify_batch(self, results: List[Dict[str, Any]]) -> None:
        """Send a batch_completed notification summarizing a BatchProcessor.run() result."""
        if not self.enabled:
            return

        succeeded = sum(1 for r in results if r.get("status") == "success")
        skipped = sum(1 for r in results if r.get("skipped"))
        failed = sum(1 for r in results if r.get("status") == "error")
        data = {
            "total": len(results),
            "succeeded": succeeded,
            "skipped": skipped,
            "failed": failed,
        }
        self.send("batch_completed", data)


webhook_notifier = WebhookNotifier()
