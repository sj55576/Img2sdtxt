"""tests/test_sd_client.py — SDClient と parse_a1111_parameters の単体テスト (Issue #66)

すべてのネットワーク呼び出しは requests.get / requests.post をモックして検証する。
実際の Stable Diffusion WebUI には接続しない。
"""

import base64
import json
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sd_client import SDClient, parse_a1111_parameters  # noqa: E402

# ------------------------------------------------------------------ #
# Helpers / fixtures
# ------------------------------------------------------------------ #


def _make_png_base64(size=(4, 4), color=(120, 200, 50)) -> str:
    """テスト用の小さな PNG を生成して Base64 文字列で返す"""
    buf = BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    """retry_with_backoff の実待機を無くしてテストを高速化する"""
    monkeypatch.setattr("retry.time.sleep", lambda *a, **k: None)


@pytest.fixture()
def sd(tmp_path, monkeypatch):
    """SD_OUTPUT_DIR を tmp_path にリダイレクトした SDClient を返す"""
    monkeypatch.setattr("sd_client.SD_OUTPUT_DIR", tmp_path)
    return SDClient(base_url="http://fake-sd:7860")


def _mock_response(status_code=200, json_data=None, raise_exc=None):
    resp = MagicMock()
    resp.status_code = status_code
    if raise_exc is not None:
        resp.raise_for_status.side_effect = raise_exc
    else:
        resp.raise_for_status.return_value = None
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


# ------------------------------------------------------------------ #
# is_available
# ------------------------------------------------------------------ #


class TestSDClientAvailability:
    @patch("sd_client.requests.get")
    def test_is_available_true_on_200(self, mock_get, sd):
        mock_get.return_value = _mock_response(status_code=200)
        assert sd.is_available() is True
        mock_get.assert_called_once()
        assert mock_get.call_args.args[0] == "http://fake-sd:7860/sdapi/v1/sd-models"

    @patch("sd_client.requests.get")
    def test_is_available_false_on_non_200(self, mock_get, sd):
        mock_get.return_value = _mock_response(status_code=500)
        assert sd.is_available() is False

    @patch("sd_client.requests.get")
    def test_is_available_false_on_exception(self, mock_get, sd):
        mock_get.side_effect = requests.exceptions.ConnectionError("refused")
        assert sd.is_available() is False


# ------------------------------------------------------------------ #
# get_models / get_current_model / set_model / get_model_list
# ------------------------------------------------------------------ #


class TestSDClientModels:
    @patch("sd_client.requests.get")
    def test_get_models_returns_list(self, mock_get, sd):
        models = [{"title": "modelA"}, {"title": "modelB"}]
        mock_get.return_value = _mock_response(json_data=models)
        assert sd.get_models() == models

    @patch("sd_client.requests.get")
    def test_get_models_raises_on_error(self, mock_get, sd):
        mock_get.side_effect = Exception("network down")
        with pytest.raises(Exception, match="Failed to get models"):
            sd.get_models()

    @patch("sd_client.requests.get")
    def test_get_current_model_returns_name(self, mock_get, sd):
        mock_get.return_value = _mock_response(json_data={"sd_model_checkpoint": "modelXYZ"})
        assert sd.get_current_model() == "modelXYZ"

    @patch("sd_client.requests.get")
    def test_get_current_model_returns_empty_string_on_error(self, mock_get, sd):
        mock_get.side_effect = Exception("boom")
        assert sd.get_current_model() == ""

    @patch("sd_client.requests.post")
    def test_set_model_returns_true_on_success(self, mock_post, sd):
        mock_post.return_value = _mock_response()
        assert sd.set_model("newmodel") is True
        mock_post.assert_called_once_with(
            "http://fake-sd:7860/sdapi/v1/options",
            json={"sd_model_checkpoint": "newmodel"},
            timeout=30,
        )

    @patch("sd_client.requests.post")
    def test_set_model_returns_false_on_error(self, mock_post, sd):
        mock_post.side_effect = Exception("boom")
        assert sd.set_model("newmodel") is False

    def test_get_model_list_delegates_to_get_models(self, sd):
        with patch.object(sd, "get_models", return_value=[{"title": "m1"}]) as mock_get_models:
            result = sd.get_model_list()
            assert result == [{"title": "m1"}]
            mock_get_models.assert_called_once()


# ------------------------------------------------------------------ #
# get_loras
# ------------------------------------------------------------------ #


