"""Pydantic request models for API endpoints."""

import re
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from validators import (
    QUALITY_ERROR,
    STYLE_ERROR,
    TONE_ERROR,
    is_valid_quality,
    is_valid_style,
    is_valid_tone,
)


class SDGenerateRequest(BaseModel):
    positive: str = Field(..., min_length=1, description="Positive prompt")
    negative: str = Field("", description="Negative prompt")
    width: int = Field(512, ge=64, le=2048, description="Image width")
    height: int = Field(512, ge=64, le=2048, description="Image height")
    steps: int = Field(20, ge=1, le=150, description="Sampling steps")
    cfg_scale: float = Field(7.0, ge=1.0, le=30.0, description="CFG scale")
    sampler: str = Field("Euler a", description="Sampler name")
    seed: int = Field(-1, description="Random seed (-1 for random)")
    batch_size: int = Field(1, ge=1, le=4, description="Batch size")
    model: str = Field("", description="Model checkpoint name")
    loras: str = Field("", description="LoRA specification")
    enable_hr: bool = Field(False, description="Enable Hires.fix")
    hr_scale: float = Field(2.0, ge=1.0, le=4.0, description="Hires.fix scale")
    hr_upscaler: str = Field("R-ESRGAN 4x+", description="Hires.fix upscaler")
    hr_second_pass_steps: int = Field(0, ge=0, le=150, description="Hires.fix second pass steps")
    hr_denoising_strength: float = Field(0.7, ge=0.0, le=1.0, description="Hires.fix denoising")
    controlnet_args: Optional[List[dict]] = Field(None, description="ControlNet unit arguments")
    expand_wildcards: bool = Field(False, description="Expand dynamic prompt syntax once per generated image")


class SDMultiModelRequest(BaseModel):
    models: List[str] = Field(..., min_length=1, description="List of model names")
    positive: str = Field(..., min_length=1, description="Positive prompt")
    negative: str = Field("", description="Negative prompt")
    width: int = Field(512, ge=64, le=2048)
    height: int = Field(512, ge=64, le=2048)
    steps: int = Field(20, ge=1, le=150)
    cfg_scale: float = Field(7.0, ge=1.0, le=30.0)
    sampler: str = Field("Euler a")
    seed: int = Field(-1)
    batch_size: int = Field(1, ge=1, le=4)
    loras: str = Field("")
    enable_hr: bool = Field(False)
    hr_scale: float = Field(2.0, ge=1.0, le=4.0)
    hr_upscaler: str = Field("R-ESRGAN 4x+")
    hr_second_pass_steps: int = Field(0, ge=0, le=150)
    hr_denoising_strength: float = Field(0.7, ge=0.0, le=1.0)
    expand_wildcards: bool = Field(False, description="Expand dynamic prompt syntax once per generated image")


class WildcardBatchRequest(BaseModel):
    """Generate one image per combinatorial expansion of a dynamic-prompt template.

    ``positive`` holds the template (``{a|b|c}`` / ``__wildcard__`` syntax); each
    combination is expanded once via ``dynamic_prompts.expand_prompt_combinatorial``
    and generated with ``batch_size`` fixed at 1 per combination, mirroring how
    ``SDGenerateRequest.expand_wildcards`` generates one variation per image.
    """

    positive: str = Field(..., min_length=1, description="Dynamic prompt template")
    negative: str = Field("", description="Negative prompt")
    width: int = Field(512, ge=64, le=2048, description="Image width")
    height: int = Field(512, ge=64, le=2048, description="Image height")
    steps: int = Field(20, ge=1, le=150, description="Sampling steps")
    cfg_scale: float = Field(7.0, ge=1.0, le=30.0, description="CFG scale")
    sampler: str = Field("Euler a", description="Sampler name")
    seed: int = Field(-1, description="Random seed (-1 for random)")
    model: str = Field("", description="Model checkpoint name")
    loras: str = Field("", description="LoRA specification")
    enable_hr: bool = Field(False, description="Enable Hires.fix")
    hr_scale: float = Field(2.0, ge=1.0, le=4.0, description="Hires.fix scale")
    hr_upscaler: str = Field("R-ESRGAN 4x+", description="Hires.fix upscaler")
    hr_second_pass_steps: int = Field(0, ge=0, le=150, description="Hires.fix second pass steps")
    hr_denoising_strength: float = Field(0.7, ge=0.0, le=1.0, description="Hires.fix denoising")
    max_combinations: int = Field(
        36, ge=1, le=1000, description="Safety cap checked against WILDCARD_BATCH_MAX_COMBINATIONS"
    )


class XYPlotAxis(BaseModel):
    type: str = Field(..., description="Axis type: steps, cfg_scale, sampler, seed, model, prompt_sr, or none")
    values: List[str] = Field(default_factory=list, description="Raw axis values (coerced per axis type)")


class XYPlotRequest(BaseModel):
    positive: str = Field(..., min_length=1, description="Positive prompt")
    negative: str = Field("", description="Negative prompt")
    width: int = Field(512, ge=64, le=2048, description="Image width")
    height: int = Field(512, ge=64, le=2048, description="Image height")
    steps: int = Field(20, ge=1, le=150, description="Sampling steps")
    cfg_scale: float = Field(7.0, ge=1.0, le=30.0, description="CFG scale")
    sampler: str = Field("Euler a", description="Sampler name")
    seed: int = Field(-1, description="Random seed (-1 for random)")
    model: str = Field("", description="Model checkpoint name")
    loras: str = Field("", description="LoRA specification")
    x_axis: XYPlotAxis = Field(..., description="X axis definition")
    y_axis: XYPlotAxis = Field(default_factory=lambda: XYPlotAxis(type="none"), description="Y axis definition")
    draw_legend: bool = Field(True, description="Draw axis labels on the composed grid image")
    include_cell_images: bool = Field(False, description="Include each cell's base64 image in the result")


class TextPromptRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000)
    style: str = Field("")
    tone: str = Field("")
    quality: str = Field("high")
    preset_id: str = Field("")
    save_history: bool = Field(True)

    @field_validator("style")
    @classmethod
    def _validate_style(cls, v: str) -> str:
        if not is_valid_style(v):
            raise ValueError(STYLE_ERROR)
        return v

    @field_validator("tone")
    @classmethod
    def _validate_tone(cls, v: str) -> str:
        if not is_valid_tone(v):
            raise ValueError(TONE_ERROR)
        return v

    @field_validator("quality")
    @classmethod
    def _validate_quality(cls, v: str) -> str:
        if not is_valid_quality(v):
            raise ValueError(QUALITY_ERROR)
        return v


class RefinePromptRequest(BaseModel):
    positive: str = Field(..., min_length=1, max_length=10000)
    negative: str = Field("")
    instruction: str = Field("")
    style: str = Field("")
    tone: str = Field("")
    quality: str = Field("high")
    parent_id: Optional[int] = Field(None, description="Parent history item ID for version tracking")

    @field_validator("style")
    @classmethod
    def _validate_style(cls, v: str) -> str:
        if not is_valid_style(v):
            raise ValueError(STYLE_ERROR)
        return v

    @field_validator("tone")
    @classmethod
    def _validate_tone(cls, v: str) -> str:
        if not is_valid_tone(v):
            raise ValueError(TONE_ERROR)
        return v

    @field_validator("quality")
    @classmethod
    def _validate_quality(cls, v: str) -> str:
        if not is_valid_quality(v):
            raise ValueError(QUALITY_ERROR)
        return v


class SwitchProviderRequest(BaseModel):
    provider: str
    model: str = ""
    api_key: str = ""


class CreateWildcardRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    entries: list[str] = Field(..., min_length=1)


class UpdateWildcardRequest(BaseModel):
    entries: list[str] = Field(..., min_length=1)


class ABConfig(BaseModel):
    positive: str = Field(..., min_length=1, description="Positive prompt")
    negative: str = Field("", description="Negative prompt")
    steps: int = Field(20, ge=1, le=150, description="Sampling steps")
    cfg_scale: float = Field(7.0, ge=1.0, le=30.0, description="CFG scale")
    sampler: str = Field("Euler a", description="Sampler name")
    width: int = Field(512, ge=64, le=2048, description="Image width")
    height: int = Field(512, ge=64, le=2048, description="Image height")


class ABGenerateRequest(BaseModel):
    config_a: ABConfig = Field(..., description="A案の生成設定")
    config_b: ABConfig = Field(..., description="B案の生成設定")
    seed: int = Field(-1, description="共有シード（-1でランダム生成し両方に使用）")


class ABVoteRequest(BaseModel):
    winner: str = Field(..., description="勝者。'a' または 'b'")
    note: str = Field("", description="投票メモ")


class ExpandPromptRequest(BaseModel):
    template: str = Field(..., min_length=1, max_length=10000)
    mode: str = Field("random", pattern=r"^(random|combinatorial|preview)$")
    count: int = Field(5, ge=1, le=100)
    seed: Optional[int] = Field(None)
    max_combinations: int = Field(100, ge=1, le=1000)


_PRESET_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PresetCreateRequest(BaseModel):
    """Payload for ``POST /api/presets``.

    Field set intentionally mirrors what ``presets.py`` actually reads
    (``get_preset``/``add_preset``/the default presets): ``id``, ``name``,
    ``description``, ``positive_suffix``, ``negative_suffix``, ``style``,
    ``tone``, ``quality``. ``is_default`` is deliberately NOT exposed here —
    ``presets.add_preset`` always forces it to ``False`` for user-created
    presets, so accepting it from the client would be misleading.

    Extra/unknown fields are rejected (422) rather than silently persisted,
    since the previous ``dict``-typed endpoint persisted whatever the client
    sent verbatim to ``data/presets.json``.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field("", max_length=64, description="Optional explicit preset id")
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field("", max_length=500)
    positive_suffix: str = Field(..., min_length=1, max_length=2000)
    negative_suffix: str = Field(..., min_length=1, max_length=2000)
    style: str = Field("")
    tone: str = Field("")
    quality: str = Field("")

    @field_validator("id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        if v == "":
            return v
        if not _PRESET_ID_RE.match(v):
            raise ValueError(
                "Preset id must be 1-64 characters and contain only letters, numbers, hyphens, or underscores."
            )
        return v

    @field_validator("style")
    @classmethod
    def _validate_style(cls, v: str) -> str:
        if not is_valid_style(v):
            raise ValueError(STYLE_ERROR)
        return v

    @field_validator("tone")
    @classmethod
    def _validate_tone(cls, v: str) -> str:
        if not is_valid_tone(v):
            raise ValueError(TONE_ERROR)
        return v

    @field_validator("quality")
    @classmethod
    def _validate_quality(cls, v: str) -> str:
        if not is_valid_quality(v):
            raise ValueError(QUALITY_ERROR)
        return v
