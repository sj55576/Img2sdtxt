"""
tests/test_batch_processing.py

batch_processor の単体テスト。
LLM サーバーへの実接続は不要 — PromptGenerator と LLMClient をモックで置き換える。
"""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import shutil

# テスト用ダミー PNG（1x1 ピクセル、最小サイズ）
_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
    b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _write_test_images(directory: Path, count: int = 3) -> list:
    """テスト用ダミー PNG を directory に count 枚作成し、パスリストを返す。"""
    paths = []
    for i in range(count):
        p = directory / f"test_image_{i}.png"
        p.write_bytes(_MINIMAL_PNG)
        paths.append(p)
    return paths


class TestScanDirectory(unittest.TestCase):
    """scan_directory の動作確認。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_finds_png_files(self):
        from batch_processor import scan_directory
        _write_test_images(self.tmpdir, 3)
        result = scan_directory(self.tmpdir)
        self.assertEqual(len(result), 3)

    def test_recursive_finds_subdir_files(self):
        from batch_processor import scan_directory
        subdir = self.tmpdir / "sub"
        subdir.mkdir()
        _write_test_images(self.tmpdir, 2)
        _write_test_images(subdir, 1)
        result = scan_directory(self.tmpdir, recursive=True)
        self.assertEqual(len(result), 3)

    def test_non_recursive_excludes_subdirs(self):
        from batch_processor import scan_directory
        subdir = self.tmpdir / "sub"
        subdir.mkdir()
        _write_test_images(self.tmpdir, 2)
        _write_test_images(subdir, 1)
        result = scan_directory(self.tmpdir, recursive=False)
        self.assertEqual(len(result), 2)

    def test_empty_directory_returns_empty(self):
        from batch_processor import scan_directory
        result = scan_directory(self.tmpdir)
        self.assertEqual(result, [])


class TestProcessSingleImage(unittest.TestCase):
    """process_single_image の動作確認（LLM をモック化）。"""

    def setUp(self):
        self.input_dir = Path(tempfile.mkdtemp())
        self.output_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.input_dir, ignore_errors=True)
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def _make_mock_prompt_gen(self, positive: str = "test positive", negative: str = "test negative"):
        mock_gen = MagicMock()
        mock_gen.generate_prompts.return_value = {
            "positive": positive,
            "negative": negative,
            "status": "success",
        }
        return mock_gen

    @patch("batch_processor.PromptGenerator")
    @patch("batch_processor.LLMClient")
    def test_json_output_created(self, mock_llm_cls, mock_pg_cls):
        mock_pg_cls.return_value = self._make_mock_prompt_gen()
        mock_llm_cls.return_value = MagicMock()

        from batch_processor import process_single_image
        img_path = self.input_dir / "img.png"
        img_path.write_bytes(_MINIMAL_PNG)

        result = process_single_image(img_path, self.output_dir, fmt="json")

        self.assertEqual(result["status"], "success")
        json_file = self.output_dir / "img.json"
        self.assertTrue(json_file.exists(), "JSON 出力ファイルが生成されていません")

        data = json.loads(json_file.read_text(encoding="utf-8"))
        self.assertEqual(data["image_filename"], "img.png")
        self.assertIn("prompt_text", data)
        self.assertIn("timestamp", data)
        self.assertIn("processing_time_ms", data)
        self.assertIn("model_used", data)
        self.assertIn("metadata", data)

    @patch("batch_processor.PromptGenerator")
    @patch("batch_processor.LLMClient")
    def test_txt_output_created(self, mock_llm_cls, mock_pg_cls):
        mock_pg_cls.return_value = self._make_mock_prompt_gen(positive="hello world")
        mock_llm_cls.return_value = MagicMock()

        from batch_processor import process_single_image
        img_path = self.input_dir / "img2.png"
        img_path.write_bytes(_MINIMAL_PNG)

        result = process_single_image(img_path, self.output_dir, fmt="txt")

        self.assertEqual(result["status"], "success")
        txt_file = self.output_dir / "img2.txt"
        self.assertTrue(txt_file.exists(), "TXT 出力ファイルが生成されていません")
        self.assertEqual(txt_file.read_text(encoding="utf-8"), "hello world")

    @patch("batch_processor.PromptGenerator")
    @patch("batch_processor.LLMClient")
    def test_both_format_creates_two_files(self, mock_llm_cls, mock_pg_cls):
        mock_pg_cls.return_value = self._make_mock_prompt_gen()
        mock_llm_cls.return_value = MagicMock()

        from batch_processor import process_single_image
        img_path = self.input_dir / "img3.png"
        img_path.write_bytes(_MINIMAL_PNG)

        result = process_single_image(img_path, self.output_dir, fmt="both")

        self.assertEqual(result["status"], "success")
        self.assertTrue((self.output_dir / "img3.json").exists())
        self.assertTrue((self.output_dir / "img3.txt").exists())

    @patch("batch_processor.PromptGenerator")
    @patch("batch_processor.LLMClient")
    def test_no_execute_permission_on_output(self, mock_llm_cls, mock_pg_cls):
        """出力ファイルに実行権限が付与されていないことを確認する。"""
        mock_pg_cls.return_value = self._make_mock_prompt_gen()
        mock_llm_cls.return_value = MagicMock()

        from batch_processor import process_single_image
        img_path = self.input_dir / "img_perm.png"
        img_path.write_bytes(_MINIMAL_PNG)

        process_single_image(img_path, self.output_dir, fmt="both")

        for suffix in (".json", ".txt"):
            out_path = self.output_dir / f"img_perm{suffix}"
            if out_path.exists():
                # 実行ビット（所有者/グループ/その他）がすべてゼロであること
                self.assertEqual(
                    out_path.stat().st_mode & 0o111, 0,
                    f"{out_path.name} に実行権限が付与されています",
                )

    @patch("batch_processor.PromptGenerator")
    @patch("batch_processor.LLMClient")
    def test_skip_existing(self, mock_llm_cls, mock_pg_cls):
        mock_pg_cls.return_value = self._make_mock_prompt_gen()
        mock_llm_cls.return_value = MagicMock()

        from batch_processor import process_single_image
        img_path = self.input_dir / "img_skip.png"
        img_path.write_bytes(_MINIMAL_PNG)

        # 既存の JSON 出力を作成
        (self.output_dir / "img_skip.json").write_text("{}", encoding="utf-8")

        result = process_single_image(img_path, self.output_dir, fmt="json", skip_existing=True)
        self.assertEqual(result["status"], "skipped")

    @patch("batch_processor.PromptGenerator")
    @patch("batch_processor.LLMClient")
    def test_error_handling(self, mock_llm_cls, mock_pg_cls):
        mock_pg = MagicMock()
        mock_pg.generate_prompts.side_effect = RuntimeError("LLM connection failed")
        mock_pg_cls.return_value = mock_pg
        mock_llm_cls.return_value = MagicMock()

        from batch_processor import process_single_image
        img_path = self.input_dir / "img_err.png"
        img_path.write_bytes(_MINIMAL_PNG)

        result = process_single_image(img_path, self.output_dir, fmt="json")
        self.assertEqual(result["status"], "error")
        self.assertIn("error", result)


class TestRunBatch(unittest.TestCase):
    """run_batch が3枚の画像を正しく処理し出力を生成することを確認する。"""

    def setUp(self):
        self.input_dir = Path(tempfile.mkdtemp())
        self.output_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.input_dir, ignore_errors=True)
        shutil.rmtree(self.output_dir, ignore_errors=True)

    @patch("batch_processor.PromptGenerator")
    @patch("batch_processor.LLMClient")
    def test_batch_processes_three_images(self, mock_llm_cls, mock_pg_cls):
        mock_pg = MagicMock()
        mock_pg.generate_prompts.return_value = {
            "positive": "sample positive",
            "negative": "sample negative",
            "status": "success",
        }
        mock_pg_cls.return_value = mock_pg
        mock_llm_cls.return_value = MagicMock()

        images = _write_test_images(self.input_dir, 3)

        from batch_processor import run_batch
        results = run_batch(
            input_dirs=[self.input_dir],
            output_dir=self.output_dir,
            fmt="json",
            concurrency=1,
        )

        self.assertEqual(len(results), 3)
        for res in results:
            self.assertEqual(res.get("status"), "success")

        json_files = list(self.output_dir.glob("*.json"))
        self.assertEqual(len(json_files), 3)

    @patch("batch_processor.PromptGenerator")
    @patch("batch_processor.LLMClient")
    def test_batch_skip_existing(self, mock_llm_cls, mock_pg_cls):
        mock_pg = MagicMock()
        mock_pg.generate_prompts.return_value = {
            "positive": "p", "negative": "n", "status": "success"
        }
        mock_pg_cls.return_value = mock_pg
        mock_llm_cls.return_value = MagicMock()

        images = _write_test_images(self.input_dir, 3)
        # 最初の1枚の出力を事前に作成
        (self.output_dir / images[0].stem).with_suffix(".json").write_text(
            "{}", encoding="utf-8"
        )

        from batch_processor import run_batch
        results = run_batch(
            input_dirs=[self.input_dir],
            output_dir=self.output_dir,
            fmt="json",
            concurrency=1,
            skip_existing=True,
        )

        skipped = [r for r in results if r.get("status") == "skipped"]
        self.assertEqual(len(skipped), 1)

    def test_batch_empty_dir(self):
        from batch_processor import run_batch
        results = run_batch(
            input_dirs=[self.input_dir],
            output_dir=self.output_dir,
        )
        self.assertEqual(results, [])


class TestHistoryBatchLog(unittest.TestCase):
    """history.save_batch_log が JSONL ファイルに書き込むことを確認する。"""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # BATCH_LOG_PATH を一時ディレクトリにリダイレクト
        import history
        self._orig = history.BATCH_LOG_PATH
        history.BATCH_LOG_PATH = self.tmpdir / "batch_log.jsonl"

    def tearDown(self):
        import history
        history.BATCH_LOG_PATH = self._orig
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_batch_log_writes_jsonl(self):
        import history
        history.save_batch_log({"image_filename": "a.png", "status": "success"})
        history.save_batch_log({"image_filename": "b.png", "status": "error", "error": "oops"})

        lines = history.BATCH_LOG_PATH.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        for line in lines:
            data = json.loads(line)
            self.assertIn("image_filename", data)
            self.assertIn("logged_at", data)

    def test_save_batch_log_thread_safe(self):
        """複数スレッドから同時書き込みしても行が混在しないことを確認する。"""
        import threading
        import history

        def writer(n: int):
            for _ in range(10):
                history.save_batch_log({"image_filename": f"img_{n}.png", "status": "success"})

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = history.BATCH_LOG_PATH.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 50)
        for line in lines:
            data = json.loads(line)  # 各行が正しい JSON であること
            self.assertIn("image_filename", data)


if __name__ == "__main__":
    unittest.main()
