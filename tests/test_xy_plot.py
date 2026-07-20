"""tests/test_xy_plot.py — XY Plot 機能 (axis parsing, grid composition, job handler, submit validation) のテスト"""

import base64
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import xy_plot  # noqa: E402
from job_queue import JobStatus  # noqa: E402


def _tiny_png_b64(color=(255, 0, 0), size=(8, 8)) -> str:
    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _solid_image(color, size=(10, 10)) -> Image.Image:
    return Image.new("RGB", size, color=color)


class FakeJob:
    def __init__(self, params, status=JobStatus.RUNNING):
        self.id = "fake-job"
        self.params = params
        self.status = status


# ------------------------------------------------------------------ #
# parse_axis_values
# ------------------------------------------------------------------ #


def test_parse_axis_values_steps_valid():
    assert xy_plot.parse_axis_values("steps", ["10", "20", "30"]) == [10, 20, 30]


def test_parse_axis_values_steps_out_of_range():
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("steps", ["0"])
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("steps", ["151"])


def test_parse_axis_values_steps_non_numeric():
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("steps", ["abc"])


def test_parse_axis_values_cfg_scale_valid():
    assert xy_plot.parse_axis_values("cfg_scale", ["1.0", "7.5", "30"]) == [1.0, 7.5, 30.0]


def test_parse_axis_values_cfg_scale_out_of_range():
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("cfg_scale", ["0.5"])
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("cfg_scale", ["30.1"])


def test_parse_axis_values_sampler_valid():
    assert xy_plot.parse_axis_values("sampler", ["Euler a", "DDIM"]) == ["Euler a", "DDIM"]


def test_parse_axis_values_sampler_empty_string_invalid():
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("sampler", ["Euler a", "  "])


def test_parse_axis_values_seed_valid():
    assert xy_plot.parse_axis_values("seed", ["-1", "42"]) == [-1, 42]


def test_parse_axis_values_seed_non_numeric():
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("seed", ["not_a_seed"])


def test_parse_axis_values_model_valid():
    assert xy_plot.parse_axis_values("model", ["modelA.safetensors", "modelB.ckpt"]) == [
        "modelA.safetensors",
        "modelB.ckpt",
    ]


def test_parse_axis_values_model_empty_string_invalid():
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("model", [""])


def test_parse_axis_values_prompt_sr_valid():
    assert xy_plot.parse_axis_values("prompt_sr", ["cat", "dog", "fox"]) == ["cat", "dog", "fox"]


def test_parse_axis_values_prompt_sr_min_length():
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("prompt_sr", ["cat"])


def test_parse_axis_values_none_returns_empty():
    assert xy_plot.parse_axis_values("none", []) == []
    assert xy_plot.parse_axis_values("none", ["ignored"]) == []


def test_parse_axis_values_empty_list_raises():
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("steps", [])


def test_parse_axis_values_unsupported_type_raises():
    with pytest.raises(ValueError):
        xy_plot.parse_axis_values("bogus", ["1"])


# ------------------------------------------------------------------ #
# validate_cell_count
# ------------------------------------------------------------------ #


def test_validate_cell_count_at_limit_ok():
    x_values = list(range(6))
    y_values = list(range(6))
    cols, rows = xy_plot.validate_cell_count(x_values, y_values, max_cells=36)
    assert cols == 6
    assert rows == 6


def test_validate_cell_count_over_limit_raises():
    x_values = list(range(7))
    y_values = list(range(6))
    with pytest.raises(ValueError):
        xy_plot.validate_cell_count(x_values, y_values, max_cells=36)


def test_validate_cell_count_single_axis():
    x_values = list(range(5))
    cols, rows = xy_plot.validate_cell_count(x_values, [], max_cells=36)
    assert cols == 5
    assert rows == 1


def test_validate_cell_count_empty_x_raises():
    with pytest.raises(ValueError):
        xy_plot.validate_cell_count([], [], max_cells=36)


