"""XY Plot generation: vary one or two Stable Diffusion parameters across a grid of images.

XYプロット機能: 1つまたは2つのパラメータを軸として変化させ、画像のグリッドを生成する。
Each cell is generated via ``sd_client.txt2img`` and the results are composed into a single
labeled grid image using Pillow.
"""

import base64
import logging
import textwrap
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageDraw, ImageFont

from config import XY_PLOT_MAX_CELLS
from deps import sd_client
from job_queue import JobStatus

logger = logging.getLogger("img2sdtxt.xy_plot")

# Supported axis types. "none" is only valid for the y axis (produces a 1xN plot).
SUPPORTED_AXIS_TYPES = {"steps", "cfg_scale", "sampler", "seed", "model", "prompt_sr", "none"}

_TOP_MARGIN = 40
_LEFT_MARGIN = 120


def parse_axis_values(axis_type: str, values: List[str]) -> List[Any]:
    """Coerce/validate raw string axis values according to axis_type.

    軸タイプに応じて生の文字列値を型変換・検証する。不正な値は ValueError を送出する。
    """
    if axis_type not in SUPPORTED_AXIS_TYPES:
        raise ValueError(f"Unsupported axis type: {axis_type!r}")

    if axis_type == "none":
        return []

    if not values:
        raise ValueError(f"Axis type '{axis_type}' requires at least one value")

    if axis_type == "prompt_sr" and len(values) < 2:
        raise ValueError("prompt_sr axis requires at least 2 values (search string plus one or more replacements)")

    if axis_type == "steps":
        parsed: List[Any] = []
        for v in values:
            try:
                iv = int(v)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid steps value: {v!r} (must be an integer)")
            if not (1 <= iv <= 150):
                raise ValueError(f"steps value out of range (1..150): {iv}")
            parsed.append(iv)
        return parsed

    if axis_type == "cfg_scale":
        parsed = []
        for v in values:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid cfg_scale value: {v!r} (must be a number)")
            if not (1.0 <= fv <= 30.0):
                raise ValueError(f"cfg_scale value out of range (1.0..30.0): {fv}")
            parsed.append(fv)
        return parsed

    if axis_type == "sampler":
        for v in values:
            if not isinstance(v, str) or not v.strip():
                raise ValueError(f"Invalid sampler value: {v!r} (must be a non-empty string)")
        return [v.strip() for v in values]

    if axis_type == "seed":
        parsed = []
        for v in values:
            try:
                parsed.append(int(v))
            except (TypeError, ValueError):
                raise ValueError(f"Invalid seed value: {v!r} (must be an integer)")
        return parsed

    if axis_type == "model":
        for v in values:
            if not isinstance(v, str) or not v.strip():
                raise ValueError(f"Invalid model value: {v!r} (must be a non-empty string)")
        return [v.strip() for v in values]

    if axis_type == "prompt_sr":
        return [str(v) for v in values]

    raise ValueError(f"Unsupported axis type: {axis_type!r}")


def validate_cell_count(
    x_values: List[Any], y_values: List[Any], max_cells: int = XY_PLOT_MAX_CELLS
) -> Tuple[int, int]:
    """Ensure the requested grid does not exceed the configured cell-count limit.

    グリッドのセル数が上限 (XY_PLOT_MAX_CELLS) を超えないことを検証する。
    Returns (cols, rows).
    """
    cols = len(x_values)
    rows = max(1, len(y_values))
    total = cols * rows
    if total > max_cells:
        raise ValueError(f"XY plot would generate {total} cells, exceeding the maximum of {max_cells}")
    if cols == 0:
        raise ValueError("x_axis must produce at least one value")
    return cols, rows


def _axis_label(axis_type: str, value: Any) -> str:
    if axis_type == "prompt_sr":
        return str(value) if str(value) else "(empty)"
    return str(value)


def _truncate(text: str, width: int) -> List[str]:
    if not text:
        return [""]
    return textwrap.wrap(text, width=width) or [""]


