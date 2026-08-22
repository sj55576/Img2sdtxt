"""tests/test_jobs.py — wildcard_batch job handler and submission validation"""

import base64
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import routes.jobs as jobs_routes  # noqa: E402
from job_queue import JobStatus  # noqa: E402


def _tiny_png_b64(color=(255, 0, 0), size=(8, 8)) -> str:
    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


class FakeJob:
    def __init__(self, params, status=JobStatus.RUNNING):
        self.id = "fake-job"
        self.params = params
        self.status = status


@pytest.mark.asyncio
async def test_handle_wildcard_batch_generates_one_image_per_combination():
    tiny_b64 = _tiny_png_b64()
    calls = []

    def fake_txt2img(**kwargs):
        calls.append(kwargs)
        return [tiny_b64]

    fake_save_images = MagicMock(
        side_effect=lambda **kwargs: [{"filename": f"{kwargs['positive']}.png", "path": "/tmp/x.png", "index": 0}]
    )

    params = {
        "positive": "{red|blue} hair",
        "negative": "blurry",
        "width": 64,
        "height": 64,
        "steps": 20,
        "cfg_scale": 7.0,
        "sampler": "Euler a",
        "seed": -1,
        "model": "",
        "loras": "",
        "max_combinations": 36,
    }
    job = FakeJob(params)
    progress_values = []

    async def update_progress(v):
        progress_values.append(v)

    with (
        patch.object(jobs_routes.sd_client, "txt2img", side_effect=fake_txt2img),
        patch.object(jobs_routes.sd_client, "save_images", fake_save_images),
    ):
        result = await jobs_routes.handle_wildcard_batch(job, update_progress)

    assert len(calls) == 2  # {red|blue} -> 2 combinations
    assert all(c["batch_size"] == 1 for c in calls)
    assert sorted(c["positive"] for c in calls) == ["blue hair", "red hair"]

    assert result["combination_count"] == 2
    assert result["count"] == 2
    assert sorted(result["expanded_prompts"]) == ["blue hair", "red hair"]
    assert len(result["saved_files"]) == 2

    # Every save_images call recorded the original template, not the expansion.
    for save_call in fake_save_images.call_args_list:
        assert save_call.kwargs["template"] == "{red|blue} hair"

    assert progress_values[-1] == 1.0
    assert all(0.0 <= v <= 1.0 for v in progress_values)


@pytest.mark.asyncio
async def test_handle_wildcard_batch_stops_when_job_is_cancelled():
    tiny_b64 = _tiny_png_b64()
    calls = []

    def fake_txt2img(**kwargs):
        calls.append(kwargs)
        return [tiny_b64]

    params = {
        "positive": "{a|b|c}",
        "negative": "",
        "max_combinations": 36,
    }
    job = FakeJob(params, status=JobStatus.CANCELLED)

    async def update_progress(_v):
        pass

    with (
        patch.object(jobs_routes.sd_client, "txt2img", side_effect=fake_txt2img),
        patch.object(jobs_routes.sd_client, "save_images", MagicMock(return_value=[])),
    ):
        result = await jobs_routes.handle_wildcard_batch(job, update_progress)

    assert calls == []
    assert result["count"] == 0


@pytest.mark.asyncio
async def test_handle_wildcard_batch_raises_when_over_the_combination_cap():
    params = {"positive": "{a|b|c|d|e} {1|2|3|4|5}", "max_combinations": 10}
    job = FakeJob(params)

    async def update_progress(_v):
        pass

    with pytest.raises(ValueError):
        await jobs_routes.handle_wildcard_batch(job, update_progress)