# ------------------------------------------------------------------ #
# compose_grid
# ------------------------------------------------------------------ #


def test_compose_grid_size_with_legend():
    images = [_solid_image((255, 0, 0)) for _ in range(6)]  # 2 rows x 3 cols
    grid = xy_plot.compose_grid(images, x_labels=["a", "b", "c"], y_labels=["y1", "y2"], draw_legend=True)
    assert grid.size == (120 + 10 * 3, 40 + 10 * 2)


def test_compose_grid_size_without_legend():
    images = [_solid_image((0, 255, 0)) for _ in range(6)]
    grid = xy_plot.compose_grid(images, x_labels=["a", "b", "c"], y_labels=["y1", "y2"], draw_legend=False)
    assert grid.size == (10 * 3, 10 * 2)


def test_compose_grid_1d_y_none():
    images = [_solid_image((0, 0, 255)) for _ in range(3)]
    grid = xy_plot.compose_grid(images, x_labels=["a", "b", "c"], y_labels=[], draw_legend=True)
    # No left margin needed when y axis is "none"
    assert grid.size == (10 * 3, 40 + 10 * 1)


def test_compose_grid_resizes_mismatched_cells():
    images = [_solid_image((255, 0, 0), size=(10, 10)), _solid_image((0, 255, 0), size=(20, 20))]
    grid = xy_plot.compose_grid(images, x_labels=["a", "b"], y_labels=[], draw_legend=False)
    assert grid.size == (20, 10)


def test_compose_grid_empty_images_raises():
    with pytest.raises(ValueError):
        xy_plot.compose_grid([], x_labels=["a"], y_labels=[])


def test_compose_grid_mismatched_length_raises():
    images = [_solid_image((1, 2, 3))]
    with pytest.raises(ValueError):
        xy_plot.compose_grid(images, x_labels=["a", "b"], y_labels=[])


# ------------------------------------------------------------------ #
# run_xy_plot handler
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_run_xy_plot_basic_grid_and_progress():
    tiny_b64 = _tiny_png_b64()
    calls = []

    def fake_txt2img(**kwargs):
        calls.append(kwargs)
        return [tiny_b64]

    fake_save_images = MagicMock(return_value=[{"filename": "grid.png", "path": "/tmp/grid.png", "index": 0}])

    params = {
        "positive": "a cat",
        "negative": "blurry",
        "width": 64,
        "height": 64,
        "steps": 20,
        "cfg_scale": 7.0,
        "sampler": "Euler a",
        "seed": -1,
        "model": "",
        "loras": "",
        "x_axis": {"type": "steps", "values": ["10", "20"]},
        "y_axis": {"type": "cfg_scale", "values": ["5", "9"]},
        "draw_legend": True,
        "include_cell_images": False,
    }
    job = FakeJob(params)
    progress_values = []

    async def update_progress(v):
        progress_values.append(v)

    with (
        patch.object(xy_plot.sd_client, "txt2img", side_effect=fake_txt2img),
        patch.object(xy_plot.sd_client, "save_images", fake_save_images),
    ):
        result = await xy_plot.run_xy_plot(job, update_progress)

    assert len(calls) == 4  # 2x2 grid
    assert all(c["batch_size"] == 1 for c in calls)

    assert result["x_axis"] == "steps"
    assert result["y_axis"] == "cfg_scale"
    assert result["x_labels"] == ["10", "20"]
    assert result["y_labels"] == ["5.0", "9.0"]
    assert result["cell_count"] == 4
    assert len(result["cells"]) == 4
    assert "image" not in result["cells"][0]
    assert "grid_image" in result and isinstance(result["grid_image"], str)
    assert result["saved_files"] == [{"filename": "grid.png", "path": "/tmp/grid.png", "index": 0}]

    # Progress should climb monotonically up to 1.0
    assert progress_values[-1] == 1.0
    assert all(0.0 <= v <= 1.0 for v in progress_values)

    # Axis overrides applied per cell: steps values used on x, cfg_scale on y
    steps_used = sorted({c["steps"] for c in calls})
    cfg_used = sorted({c["cfg_scale"] for c in calls})
    assert steps_used == [10, 20]
    assert cfg_used == [5.0, 9.0]


