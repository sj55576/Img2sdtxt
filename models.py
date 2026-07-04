"""Pydantic request models for API endpoints."""

from typing import List, Optional

from pydantic import BaseModel, Field


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


class TextPromptRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=5000)
    style: str = Field("")
    tone: str = Field("")
    quality: str = Field("high")
    preset_id: str = Field("")
    save_history: bool = Field(True)


class RefinePromptRequest(BaseModel):
    positive: str = Field(..., min_length=1, max_length=10000)
    negative: str = Field("")
    instruction: str = Field("")
    style: str = Field("")
    tone: str = Field("")
    quality: str = Field("high")
    parent_id: Optional[int] = Field(None, description="Parent history item ID for version tracking")


class SwitchProviderRequest(BaseModel):
    provider: str
    model: str = ""
    api_key: str = ""


class CreateWildcardRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    entries: list[str] = Field(..., min_length=1)


class UpdateWildcardRequest(BaseModel):
    entries: list[str] = Field(..., min_length=1)


class ExpandPromptRequest(BaseModel):
    template: str = Field(..., min_length=1, max_length=10000)
    mode: str = Field("random", pattern=r"^(random|combinatorial|preview)$")
    count: int = Field(5, ge=1, le=100)
    seed: Optional[int] = Field(None)
    max_combinations: int = Field(100, ge=1, le=1000)