def compose_grid(
    images: List[Image.Image],
    x_labels: List[str],
    y_labels: List[str],
    draw_legend: bool = True,
) -> Image.Image:
    """Compose a row-major list of PIL images into a single labeled grid image.

    images: 行優先 (row-major) 順の PIL Image リスト（長さ = rows * cols）
    """
    if not images:
        raise ValueError("images must not be empty")

    cols = len(x_labels) if x_labels else 1
    rows = len(y_labels) if y_labels else 1

    if len(images) != rows * cols:
        raise ValueError(f"images length ({len(images)}) does not match rows*cols ({rows * cols})")

    cell_w, cell_h = images[0].size

    normalized: List[Image.Image] = []
    for img in images:
        if img.size != (cell_w, cell_h):
            img = img.resize((cell_w, cell_h))
        normalized.append(img.convert("RGB"))

    top_margin = _TOP_MARGIN if (draw_legend and x_labels) else 0
    left_margin = _LEFT_MARGIN if (draw_legend and y_labels) else 0

    grid_w = left_margin + cell_w * cols
    grid_h = top_margin + cell_h * rows

    grid = Image.new("RGB", (grid_w, grid_h), "white")
    for idx, img in enumerate(normalized):
        r = idx // cols
        c = idx % cols
        x = left_margin + c * cell_w
        y = top_margin + r * cell_h
        grid.paste(img, (x, y))

    if draw_legend:
        draw = ImageDraw.Draw(grid)
        font = ImageFont.load_default()

        if x_labels:
            for c, label in enumerate(x_labels):
                lines = _truncate(label, width=max(8, cell_w // 7))
                x = left_margin + c * cell_w + 4
                y = 2
                for line in lines[:2]:
                    draw.text((x, y), line, fill="black", font=font)
                    y += 12

        if y_labels:
            for r, label in enumerate(y_labels):
                lines = _truncate(label, width=18)
                y = top_margin + r * cell_h + max(2, cell_h // 2 - 6 * len(lines))
                for line in lines[:4]:
                    draw.text((4, y), line, fill="black", font=font)
                    y += 12

    return grid


def _decode_b64_image(b64_str: str) -> Image.Image:
    raw = base64.b64decode(b64_str)
    return Image.open(BytesIO(raw)).convert("RGB")


def _encode_image_b64(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _apply_overrides(
    base: Dict[str, Any],
    x_type: str,
    x_value: Any,
    y_type: str,
    y_value: Any,
    x_search: Any = None,
    y_search: Any = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Apply x/y axis overrides to a base parameter dict, returning (cell_params, applied).

    For "prompt_sr" axes, x_search/y_search must be the axis's values[0] (the search
    string); each cell replaces that search string with its own axis value.
    """
    cell_params = dict(base)
    applied: Dict[str, Any] = {}

    for axis_type, axis_value, search in (
        (x_type, x_value, x_search),
        (y_type, y_value, y_search),
    ):
        if axis_type == "none" or axis_value is None:
            continue
        if axis_type == "prompt_sr":
            replacement = axis_value
            cell_params["positive"] = str(cell_params.get("positive", "")).replace(str(search), str(replacement))
            applied["prompt_sr"] = replacement
        else:
            cell_params[axis_type] = axis_value
            applied[axis_type] = axis_value

    return cell_params, applied


async def run_xy_plot(job, update_progress) -> Dict[str, Any]:
    """Async job handler for the "xy_plot" job type.

    XYプロットジョブのハンドラ。行優先でセルを生成し、グリッド画像に合成する。
    """
    p = job.params

    x_axis = p["x_axis"]
    y_axis = p.get("y_axis") or {"type": "none", "values": []}
    x_type = x_axis["type"]
    y_type = y_axis["type"]

    x_values = parse_axis_values(x_type, x_axis.get("values", []))
    y_values = parse_axis_values(y_type, y_axis.get("values", []))

    cols, rows = validate_cell_count(x_values, y_values)
    total = cols * rows

    x_labels = [_axis_label(x_type, v) for v in x_values]
    y_labels = [_axis_label(y_type, v) for v in y_values] if y_type != "none" else []

    x_search = x_values[0] if x_type == "prompt_sr" else None
    y_search = y_values[0] if y_type == "prompt_sr" else None

    base_params: Dict[str, Any] = {
        "positive": p["positive"],
        "negative": p.get("negative", ""),
        "width": p.get("width", 512),
        "height": p.get("height", 512),
        "steps": p.get("steps", 20),
        "cfg_scale": p.get("cfg_scale", 7.0),
        "sampler": p.get("sampler", "Euler a"),
        "seed": p.get("seed", -1),
        "model": p.get("model", ""),
        "loras": p.get("loras", ""),
    }

    include_cell_images = bool(p.get("include_cell_images", False))
    draw_legend = bool(p.get("draw_legend", True))

    # Effective per-axis value lists (length 1 with sentinel None when axis is "none")
    y_iter: List[Any] = y_values if y_values else [None]

    # Build the row-major cell grid, iterating in an order that minimizes model
    # checkpoint switching if exactly one axis is "model".
    grid_images: List[Optional[Image.Image]] = [None] * total
    cells: List[Dict[str, Any]] = [{} for _ in range(total)]

    model_on_x = x_type == "model"
    model_on_y = y_type == "model"

    def cell_index(xi: int, yi: int) -> int:
        return yi * cols + xi

    # Build the list of (xi, yi) pairs in an order that groups by model when applicable.
    order: List[Tuple[int, int]] = []
    if model_on_x and not model_on_y:
        for xi in range(cols):
            for yi in range(len(y_iter)):
                order.append((xi, yi))
    else:
        for yi in range(len(y_iter)):
            for xi in range(cols):
                order.append((xi, yi))

    completed = 0
    for xi, yi in order:
        job_is_cancelled = getattr(job, "status", None) == JobStatus.CANCELLED
        if job_is_cancelled:
            return {
                "cancelled": True,
                "x_axis": x_type,
                "y_axis": y_type,
                "x_labels": x_labels,
                "y_labels": y_labels,
                "cell_count": total,
                "cells": [c for c in cells if c],
                "completed_cells": completed,
            }

        x_val = x_values[xi]
        y_val = y_iter[yi]

        cell_params, applied = _apply_overrides(
            base_params, x_type, x_val, y_type, y_val, x_search=x_search, y_search=y_search
        )

        images = await run_in_threadpool(
            sd_client.txt2img,
            positive=cell_params["positive"],
            negative=cell_params.get("negative", ""),
            width=cell_params.get("width", 512),
            height=cell_params.get("height", 512),
            steps=cell_params.get("steps", 20),
            cfg_scale=cell_params.get("cfg_scale", 7.0),
            sampler=cell_params.get("sampler", "Euler a"),
            seed=cell_params.get("seed", -1),
            batch_size=1,
            model=cell_params.get("model", ""),
            loras=cell_params.get("loras", ""),
        )
        if not images:
            raise Exception(f"XY plot cell (x={xi}, y={yi}) produced no image")

        cell_image = _decode_b64_image(images[0])
        idx = cell_index(xi, yi)
        grid_images[idx] = cell_image

        cell_entry: Dict[str, Any] = {
            "x_label": x_labels[xi] if xi < len(x_labels) else "",
            "y_label": y_labels[yi] if yi < len(y_labels) else "",
            "params": applied,
        }
        if include_cell_images:
            cell_entry["image"] = images[0]
        cells[idx] = cell_entry

        completed += 1
        await update_progress((completed / total) * 0.95)

    # All cells generated (grid_images should be fully populated at this point).
    final_images = [img for img in grid_images if img is not None]
    if len(final_images) != total:
        raise Exception("XY plot did not generate all cells")

    grid = compose_grid(final_images, x_labels, y_labels, draw_legend=draw_legend)
    grid_b64 = _encode_image_b64(grid)

    saved_files = await run_in_threadpool(
        sd_client.save_images,
        images=[grid_b64],
        positive=base_params["positive"],
        negative=base_params.get("negative", ""),
        width=base_params.get("width", 512),
        height=base_params.get("height", 512),
        steps=base_params.get("steps", 20),
        cfg_scale=base_params.get("cfg_scale", 7.0),
        sampler=base_params.get("sampler", "Euler a"),
        seed=base_params.get("seed", -1),
        model=base_params.get("model", ""),
        loras=base_params.get("loras", ""),
    )

    await update_progress(1.0)

    return {
        "grid_image": grid_b64,
        "x_axis": x_type,
        "y_axis": y_type,
        "x_labels": x_labels,
        "y_labels": y_labels,
        "cell_count": total,
        "cells": cells,
        "saved_files": saved_files,
    }