@pytest.mark.asyncio
async def test_run_xy_plot_include_cell_images():
    tiny_b64 = _tiny_png_b64()
    params = {
        "positive": "a cat",
        "x_axis": {"type": "steps", "values": ["10", "20"]},
        "y_axis": {"type": "none", "values": []},
        "include_cell_images": True,
    }
    job = FakeJob(params)

    async def update_progress(v):
        pass

    with (
        patch.object(xy_plot.sd_client, "txt2img", return_value=[tiny_b64]),
        patch.object(xy_plot.sd_client, "save_images", return_value=[]),
    ):
        result = await xy_plot.run_xy_plot(job, update_progress)

    assert result["y_labels"] == []
    assert result["cell_count"] == 2
    for cell in result["cells"]:
        assert cell["image"] == tiny_b64


@pytest.mark.asyncio
async def test_run_xy_plot_prompt_sr_axis():
    tiny_b64 = _tiny_png_b64()
    calls = []

    def fake_txt2img(**kwargs):
        calls.append(kwargs)
        return [tiny_b64]

    params = {
        "positive": "a cat in a hat",
        "x_axis": {"type": "prompt_sr", "values": ["cat", "cat", "dog"]},
        "y_axis": {"type": "none", "values": []},
    }
    job = FakeJob(params)

    async def update_progress(v):
        pass

    with (
        patch.object(xy_plot.sd_client, "txt2img", side_effect=fake_txt2img),
        patch.object(xy_plot.sd_client, "save_images", return_value=[]),
    ):
        result = await xy_plot.run_xy_plot(job, update_progress)

    positives = [c["positive"] for c in calls]
    assert "a cat in a hat" in positives  # first column: search replaced by itself
    assert "a dog in a hat" in positives
    assert result["x_labels"] == ["cat", "cat", "dog"]


@pytest.mark.asyncio
async def test_run_xy_plot_model_axis_outer_loop_grouping():
    tiny_b64 = _tiny_png_b64()
    calls = []

    def fake_txt2img(**kwargs):
        calls.append(kwargs)
        return [tiny_b64]

    params = {
        "positive": "a cat",
        "x_axis": {"type": "model", "values": ["modelA", "modelB"]},
        "y_axis": {"type": "steps", "values": ["10", "20"]},
    }
    job = FakeJob(params)

    async def update_progress(v):
        pass

    with (
        patch.object(xy_plot.sd_client, "txt2img", side_effect=fake_txt2img),
        patch.object(xy_plot.sd_client, "save_images", return_value=[]),
    ):
        result = await xy_plot.run_xy_plot(job, update_progress)

    models_called = [c["model"] for c in calls]
    # Calls should be grouped by model (no thrashing): all of one model before the other.
    assert models_called == ["modelA", "modelA", "modelB", "modelB"]

    # But grid cells must still land at the correct row-major (x=model, y=steps) position.
    assert result["cell_count"] == 4
    assert result["x_labels"] == ["modelA", "modelB"]
    assert result["y_labels"] == ["10", "20"]
    # Row-major: cells[0]=(x=modelA,y=10) cells[1]=(x=modelB,y=10) cells[2]=(x=modelA,y=20) cells[3]=(x=modelB,y=20)
    assert result["cells"][0]["x_label"] == "modelA"
    assert result["cells"][0]["y_label"] == "10"
    assert result["cells"][1]["x_label"] == "modelB"
    assert result["cells"][1]["y_label"] == "10"
    assert result["cells"][2]["x_label"] == "modelA"
    assert result["cells"][2]["y_label"] == "20"
    assert result["cells"][3]["x_label"] == "modelB"
    assert result["cells"][3]["y_label"] == "20"


