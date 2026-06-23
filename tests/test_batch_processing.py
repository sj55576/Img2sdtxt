"""tests/test_batch_processing.py — Unit tests for batch_processor.py.

Uses minimal 1×1 pixel PNG images (generated in-memory with Pillow) and a
stubbed LLMClient so no real LLM server is required.
"""

import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the project root is on the path when running from the tests/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

import batch_processor
from batch_processor import (
    BatchProcessor,
    _output_stem,
    _output_paths_for_format,
    _validate_output_format,
    process_single_image,
    scan_directory,
)
from llm_client import LLMClient
from prompt_generator import PromptGenerator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_png_bytes() -> bytes:
    """Return the raw bytes of a tiny 1×1 red PNG."""
    buf = BytesIO()
    Image.new("RGB", (1, 1), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _stub_generate_prompts(image_bytes, **kwargs):  # noqa: ARG001
    """Stub for PromptGenerator.generate_prompts that returns a fixed result."""
    return {
        "positive": "1girl, red background, simple",
        "negative": "low quality, blurry",
        "status": "success",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScanDirectory(unittest.TestCase):
    """scan_directory() returns the right files."""

    def test_non_recursive(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(_make_png_bytes())
            (root / "b.png").write_bytes(_make_png_bytes())
            (root / "c.txt").write_text("not an image")
            sub = root / "sub"
            sub.mkdir()
            (sub / "d.webp").write_bytes(_make_png_bytes())

            found = scan_directory(root, recursive=False)
            names = [p.name for p in found]
            self.assertIn("a.jpg", names)
            self.assertIn("b.png", names)
            self.assertNotIn("c.txt", names)
            self.assertNotIn("d.webp", names)  # sub-dir not included

    def test_recursive(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "a.jpg").write_bytes(_make_png_bytes())
            sub = root / "sub"
            sub.mkdir()
            (sub / "d.webp").write_bytes(_make_png_bytes())

            found = scan_directory(root, recursive=True)
            names = [p.name for p in found]
            self.assertIn("a.jpg", names)
            self.assertIn("d.webp", names)


class TestOutputStem(unittest.TestCase):
    """_output_stem() produces the expected flat stem."""

    def test_top_level_file(self):
        root = Path("/images")
        img = Path("/images/cat.jpg")
        self.assertEqual(_output_stem(img, root), "cat")


class TestOutputFormatHelpers(unittest.TestCase):
    """Output format helpers validate and resolve required files."""

    def test_output_paths_for_both_requires_json_and_txt(self):
        out = Path("/tmp/out")
        self.assertEqual(
            _output_paths_for_format(out, "cat", "both"),
            [out / "cat.json", out / "cat.txt"],
        )

    def test_invalid_format_raises_value_error(self):
        with self.assertRaises(ValueError):
            _validate_output_format("yaml")

    def test_nested_file(self):
        root = Path("/images")
        img = Path("/images/animals/cat.jpg")
        self.assertEqual(_output_stem(img, root), "animals__cat")

    def test_outside_root_fallback(self):
        root = Path("/images")
        img = Path("/other/cat.jpg")
        self.assertEqual(_output_stem(img, root), "cat")


class TestProcessSingleImage(unittest.TestCase):
    """process_single_image() writes the expected output files."""

    def _make_processor(self) -> PromptGenerator:
        client = MagicMock(spec=LLMClient)
        client.model = "test-model"
        gen = PromptGenerator(client)
        gen.generate_prompts = MagicMock(side_effect=_stub_generate_prompts)
        return gen

    def test_json_output_created(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "input"
            root.mkdir()
            out = Path(td) / "output"
            img = root / "test.png"
            img.write_bytes(_make_png_bytes())

            gen = self._make_processor()
            result = process_single_image(
                image_path=img,
                input_dir=root,
                output_dir=out,
                prompt_generator=gen,
                model_name="test-model",
                fmt="json",
            )

            self.assertEqual(result["status"], "success")
            json_file = out / "test.json"
            self.assertTrue(json_file.exists(), "JSON output file should exist")
            data = json.loads(json_file.read_text())
            self.assertEqual(data["image_filename"], "test.png")
            self.assertIn("positive", data)
            self.assertEqual(data["model_used"], "test-model")

    def test_txt_output_created(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "input"
            root.mkdir()
            out = Path(td) / "output"
            img = root / "test.png"
            img.write_bytes(_make_png_bytes())

            gen = self._make_processor()
            result = process_single_image(
                image_path=img,
                input_dir=root,
                output_dir=out,
                prompt_generator=gen,
                model_name="test-model",
                fmt="txt",
            )

            self.assertEqual(result["status"], "success")
            txt_file = out / "test.txt"
            self.assertTrue(txt_file.exists())
            content = txt_file.read_text()
            self.assertIn("1girl", content)

    def test_skip_existing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "input"
            root.mkdir()
            out = Path(td) / "output"
            out.mkdir()
            img = root / "test.png"
            img.write_bytes(_make_png_bytes())
            # Pre-create the output file
            (out / "test.json").write_text("{}")

            gen = self._make_processor()
            result = process_single_image(
                image_path=img,
                input_dir=root,
                output_dir=out,
                prompt_generator=gen,
                model_name="test-model",
                fmt="json",
                skip_existing=True,
            )

            self.assertTrue(result.get("skipped"), "Should be skipped")
            # generate_prompts must NOT have been called
            gen.generate_prompts.assert_not_called()

    def test_skip_existing_both_requires_all_outputs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "input"
            root.mkdir()
            out = Path(td) / "output"
            out.mkdir()
            img = root / "test.png"
            img.write_bytes(_make_png_bytes())
            # Only JSON exists; "both" still needs to generate the missing TXT.
            (out / "test.json").write_text("{}")

            gen = self._make_processor()
            result = process_single_image(
                image_path=img,
                input_dir=root,
                output_dir=out,
                prompt_generator=gen,
                model_name="test-model",
                fmt="both",
                skip_existing=True,
            )

            self.assertEqual(result["status"], "success")
            self.assertTrue((out / "test.txt").exists())
            gen.generate_prompts.assert_called_once()

    def test_skip_existing_both_skips_when_all_outputs_exist(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "input"
            root.mkdir()
            out = Path(td) / "output"
            out.mkdir()
            img = root / "test.png"
            img.write_bytes(_make_png_bytes())
            (out / "test.json").write_text("{}")
            (out / "test.txt").write_text("already done")

            gen = self._make_processor()
            result = process_single_image(
                image_path=img,
                input_dir=root,
                output_dir=out,
                prompt_generator=gen,
                model_name="test-model",
                fmt="both",
                skip_existing=True,
            )

            self.assertTrue(result.get("skipped"), "Should be skipped only when all outputs exist")
            gen.generate_prompts.assert_not_called()

    def test_error_on_llm_failure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "input"
            root.mkdir()
            out = Path(td) / "output"
            img = root / "test.png"
            img.write_bytes(_make_png_bytes())

            client = MagicMock(spec=LLMClient)
            client.model = "test-model"
            gen = PromptGenerator(client)
            gen.generate_prompts = MagicMock(side_effect=Exception("LLM down"))

            result = process_single_image(
                image_path=img,
                input_dir=root,
                output_dir=out,
                prompt_generator=gen,
                model_name="test-model",
                fmt="json",
            )

            self.assertEqual(result["status"], "error")
            self.assertIn("LLM down", result["error"])


class TestBatchProcessor(unittest.TestCase):
    """BatchProcessor.run() processes multiple images correctly."""

    def _make_batch_processor(self) -> BatchProcessor:
        client = MagicMock(spec=LLMClient)
        client.model = "test-model"
        bp = BatchProcessor(client, concurrency=1)
        bp._generator.generate_prompts = MagicMock(side_effect=_stub_generate_prompts)
        return bp

    def test_three_images_produce_three_outputs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "input"
            root.mkdir()
            out = Path(td) / "output"

            # Create 3 test images
            for name in ("img1.jpg", "img2.png", "img3.webp"):
                (root / name).write_bytes(_make_png_bytes())

            bp = self._make_batch_processor()
            results = bp.run(
                input_dirs=[root],
                output_dir=out,
                fmt="json",
            )

            success = [r for r in results if r.get("status") == "success"]
            self.assertEqual(len(success), 3, "All 3 images should succeed")

            json_files = list(out.glob("*.json"))
            self.assertEqual(len(json_files), 3, "3 JSON files should be created")

    def test_skip_existing_skips_done_images(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "input"
            root.mkdir()
            out = Path(td) / "output"
            out.mkdir()

            for name in ("img1.jpg", "img2.png", "img3.webp"):
                (root / name).write_bytes(_make_png_bytes())

            # Pre-create output for img1 and img2
            (out / "img1.json").write_text("{}")
            (out / "img2.json").write_text("{}")

            bp = self._make_batch_processor()
            results = bp.run(
                input_dirs=[root],
                output_dir=out,
                fmt="json",
                skip_existing=True,
            )

            skipped = [r for r in results if r.get("skipped")]
            success = [r for r in results if r.get("status") == "success"]
            self.assertEqual(len(skipped), 2)
            self.assertEqual(len(success), 1)

    def test_both_format_creates_json_and_txt(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "input"
            root.mkdir()
            out = Path(td) / "output"
            img = root / "photo.jpg"
            img.write_bytes(_make_png_bytes())

            bp = self._make_batch_processor()
            results = bp.run(
                input_dirs=[root],
                output_dir=out,
                fmt="both",
            )

            self.assertEqual(results[0]["status"], "success")
            self.assertTrue((out / "photo.json").exists())
            self.assertTrue((out / "photo.txt").exists())


if __name__ == "__main__":
    unittest.main()