class TestSDClientLoras:
    @patch("sd_client.requests.get")
    def test_get_loras_returns_list(self, mock_get, sd):
        loras = [{"name": "lora1"}, {"name": "lora2"}]
        mock_get.return_value = _mock_response(json_data=loras)
        assert sd.get_loras() == loras

    @patch("sd_client.requests.get")
    def test_get_loras_handles_non_list_response(self, mock_get, sd):
        mock_get.return_value = _mock_response(json_data={"unexpected": "dict"})
        assert sd.get_loras() == []

    @patch("sd_client.requests.get")
    def test_get_loras_returns_empty_list_on_error(self, mock_get, sd):
        mock_get.side_effect = Exception("boom")
        assert sd.get_loras() == []


# ------------------------------------------------------------------ #
# get_progress
# ------------------------------------------------------------------ #


class TestSDClientProgress:
    @patch("sd_client.requests.get")
    def test_get_progress_returns_dict(self, mock_get, sd):
        progress = {"progress": 0.5, "eta_relative": 3.2}
        mock_get.return_value = _mock_response(json_data=progress)
        assert sd.get_progress() == progress

    @patch("sd_client.requests.get")
    def test_get_progress_returns_none_on_error(self, mock_get, sd):
        mock_get.side_effect = Exception("boom")
        assert sd.get_progress() is None


# ------------------------------------------------------------------ #
# ControlNet endpoints
# ------------------------------------------------------------------ #


class TestSDClientControlNet:
    @patch("sd_client.requests.get")
    def test_get_controlnet_models_returns_list(self, mock_get, sd):
        mock_get.return_value = _mock_response(json_data={"model_list": ["canny", "depth"]})
        assert sd.get_controlnet_models() == ["canny", "depth"]

    @patch("sd_client.requests.get")
    def test_get_controlnet_models_returns_empty_on_error(self, mock_get, sd):
        mock_get.side_effect = Exception("not installed")
        assert sd.get_controlnet_models() == []

    @patch("sd_client.requests.get")
    def test_get_controlnet_modules_returns_list(self, mock_get, sd):
        mock_get.return_value = _mock_response(json_data={"module_list": ["canny", "none"]})
        assert sd.get_controlnet_modules() == ["canny", "none"]

    @patch("sd_client.requests.get")
    def test_get_controlnet_modules_returns_empty_on_error(self, mock_get, sd):
        mock_get.side_effect = Exception("not installed")
        assert sd.get_controlnet_modules() == []

    @patch("sd_client.requests.get")
    def test_get_controlnet_settings_returns_dict(self, mock_get, sd):
        settings = {"control_net_max_models_num": 3}
        mock_get.return_value = _mock_response(json_data=settings)
        assert sd.get_controlnet_settings() == settings

    @patch("sd_client.requests.get")
    def test_get_controlnet_settings_returns_empty_dict_on_error(self, mock_get, sd):
        mock_get.side_effect = Exception("not installed")
        assert sd.get_controlnet_settings() == {}


# ------------------------------------------------------------------ #
# get_upscalers / get_samplers
# ------------------------------------------------------------------ #


class TestSDClientUpscalersAndSamplers:
    @patch("sd_client.requests.get")
    def test_get_upscalers_returns_names(self, mock_get, sd):
        mock_get.return_value = _mock_response(json_data=[{"name": "Latent"}, {"name": "ESRGAN_4x"}])
        assert sd.get_upscalers() == ["Latent", "ESRGAN_4x"]

    @patch("sd_client.requests.get")
    def test_get_upscalers_returns_defaults_on_error(self, mock_get, sd):
        mock_get.side_effect = Exception("boom")
        result = sd.get_upscalers()
        assert "Latent" in result
        assert "R-ESRGAN 4x+" in result
        assert len(result) == 15

    @patch("sd_client.requests.get")
    def test_get_samplers_returns_names(self, mock_get, sd):
        mock_get.return_value = _mock_response(json_data=[{"name": "Euler a"}, {"name": "DDIM"}])
        assert sd.get_samplers() == ["Euler a", "DDIM"]

    @patch("sd_client.requests.get")
    def test_get_samplers_returns_defaults_on_error(self, mock_get, sd):
        mock_get.side_effect = Exception("boom")
        assert sd.get_samplers() == ["Euler a", "Euler", "DPM++ 2M Karras", "DDIM"]


