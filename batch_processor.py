"""
batch_processor.py
指定ディレクトリ内の画像を一括処理し、LLM を利用してプロンプトを生成・保存する。
ウォッチモード（watchdog）での新規ファイル自動処理にも対応。
"""

import json
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from tqdm import tqdm

from config import LLM_MODEL
from llm_client import LLMClient
from prompt_generator import PromptGenerator
import history as hist

# 対応画像拡張子（小文字）
IMAGE_EXTENSIONS: set = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}

# ウォッチモードでファイルサイズ安定待機に使う設定
_STABLE_WAIT_INTERVAL: float = 0.5   # 秒: サイズチェック間隔
_STABLE_WAIT_ROUNDS: int = 3          # 連続して同じサイズが続く回数


def scan_directory(input_dir: Path, recursive: bool = False) -> List[Path]:
    """input_dir 内の画像ファイルを返す（recursive=True でサブディレクトリも含む）。"""
    input_dir = Path(input_dir)
    pattern = "**/*" if recursive else "*"
    found: List[Path] = []
    for ext in IMAGE_EXTENSIONS:
        found.extend(input_dir.glob(f"{pattern}{ext}"))
        found.extend(input_dir.glob(f"{pattern}{ext.upper()}"))
    # 重複排除して安定ソート
    return sorted(set(found))


def _output_stem(image_path: Path, output_dir: Path) -> Path:
    """画像パスに対応する出力ファイル（拡張子なし）のパスを返す。"""
    return output_dir / image_path.stem


def _output_exists(image_path: Path, output_dir: Path, fmt: str) -> bool:
    """指定フォーマットの出力ファイルがすでに存在するか確認する。"""
    stem = _output_stem(image_path, output_dir)
    if fmt in ("json", "both"):
        if stem.with_suffix(".json").exists():
            return True
    if fmt in ("txt", "both"):
        if stem.with_suffix(".txt").exists():
            return True
    return False


def _wait_for_stable_size(path: Path) -> None:
    """ファイルサイズが安定するまで待機する（書き込み中ファイルへの対応）。"""
    prev_size = -1
    stable_count = 0
    while stable_count < _STABLE_WAIT_ROUNDS:
        try:
            current_size = path.stat().st_size
        except OSError:
            time.sleep(_STABLE_WAIT_INTERVAL)
            continue
        if current_size == prev_size:
            stable_count += 1
        else:
            stable_count = 0
            prev_size = current_size
        time.sleep(_STABLE_WAIT_INTERVAL)