@pytest.mark.asyncio
async def test_run_xy_plot_cancellation_partial_result():
    tiny_b64 = _tiny_png_b64()
    params = {
        "positive": "a cat",
        "x_axis": {"type": "steps", "values": ["10", "20", "30"]},
        "y_axis": {"type": "none", "values": []},
    }
    job = FakeJob(params)
    call_count = {"n": 0}

    def fake_txt2img(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            job.status = JobStatus.CANCELLED
        return [tiny_b64]

    async def update_progress(v):
        pass

    with (
        patch.object(xy_plot.sd_client, "txt2img", side_effect=fake_txt2img),
        patch.object(xy_plot.sd_client, "save_images", return_value=[]) as mock_save,
    ):
        result = await xy_plot.run_xy_plot(job, update_progress)

    assert result["cancelled"] is True
    assert result["completed_cells"] == 1
    # Grid composition/save should be skipped once cancelled.
    mock_save.assert_not_called()
    # Only one cell was generated before cancellation was observed.
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_run_xy_plot_cell_failure_propagates():
    params = {
        "positive": "a cat",
        "x_axis": {"type": "steps", "values": ["10"]},
        "y_axis": {"type": "none", "values": []},
    }
    job = FakeJob(params)

    async def update_progress(v):
        pass

    with patch.object(xy_plot.sd_client, "txt2img", side_effect=RuntimeError("SD error")):
        with pytest.raises(RuntimeError):
            await xy_plot.run_xy_plot(job, update_progress)


# ------------------------------------------------------------------ #
# submit endpoint validation
# ------------------------------------------------------------------ #


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    import config
    import deps
    import main as main_module
    import routes.jobs as jobs_routes

    config.RATE_LIMIT_ENABLED = False

    mock_sd = MagicMock()
    mock_sd.get_progress.return_value = None
    mock_sd.is_available.return_value = False
    mock_sd.txt2img.return_value = []
    mock_sd.save_images.return_value = []

    deps.sd_client = mock_sd
    jobs_routes.sd_client = mock_sd
    xy_plot.sd_client = mock_sd

    with TestClient(main_module.app) as c:
        yield c


def test_submit_xy_plot_over_cell_limit_returns_4xx(client):
    payload = {
        "job_type": "xy_plot",
        "params": {
            "positive": "a cat",
            "x_axis": {"type": "steps", "values": [str(i) for i in range(1, 10)]},  # 9
            "y_axis": {"type": "cfg_scale", "values": ["5", "6", "7", "8", "9"]},  # 5 -> 45 cells > 36
        },
    }
    response = client.post("/api/jobs/submit", json=payload)
    assert response.status_code in (400, 422)


def test_submit_xy_plot_within_limit_accepted(client):
    payload = {
        "job_type": "xy_plot",
        "params": {
            "positive": "a cat",
            "x_axis": {"type": "steps", "values": ["10", "20"]},
            "y_axis": {"type": "cfg_scale", "values": ["5", "7"]},
        },
    }
    response = client.post("/api/jobs/submit", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["job"]["job_type"] == "xy_plot"


def test_submit_xy_plot_invalid_axis_type_returns_422(client):
    payload = {
        "job_type": "xy_plot",
        "params": {
            "positive": "a cat",
            "x_axis": {"type": "not_a_real_axis", "values": ["1"]},
        },
    }
    response = client.post("/api/jobs/submit", json=payload)
    assert response.status_code == 422


def test_submit_xy_plot_x_axis_none_rejected(client):
    payload = {
        "job_type": "xy_plot",
        "params": {
            "positive": "a cat",
            "x_axis": {"type": "none", "values": []},
        },
    }
    response = client.post("/api/jobs/submit", json=payload)
    assert response.status_code == 422


def test_submit_xy_plot_missing_positive_returns_422(client):
    payload = {
        "job_type": "xy_plot",
        "params": {
            "x_axis": {"type": "steps", "values": ["10"]},
        },
    }
    response = client.post("/api/jobs/submit", json=payload)
    assert response.status_code == 422