# ------------------------------------------------------------------ #
# txt2img
# ------------------------------------------------------------------ #


class TestSDClientTxt2Img:
    @patch("sd_client.requests.post")
    def test_txt2img_returns_images(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": ["img_b64_1", "img_b64_2"]})
        images = sd.txt2img("a cat", "blurry")
        assert images == ["img_b64_1", "img_b64_2"]
        mock_post.assert_called_once()
        assert mock_post.call_args.args[0] == "http://fake-sd:7860/sdapi/v1/txt2img"

    @patch("sd_client.requests.post")
    def test_txt2img_lora_injection_comma_format(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        sd.txt2img("a cat", "blurry", loras="lora1:1.0,lora2:0.8")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["prompt"] == "<lora:lora1:1.0><lora:lora2:0.8>, a cat"

    @patch("sd_client.requests.post")
    def test_txt2img_lora_injection_already_tagged_format(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        sd.txt2img("a cat", "blurry", loras="<lora:lora1:1.0>")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["prompt"] == "<lora:lora1:1.0>, a cat"

    @patch("sd_client.requests.post")
    def test_txt2img_hires_fix_params_enabled(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        sd.txt2img(
            "a cat",
            "blurry",
            enable_hr=True,
            hr_scale=1.5,
            hr_upscaler="Lanczos",
            hr_second_pass_steps=10,
            hr_denoising_strength=0.55,
        )
        payload = mock_post.call_args.kwargs["json"]
        assert payload["enable_hr"] is True
        assert payload["hr_scale"] == 1.5
        assert payload["hr_upscaler"] == "Lanczos"
        assert payload["hr_second_pass_steps"] == 10
        assert payload["denoising_strength"] == 0.55

    @patch("sd_client.requests.post")
    def test_txt2img_hires_fix_disabled_uses_default_denoising(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        sd.txt2img("a cat", "blurry", enable_hr=False, hr_denoising_strength=0.9)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["enable_hr"] is False
        assert payload["denoising_strength"] == 0.7

    @patch("sd_client.requests.post")
    def test_txt2img_controlnet_args_included(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        cn_args = [{"module": "canny", "model": "control_canny"}]
        sd.txt2img("a cat", "blurry", controlnet_args=cn_args)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["alwayson_scripts"]["controlnet"]["args"] == cn_args

    @patch("sd_client.requests.post")
    def test_txt2img_no_controlnet_args_key_when_none(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        sd.txt2img("a cat", "blurry")
        payload = mock_post.call_args.kwargs["json"]
        assert "alwayson_scripts" not in payload

    @patch("sd_client.requests.post")
    def test_txt2img_model_switching_calls_options_then_generation(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        sd.txt2img("a cat", "blurry", model="newmodel")
        assert mock_post.call_count == 2
        first_call, second_call = mock_post.call_args_list
        assert first_call.args[0] == "http://fake-sd:7860/sdapi/v1/options"
        assert first_call.kwargs["json"] == {"sd_model_checkpoint": "newmodel"}
        assert second_call.args[0] == "http://fake-sd:7860/sdapi/v1/txt2img"

    @patch("sd_client.requests.post")
    def test_txt2img_connection_error_raises_and_retries(self, mock_post, sd):
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        with pytest.raises(ConnectionError):
            sd.txt2img("a cat", "blurry")
        # max_retries=2 -> 3 total attempts
        assert mock_post.call_count == 3

    @patch("sd_client.requests.post")
    def test_txt2img_timeout_raises(self, mock_post, sd):
        mock_post.side_effect = requests.exceptions.Timeout("too slow")
        with pytest.raises(TimeoutError):
            sd.txt2img("a cat", "blurry")
        assert mock_post.call_count == 3


# ------------------------------------------------------------------ #
# img2img
# ------------------------------------------------------------------ #


class TestSDClientImg2Img:
    @patch("sd_client.requests.post")
    def test_img2img_returns_images(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": ["img1"]})
        init_image = _make_png_base64()
        result = sd.img2img(init_image, "a cat", "blurry")
        assert result == ["img1"]
        assert mock_post.call_args.args[0] == "http://fake-sd:7860/sdapi/v1/img2img"

    @patch("sd_client.requests.post")
    def test_img2img_payload_params(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        init_image = _make_png_base64()
        sd.img2img(init_image, "a cat", "blurry", denoising_strength=0.42, resize_mode=2)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["init_images"] == [init_image]
        assert payload["denoising_strength"] == 0.42
        assert payload["resize_mode"] == 2

    @patch("sd_client.requests.post")
    def test_img2img_lora_injection(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        init_image = _make_png_base64()
        sd.img2img(init_image, "a cat", "blurry", loras="lora1:0.5")
        payload = mock_post.call_args.kwargs["json"]
        assert payload["prompt"] == "<lora:lora1:0.5>, a cat"

    @patch("sd_client.requests.post")
    def test_img2img_connection_error_raises(self, mock_post, sd):
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        with pytest.raises(ConnectionError):
            sd.img2img(_make_png_base64(), "a cat", "blurry")

    @patch("sd_client.requests.post")
    def test_img2img_timeout_raises(self, mock_post, sd):
        mock_post.side_effect = requests.exceptions.Timeout("too slow")
        with pytest.raises(TimeoutError):
            sd.img2img(_make_png_base64(), "a cat", "blurry")


# ------------------------------------------------------------------ #
# inpaint
# ------------------------------------------------------------------ #


class TestSDClientInpaint:
    @patch("sd_client.requests.post")
    def test_inpaint_returns_images(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": ["img1"]})
        init_image = _make_png_base64()
        mask = _make_png_base64(color=(255, 255, 255))
        result = sd.inpaint(init_image, mask, "a cat", "blurry")
        assert result == ["img1"]
        assert mock_post.call_args.args[0] == "http://fake-sd:7860/sdapi/v1/img2img"

    @patch("sd_client.requests.post")
    def test_inpaint_mask_params(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"images": []})
        init_image = _make_png_base64()
        mask = _make_png_base64(color=(255, 255, 255))
        sd.inpaint(
            init_image,
            mask,
            "a cat",
            "blurry",
            mask_blur=8,
            inpainting_fill=2,
            inpaint_full_res=False,
            inpaint_full_res_padding=64,
        )
        payload = mock_post.call_args.kwargs["json"]
        assert payload["mask"] == mask
        assert payload["mask_blur"] == 8
        assert payload["inpainting_fill"] == 2
        assert payload["inpaint_full_res"] is False
        assert payload["inpaint_full_res_padding"] == 64

    @patch("sd_client.requests.post")
    def test_inpaint_connection_error_raises(self, mock_post, sd):
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        with pytest.raises(ConnectionError):
            sd.inpaint(_make_png_base64(), _make_png_base64(), "a cat", "blurry")

    @patch("sd_client.requests.post")
    def test_inpaint_timeout_raises(self, mock_post, sd):
        mock_post.side_effect = requests.exceptions.Timeout("too slow")
        with pytest.raises(TimeoutError):
            sd.inpaint(_make_png_base64(), _make_png_base64(), "a cat", "blurry")


# ------------------------------------------------------------------ #
# interrogate
# ------------------------------------------------------------------ #


class TestSDClientInterrogate:
    @patch("sd_client.requests.post")
    def test_interrogate_returns_caption(self, mock_post, sd):
        mock_post.return_value = _mock_response(json_data={"caption": "1girl, solo"})
        caption = sd.interrogate(b"fake-bytes", model="clip")
        assert caption == "1girl, solo"
        payload = mock_post.call_args.kwargs["json"]
        assert payload["model"] == "clip"
        assert "image" in payload

    @patch("sd_client.requests.post")
    def test_interrogate_connection_error_raises(self, mock_post, sd):
        mock_post.side_effect = requests.exceptions.ConnectionError("refused")
        with pytest.raises(ConnectionError):
            sd.interrogate(b"fake-bytes")

    @patch("sd_client.requests.post")
    def test_interrogate_timeout_raises(self, mock_post, sd):
        mock_post.side_effect = requests.exceptions.Timeout("too slow")
        with pytest.raises(TimeoutError):
            sd.interrogate(b"fake-bytes")


# ------------------------------------------------------------------ #
# save_images
# ------------------------------------------------------------------ #


class TestSDClientSaveImages:
    def test_save_images_creates_png_with_metadata(self, sd, tmp_path):
        img_b64 = _make_png_base64()
        saved = sd.save_images(
            [img_b64],
            positive="a cat",
            negative="blurry",
            width=512,
            height=512,
            steps=20,
            cfg_scale=7.0,
            sampler="Euler a",
            seed=42,
            model="mymodel",
            loras="lora1:1.0",
            mode="txt2img",
        )
        assert len(saved) == 1
        filepath = Path(saved[0]["path"])
        assert filepath.exists()
        assert filepath.name.startswith("sd_")

        with Image.open(filepath) as img:
            params = img.info.get("parameters")
        assert params is not None
        assert params.startswith("a cat")
        assert "Negative prompt: blurry" in params
        assert "Steps: 20" in params
        assert "Sampler: Euler a" in params
        assert "CFG scale: 7.0" in params
        assert "Seed: 42" in params
        assert "Size: 512x512" in params
        assert "Model: mymodel" in params
        assert "LoRA: lora1:1.0" in params

    def test_save_images_writes_metadata_json(self, sd, tmp_path):
        img_b64 = _make_png_base64()
        saved = sd.save_images([img_b64], positive="a cat", negative="blurry", mode="txt2img")
        date_dir = Path(saved[0]["path"]).parent
        metadata_files = list(date_dir.glob("sd_*_metadata.json"))
        assert len(metadata_files) == 1

        with open(metadata_files[0], encoding="utf-8") as f:
            metadata = json.load(f)
        assert metadata["mode"] == "txt2img"
        assert metadata["image_count"] == 1
        assert metadata["parameters"]["positive_prompt"] == "a cat"
        assert metadata["parameters"]["negative_prompt"] == "blurry"
        assert "denoising_strength" not in metadata["parameters"]
        assert len(metadata["files"]) == 1

    def test_save_images_generates_thumbnail(self, sd, tmp_path):
        img_b64 = _make_png_base64()
        saved = sd.save_images([img_b64], positive="a cat", mode="txt2img")
        filepath = Path(saved[0]["path"])
        thumb_path = filepath.parent / "thumbs" / f"{filepath.stem}.jpg"
        assert thumb_path.exists()
        with Image.open(thumb_path) as thumb:
            assert thumb.format == "JPEG"
            assert max(thumb.size) <= 200

    def test_save_images_multiple_images_indexed(self, sd, tmp_path):
        images = [_make_png_base64(), _make_png_base64(color=(0, 0, 0))]
        saved = sd.save_images(images, positive="a cat", mode="txt2img")
        assert len(saved) == 2
        assert saved[0]["index"] == 0
        assert saved[1]["index"] == 1
        assert saved[0]["filename"].endswith("_000.png")
        assert saved[1]["filename"].endswith("_001.png")

    def test_save_images_img2img_mode_prefix_and_denoising(self, sd, tmp_path):
        img_b64 = _make_png_base64()
        saved = sd.save_images([img_b64], positive="a cat", mode="img2img", denoising_strength=0.6)
        assert Path(saved[0]["path"]).name.startswith("i2i_")
        date_dir = Path(saved[0]["path"]).parent
        metadata_file = next(date_dir.glob("i2i_*_metadata.json"))
        with open(metadata_file, encoding="utf-8") as f:
            metadata = json.load(f)
        assert metadata["parameters"]["denoising_strength"] == 0.6

        with Image.open(saved[0]["path"]) as img:
            params = img.info.get("parameters")
        assert "Denoising strength: 0.6" in params

    def test_save_images_inpaint_mode_prefix(self, sd, tmp_path):
        img_b64 = _make_png_base64()
        saved = sd.save_images([img_b64], positive="a cat", mode="inpaint", denoising_strength=0.8)
        assert Path(saved[0]["path"]).name.startswith("inp_")

    def test_save_images_returns_empty_list_on_error(self, sd, tmp_path, monkeypatch):
        # 不正な Base64 を渡してデコードエラーを発生させる
        result = sd.save_images(["not-valid-base64!!!"], positive="a cat")
        assert result == []


# ------------------------------------------------------------------ #
# read_png_metadata
# ------------------------------------------------------------------ #


class TestSDClientReadPngMetadata:
    def test_read_png_metadata_returns_parsed_dict(self, sd, tmp_path):
        raw = "a cat\nNegative prompt: dog\nSteps: 10, Sampler: Euler a, CFG scale: 7, Seed: 1, Size: 256x256"
        filepath = tmp_path / "test.png"
        info = PngInfo()
        info.add_text("parameters", raw)
        Image.new("RGB", (4, 4)).save(filepath, "PNG", pnginfo=info)

        result = sd.read_png_metadata(str(filepath))
        assert result == parse_a1111_parameters(raw)
        assert result["positive_prompt"] == "a cat"
        assert result["steps"] == 10

    def test_read_png_metadata_returns_none_without_parameters(self, sd, tmp_path):
        filepath = tmp_path / "plain.png"
        Image.new("RGB", (4, 4)).save(filepath, "PNG")
        assert sd.read_png_metadata(str(filepath)) is None

    def test_read_png_metadata_returns_none_on_missing_file(self, sd, tmp_path):
        assert sd.read_png_metadata(str(tmp_path / "does_not_exist.png")) is None


# ------------------------------------------------------------------ #
# parse_a1111_parameters
# ------------------------------------------------------------------ #


class TestParseA1111Parameters:
    def test_simple_positive_prompt_only(self):
        raw = "a cat sitting on a chair"
        result = parse_a1111_parameters(raw)
        assert result["positive_prompt"] == "a cat sitting on a chair"
        assert result["raw"] == raw
        assert "negative_prompt" not in result
        assert "extras" not in result

    def test_positive_negative_and_settings(self):
        raw = "a cat\nNegative prompt: dog, ugly\nSteps: 15, Sampler: DDIM, CFG scale: 6.5, Seed: 999"
        result = parse_a1111_parameters(raw)
        assert result["positive_prompt"] == "a cat"
        assert result["negative_prompt"] == "dog, ugly"
        assert result["steps"] == 15
        assert result["sampler"] == "DDIM"
        assert result["cfg_scale"] == 6.5
        assert result["seed"] == 999

    def test_multiline_prompts(self):
        raw = (
            "a beautiful landscape\n"
            "mountains, rivers, sunset\n"
            "Negative prompt: blurry\nlow quality\n"
            "Steps: 30, Sampler: Euler a, CFG scale: 8, Seed: 1"
        )
        result = parse_a1111_parameters(raw)
        assert result["positive_prompt"] == "a beautiful landscape\nmountains, rivers, sunset"
        assert result["negative_prompt"] == "blurry\nlow quality"

    def test_all_known_parameter_types(self):
        raw = (
            "a cat\n"
            "Steps: 25, Sampler: DPM++ 2M Karras, CFG scale: 7.5, Seed: 12345, "
            "Size: 640x960, Model: sd_xl_base, LoRA: lora1:1.0, Denoising strength: 0.65"
        )
        result = parse_a1111_parameters(raw)
        assert result["steps"] == 25 and isinstance(result["steps"], int)
        assert result["sampler"] == "DPM++ 2M Karras"
        assert result["cfg_scale"] == 7.5 and isinstance(result["cfg_scale"], float)
        assert result["seed"] == 12345 and isinstance(result["seed"], int)
        assert result["width"] == 640
        assert result["height"] == 960
        assert result["model"] == "sd_xl_base"
        assert result["loras"] == "lora1:1.0"
        assert result["denoising_strength"] == 0.65 and isinstance(result["denoising_strength"], float)

    def test_quoted_value_with_escaped_quotes(self):
        raw = 'a cat\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1, Model: "sd_xl \\"turbo\\""'
        result = parse_a1111_parameters(raw)
        assert result["model"] == 'sd_xl "turbo"'

    def test_quoted_value_preserves_commas(self):
        raw = 'a cat\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1, LoRA: "lora1:1.0, lora2:0.8"'
        result = parse_a1111_parameters(raw)
        assert result["loras"] == "lora1:1.0, lora2:0.8"

    def test_unknown_parameters_go_to_extras(self):
        raw = (
            "a cat\nSteps: 20, Sampler: Euler a, CFG scale: 7, Seed: 1, "
            "Model hash: abc123, Clip skip: 2, Version: v1.7.0"
        )
        result = parse_a1111_parameters(raw)
        assert result["extras"]["Model hash"] == "abc123"
        assert result["extras"]["Clip skip"] == "2"
        assert result["extras"]["Version"] == "v1.7.0"

    def test_missing_settings_line(self):
        raw = "just a prompt\nwith multiple lines\nbut no settings"
        result = parse_a1111_parameters(raw)
        assert result["positive_prompt"] == raw
        assert set(result.keys()) == {"positive_prompt", "raw"}

    def test_missing_settings_line_with_negative_prompt(self):
        raw = "a cat\nNegative prompt: dog"
        result = parse_a1111_parameters(raw)
        assert result["positive_prompt"] == "a cat"
        assert result["negative_prompt"] == "dog"
        assert "steps" not in result