def process_single_image(
    image_path: Path,
    output_dir: Path,
    fmt: str = "json",
    skip_existing: bool = False,
) -> Dict:
    """単一画像を処理してプロンプトを生成・保存し、結果を dict で返す。

    スレッドごとに LLMClient / PromptGenerator を生成するため、
    マルチスレッド環境でも安全に呼び出せる。
    """
    image_path = Path(image_path)
    output_dir = Path(output_dir)

    if skip_existing and _output_exists(image_path, output_dir, fmt):
        return {"status": "skipped", "image_filename": image_path.name}

    start_time = time.time()
    try:
        # スレッドセーフのためスレッドごとにクライアントを生成
        llm_client = LLMClient()
        prompt_gen = PromptGenerator(llm_client)

        image_bytes = image_path.read_bytes()
        result = prompt_gen.generate_prompts(image_bytes)

        elapsed_ms = int((time.time() - start_time) * 1000)

        if result.get("status") == "error":
            raise RuntimeError(result.get("error", "Unknown error"))

        positive: str = result.get("positive", "")
        negative: str = result.get("negative", "")
        model_used: str = LLM_MODEL
        ts: str = datetime.now().isoformat()

        output_data: Dict = {
            "image_filename": image_path.name,
            "prompt_text": positive,
            "negative_prompt": negative,
            "model_used": model_used,
            "timestamp": ts,
            "processing_time_ms": elapsed_ms,
            "metadata": {
                "image_path": str(image_path.resolve()),
                "image_size_bytes": image_path.stat().st_size,
            },
        }

        output_dir.mkdir(parents=True, exist_ok=True)
        stem = _output_stem(image_path, output_dir)

        if fmt in ("json", "both"):
            json_path = stem.with_suffix(".json")
            json_path.write_text(
                json.dumps(output_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            # セキュリティ: 実行権限を付与しない
            os.chmod(json_path, 0o644)

        if fmt in ("txt", "both"):
            txt_path = stem.with_suffix(".txt")
            txt_path.write_text(positive, encoding="utf-8")
            os.chmod(txt_path, 0o644)

        # 成功ログを history.py に記録
        hist.save_history(
            positive=positive,
            negative=negative,
            image_name=image_path.name,
        )
        hist.save_batch_log(
            {
                "image_filename": image_path.name,
                "status": "success",
                "prompt_text": positive,
                "model_used": model_used,
                "timestamp": ts,
                "processing_time_ms": elapsed_ms,
            }
        )

        return {"status": "success", **output_data}

    except Exception as exc:
        elapsed_ms = int((time.time() - start_time) * 1000)
        error_str = str(exc)
        ts = datetime.now().isoformat()

        # 失敗ログを history.py に記録
        hist.save_batch_log(
            {
                "image_filename": image_path.name,
                "status": "error",
                "error": error_str,
                "timestamp": ts,
                "processing_time_ms": elapsed_ms,
            }
        )

        return {
            "status": "error",
            "image_filename": image_path.name,
            "error": error_str,
            "processing_time_ms": elapsed_ms,
        }


def run_batch(
    input_dirs: List[Path],
    output_dir: Path = Path("./outputs"),
    fmt: str = "json",
    recursive: bool = False,
    concurrency: int = 1,
    skip_existing: bool = False,
) -> List[Dict]:
    """複数ディレクトリ内の画像を一括処理する。

    Args:
        input_dirs: 処理対象ディレクトリのリスト
        output_dir: 出力先ディレクトリ（デフォルト ./outputs）
        fmt: 出力フォーマット "json" | "txt" | "both"
        recursive: サブディレクトリを再帰的に処理するか
        concurrency: 同時実行数（デフォルト 1）
        skip_existing: 既に出力ファイルがある画像をスキップするか

    Returns:
        各画像の処理結果 dict のリスト
    """
    output_dir = Path(output_dir)
    all_images: List[Path] = []
    for d in input_dirs:
        all_images.extend(scan_directory(Path(d), recursive=recursive))

    if not all_images:
        print("処理対象の画像が見つかりませんでした。")
        return []

    results: List[Dict] = []
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as executor:
        futures = {
            executor.submit(
                process_single_image, img, output_dir, fmt, skip_existing
            ): img
            for img in all_images
        }
        with tqdm(total=len(futures), desc="処理中", unit="img") as pbar:
            for future in as_completed(futures):
                img_path = futures[future]
                try:
                    res = future.result()
                except Exception as exc:
                    res = {
                        "status": "error",
                        "image_filename": img_path.name,
                        "error": str(exc),
                    }
                results.append(res)

                status = res.get("status", "?")
                pbar.set_postfix_str(f"{img_path.name} [{status}]")
                pbar.update(1)

    # サマリー表示
    success = sum(1 for r in results if r.get("status") == "success")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    failed = sum(1 for r in results if r.get("status") == "error")
    print(
        f"\n完了: {len(all_images)} 件中 成功={success} スキップ={skipped} 失敗={failed}"
    )
    return results


# --------------------------------------------------------------------------- #
# Watch mode
# --------------------------------------------------------------------------- #

class _ImageEventHandler:
    """watchdog イベントハンドラ（watchdog 非依存の内部ロジック）。"""

    def __init__(
        self,
        output_dir: Path,
        fmt: str,
        skip_existing: bool,
        executor: ThreadPoolExecutor,
    ) -> None:
        self.output_dir = output_dir
        self.fmt = fmt
        self.skip_existing = skip_existing
        self.executor = executor
        self._processing: set = set()
        self._lock = threading.Lock()

    def handle_new_file(self, src_path: str) -> None:
        p = Path(src_path)
        if p.suffix.lower() not in IMAGE_EXTENSIONS:
            return
        with self._lock:
            if src_path in self._processing:
                return
            self._processing.add(src_path)
        self.executor.submit(self._deferred_process, p)

    def _deferred_process(self, p: Path) -> None:
        try:
            _wait_for_stable_size(p)
            res = process_single_image(p, self.output_dir, self.fmt, self.skip_existing)
            status = res.get("status", "?")
            print(f"[watch] {p.name} -> {status}")
        finally:
            with self._lock:
                self._processing.discard(str(p))


def run_watch(
    input_dirs: List[Path],
    output_dir: Path = Path("./outputs"),
    fmt: str = "json",
    recursive: bool = False,
    concurrency: int = 1,
    skip_existing: bool = False,
) -> None:
    """ディレクトリを監視し、新規画像が追加されたら自動処理する。

    Ctrl+C で停止。
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler as WatchdogFileSystemEventHandler
    except ImportError:
        raise ImportError(
            "watchdog がインストールされていません。"
            "`pip install watchdog` を実行してください。"
        )

    output_dir = Path(output_dir)
    executor = ThreadPoolExecutor(max_workers=max(1, concurrency))
    handler_core = _ImageEventHandler(output_dir, fmt, skip_existing, executor)

    class _WDHandler(WatchdogFileSystemEventHandler):
        def __init__(self, core: _ImageEventHandler) -> None:
            super().__init__()
            self._core = core

        def on_created(self, event):  # type: ignore[override]
            if not event.is_directory:
                self._core.handle_new_file(event.src_path)

        def on_moved(self, event):  # type: ignore[override]
            if not event.is_directory:
                self._core.handle_new_file(event.dest_path)

    observer = Observer()
    for d in input_dirs:
        d = Path(d)
        if not d.exists():
            print(f"警告: ディレクトリが存在しません: {d}")
            continue
        observer.schedule(_WDHandler(handler_core), str(d), recursive=recursive)
        print(f"監視中: {d}")

    observer.start()
    print("ウォッチモード開始。Ctrl+C で停止します。")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        executor.shutdown(wait=True)
        print("ウォッチモード終了。")
