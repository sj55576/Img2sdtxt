"""Tests for webhook module."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from job_queue import _JOB_HANDLERS, Job, JobQueue, JobStatus
from webhook import WebhookNotifier


def _make_response(status_code: int = 200):
    resp = MagicMock()
    resp.status_code = status_code
    return resp


class TestSendDisabledOrFiltered:
    def test_disabled_when_url_empty_does_not_call_requests(self):
        notifier = WebhookNotifier(url="", events="job_completed", fmt="generic", timeout=5)
        with patch("webhook.requests.post") as mock_post:
            result = notifier.send("job_completed", {"job_id": "abc"})
        assert result is False
        mock_post.assert_not_called()

    def test_event_not_in_configured_events_is_not_sent(self):
        notifier = WebhookNotifier(url="http://example.com/hook", events="job_completed", fmt="generic", timeout=5)
        with patch("webhook.requests.post") as mock_post:
            result = notifier.send("job_failed", {"job_id": "abc"})
        assert result is False
        mock_post.assert_not_called()


class TestPayloadFormats:
    def test_generic_payload_shape(self):
        notifier = WebhookNotifier(url="http://example.com/hook", events="job_completed", fmt="generic", timeout=7)
        with patch("webhook.requests.post", return_value=_make_response(200)) as mock_post:
            result = notifier.send("job_completed", {"job_id": "abc123"})

        assert result is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://example.com/hook"
        assert kwargs["timeout"] == 7
        payload = kwargs["json"]
        assert payload["event"] == "job_completed"
        assert isinstance(payload["timestamp"], float)
        assert payload["data"] == {"job_id": "abc123"}

    def test_discord_format_posts_content_with_job_id(self):
        notifier = WebhookNotifier(url="http://example.com/hook", events="job_completed", fmt="discord", timeout=5)
        with patch("webhook.requests.post", return_value=_make_response(200)) as mock_post:
            notifier.send("job_completed", {"job_id": "abc123", "job_type": "txt2img"})

        payload = mock_post.call_args.kwargs["json"]
        assert "content" in payload
        assert "abc123" in payload["content"]

    def test_slack_format_posts_text_with_job_id(self):
        notifier = WebhookNotifier(url="http://example.com/hook", events="job_completed", fmt="slack", timeout=5)
        with patch("webhook.requests.post", return_value=_make_response(200)) as mock_post:
            notifier.send("job_completed", {"job_id": "abc123", "job_type": "txt2img"})

        payload = mock_post.call_args.kwargs["json"]
        assert "text" in payload
        assert "abc123" in payload["text"]


class TestSendErrorHandling:
    def test_requests_post_raising_returns_false_without_exception(self):
        notifier = WebhookNotifier(url="http://example.com/hook", events="job_completed", fmt="generic", timeout=5)
        with patch("webhook.requests.post", side_effect=ConnectionError("boom")):
            result = notifier.send("job_completed", {"job_id": "abc"})
        assert result is False

    def test_non_2xx_response_returns_false(self):
        notifier = WebhookNotifier(url="http://example.com/hook", events="job_completed", fmt="generic", timeout=5)
        with patch("webhook.requests.post", return_value=_make_response(500)):
            result = notifier.send("job_completed", {"job_id": "abc"})
        assert result is False


class TestJobListener:
    @pytest.mark.asyncio
    async def test_completed_job_sends_job_completed_with_duration(self):
        notifier = WebhookNotifier(
            url="http://example.com/hook", events="job_completed,job_failed", fmt="generic", timeout=5
        )
        job = Job(id="jid1", job_type="txt2img", params={})
        job.status = JobStatus.COMPLETED
        job.started_at = 100.0
        job.completed_at = 112.3

        with patch("webhook.requests.post", return_value=_make_response(200)) as mock_post:
            await notifier.job_listener(job)

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["event"] == "job_completed"
        assert payload["data"]["job_id"] == "jid1"
        assert payload["data"]["job_type"] == "txt2img"
        assert payload["data"]["duration_seconds"] == pytest.approx(12.3)

    @pytest.mark.asyncio
    async def test_failed_job_sends_job_failed_with_error(self):
        notifier = WebhookNotifier(
            url="http://example.com/hook", events="job_completed,job_failed", fmt="generic", timeout=5
        )
        job = Job(id="jid2", job_type="txt2img", params={})
        job.status = JobStatus.FAILED
        job.error = "boom"
        job.started_at = 100.0
        job.completed_at = 101.0

        with patch("webhook.requests.post", return_value=_make_response(200)) as mock_post:
            await notifier.job_listener(job)

        payload = mock_post.call_args.kwargs["json"]
        assert payload["event"] == "job_failed"
        assert payload["data"]["error"] == "boom"

    @pytest.mark.asyncio
    async def test_cancelled_job_not_sent_with_default_events(self):
        notifier = WebhookNotifier(url="http://example.com/hook", timeout=5)  # default events from config
        job = Job(id="jid3", job_type="txt2img", params={})
        job.status = JobStatus.CANCELLED
        job.started_at = 100.0
        job.completed_at = 101.0

        with patch("webhook.requests.post") as mock_post:
            await notifier.job_listener(job)

        mock_post.assert_not_called()


class TestNotifyBatch:
    def test_mixed_results_produce_correct_counts(self):
        notifier = WebhookNotifier(url="http://example.com/hook", events="batch_completed", fmt="generic", timeout=5)
        results = [
            {"status": "success"},
            {"status": "success"},
            {"skipped": True},
            {"status": "error"},
        ]

        with patch("webhook.requests.post", return_value=_make_response(200)) as mock_post:
            notifier.notify_batch(results)

        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        assert payload["event"] == "batch_completed"
        assert payload["data"] == {"total": 4, "succeeded": 2, "skipped": 1, "failed": 1}

    def test_disabled_notifier_is_a_noop(self):
        notifier = WebhookNotifier(url="", events="batch_completed", fmt="generic", timeout=5)
        with patch("webhook.requests.post") as mock_post:
            notifier.notify_batch([{"status": "success"}])
        mock_post.assert_not_called()


class TestIntegrationWithJobQueue:
    @pytest.mark.asyncio
    async def test_registered_listener_triggers_webhook_on_completion(self):
        queue = JobQueue(max_concurrent=1, max_history=10)
        notifier = WebhookNotifier(
            url="http://example.com/hook", events="job_completed,job_failed", fmt="generic", timeout=5
        )
        queue.add_listener(notifier.job_listener)

        async def _echo(job, update_progress):
            await update_progress(0.5)
            return {"echo": job.params.get("msg", "hello")}

        _JOB_HANDLERS["test_webhook_echo"] = _echo
        try:
            with patch("webhook.requests.post", return_value=_make_response(200)) as mock_post:
                job = await queue.submit("test_webhook_echo", {"msg": "hi"})
                for _ in range(20):
                    if queue.get_job(job.id).status == JobStatus.COMPLETED:
                        break
                    await asyncio.sleep(0.05)

            assert queue.get_job(job.id).status == JobStatus.COMPLETED
            mock_post.assert_called_once()
            payload = mock_post.call_args.kwargs["json"]
            assert payload["event"] == "job_completed"
            assert payload["data"]["job_id"] == job.id
        finally:
            _JOB_HANDLERS.pop("test_webhook_echo", None)
