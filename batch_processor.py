"""
batch_processor.py — Batch image processing and folder-watch mode.

Usage (via main.py CLI):
    python main.py --input-dir ./images --output-dir ./outputs --format json
    python main.py --input-dir ./images --watch
"""

import json
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tqdm import tqdm

import history as hist
from llm_client import LLMClient
from prompt_generator import PromptGenerator

# Supported image extensions
IMAGE_EXTENSIONS: Tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
OUTPUT_FORMATS: Tuple[str, ...] = ("json", "txt", "both")

# How long (seconds) a file's size must be stable before processing in watch mode
_STABLE_WAIT_SEC: float = 1.5
_STABLE_POLL_INTERVAL: float = 0.5


def _is_image(path: Path) -> bool:
    """Return True if *path* has a supported image extension."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def scan_directory(input_dir: Path, recursive: bool = False) -> List[Path]:
    """Return a sorted list of image file paths found in *input_dir*.

    Args:
        input_dir: Directory to scan.
        recursive: When True, also scan sub-directories.

    Returns:
        Sorted list of image ``Path`` objects.
    """
    if recursive:
        paths = [p for p in input_dir.rglob("*") if p.is_file() and _is_image(p)]
    else:
        paths = [p for p in input_dir.iterdir() if p.is_file() and _is_image(p)]
    return sorted(paths)


def _output_stem(image_path: Path, input_dir: Path) -> str:
    """Derive a unique, flat output file stem from an image path.

    For images inside sub-directories the path segments are joined with ``__``
    so that the output directory stays flat and collision-free.

    Example:
        input_dir = /images
        image_path = /images/sub/cat.jpg  →  stem = "sub__cat"
    """
    try:
        rel = image_path.relative_to(input_dir)
    except ValueError:
        rel = Path(image_path.name)
    parts = list(rel.with_suffix("").parts)
    return "__".join(parts)


def _validate_output_format(fmt: str) -> None:
    """Raise ``ValueError`` when *fmt* is not a supported output format."""
    if fmt not in OUTPUT_FORMATS:
        allowed = ", ".join(OUTPUT_FORMATS)
        raise ValueError(f"Unsupported output format: {fmt!r}. Expected one of: {allowed}.")


def _output_paths_for_format(output_dir: Path, stem: str, fmt: str) -> List[Path]:
    """Return the output file paths required for *fmt*."""
    _validate_output_format(fmt)
    paths: List[Path] = []
    if fmt in ("json", "both"):
        paths.append(output_dir / f"{stem}.json")
    if fmt in ("txt", "both"):
        paths.append(output_dir / f"{stem}.txt")
    return paths


def _save_outputs(
    result: Dict,
    output_dir: Path,
    stem: str,
    fmt: str,
) -> List[Path]:
    """Persist *result* to *output_dir* in the requested *fmt*.

    Args:
        result: Processing result dict with at least ``prompt_text`` key.
        output_dir: Directory where files are written.
        stem: Base file name (without extension).
        fmt: ``"json"``, ``"txt"``, or ``"both"``.

    Returns:
        List of ``Path`` objects that were written.
    """
    _validate_output_format(fmt)
    output_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []

    if fmt in ("json", "both"):
        json_path = output_dir / f"{stem}.json"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        # Remove execute permissions (security: watch mode)
        json_path.chmod(json_path.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        written.append(json_path)

    if fmt in ("txt", "both"):
        txt_path = output_dir / f"{stem}.txt"
        txt_path.write_text(result.get("prompt_text", ""), encoding="utf-8")
        txt_path.chmod(txt_path.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        written.append(txt_path)

    return written


def process_single_image(
    image_path: Path,
    input_dir: Path,
    output_dir: Path,
    prompt_generator: PromptGenerator,
    model_name: str,
    fmt: str = "json",
    skip_existing: bool = False,
) -> Dict:
    """Generate a prompt for one image and save the result.

    Args:
        image_path: Path to the source image file.
        input_dir: Root input directory (used to compute a relative stem).
        output_dir: Directory where output files are written.
        prompt_generator: An initialised ``PromptGenerator`` instance.
        model_name: LLM model identifier to record in the output.
        fmt: Output format — ``"json"``, ``"txt"``, or ``"both"``.
        skip_existing: When True, return early if the output file already exists.

    Returns:
        A result dict with keys: ``image_filename``, ``prompt_text``,
        ``model_used``, ``timestamp``, ``processing_time_ms``, ``metadata``,
        and optionally ``error`` / ``skipped``.
    """
    stem = _output_stem(image_path, input_dir)
    _validate_output_format(fmt)

    # Skip check
    if skip_existing:
        output_paths = _output_paths_for_format(output_dir, stem, fmt)
        if output_paths and all(path.exists() for path in output_paths):
            return {
                "image_filename": image_path.name,
                "skipped": True,
                "output_stem": stem,
                "existing_outputs": [str(path) for path in output_paths],
            }

    start_ms = time.time() * 1000
    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        image_bytes = image_path.read_bytes()
    except OSError as exc:
        error_msg = f"Cannot read file: {exc}"
        hist.save_batch_result(
            image_filename=image_path.name,
            status="error",
            error=error_msg,
        )
        return {
            "image_filename": image_path.name,
            "error": error_msg,
            "status": "error",
        }

    try:
        gen_result = prompt_generator.generate_prompts(image_bytes)
    except Exception as exc:
        error_msg = str(exc)
        hist.save_batch_result(
            image_filename=image_path.name,
            status="error",
            error=error_msg,
        )
        return {
            "image_filename": image_path.name,
            "error": error_msg,
            "status": "error",
        }

    if gen_result.get("status") == "error":
        error_msg = gen_result.get("error", "Unknown error")
        hist.save_batch_result(
            image_filename=image_path.name,
            status="error",
            error=error_msg,
        )
        return {
            "image_filename": image_path.name,
            "error": error_msg,
            "status": "error",
        }

    elapsed_ms = round(time.time() * 1000 - start_ms)

    positive = gen_result.get("positive", "")
    negative = gen_result.get("negative", "")
    prompt_text = positive
    if negative:
        prompt_text += f"\n\nNegative: {negative}"

    result: Dict = {
        "image_filename": image_path.name,
        "prompt_text": prompt_text,
        "positive": positive,
        "negative": negative,
        "model_used": model_name,
        "timestamp": timestamp,
        "processing_time_ms": elapsed_ms,
        "metadata": {
            "source_path": str(image_path),
            "file_size_bytes": len(image_bytes),
        },
        "status": "success",
    }

    _save_outputs(result, output_dir, stem, fmt)

    hist.save_batch_result(
        image_filename=image_path.name,
        status="success",
        positive=positive,
        negative=negative,
    )

    return result


class BatchProcessor:
    """Orchestrates batch prompt generation for a set of image directories.

    Args:
        llm_client: An initialised ``LLMClient`` (shared across threads;
                    ``requests.Session`` is **not** used so this is safe).
        concurrency: Maximum number of worker threads (default 1).
    """

    def __init__(self, llm_client: LLMClient, concurrency: int = 1) -> None:
        self.llm_client = llm_client
        self.concurrency = max(1, concurrency)
        self.model_name: str = llm_client.model
        # PromptGenerator is stateless (no mutable shared state) so it is
        # safe to share across threads.
        self._generator = PromptGenerator(llm_client)

    def run(
        self,
        input_dirs: List[Path],
        output_dir: Path,
        fmt: str = "json",
        recursive: bool = False,
        skip_existing: bool = False,
    ) -> List[Dict]:
        """Process all images in *input_dirs* and return a list of results.

        Args:
            input_dirs: List of directories to scan for images.
            output_dir: Root directory where results are saved.
            fmt: Output format — ``"json"``, ``"txt"``, or ``"both"``.
            recursive: Scan sub-directories when True.
            skip_existing: Skip images that already have output files.

        Returns:
            List of per-image result dicts.
        """
        _validate_output_format(fmt)

        # Collect (image_path, input_dir) pairs
        tasks: List[Tuple[Path, Path]] = []
        for d in input_dirs:
            images = scan_directory(d, recursive=recursive)
            tasks.extend((img, d) for img in images)

        if not tasks:
            print("No images found.")
            return []

        results: List[Dict] = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {
                executor.submit(
                    process_single_image,
                    img,
                    root,
                    output_dir,
                    self._generator,
                    self.model_name,
                    fmt,
                    skip_existing,
                ): img
                for img, root in tasks
            }

            with tqdm(total=len(futures), desc="Processing images", unit="img") as pbar:
                for future in as_completed(futures):
                    img_path = futures[future]
                    try:
                        res = future.result()
                    except Exception as exc:
                        res = {
                            "image_filename": img_path.name,
                            "error": str(exc),
                            "status": "error",
                        }
                    results.append(res)
                    pbar.update(1)

        success = sum(1 for r in results if r.get("status") == "success")
        skipped = sum(1 for r in results if r.get("skipped"))
        failed = sum(1 for r in results if r.get("status") == "error")
        print(
            f"\nDone — {success} succeeded, {skipped} skipped, {failed} failed "
            f"(total {len(results)})."
        )
        return results

    def watch(
        self,
        input_dirs: List[Path],
        output_dir: Path,
        fmt: str = "json",
        recursive: bool = False,
        skip_existing: bool = False,
    ) -> None:
        """Start watching *input_dirs* for new image files.

        New files are processed only after their size has been stable for
        ``_STABLE_WAIT_SEC`` seconds to avoid reading partially-written files.

        Press Ctrl+C to stop.

        Args:
            input_dirs: Directories to watch.
            output_dir: Root directory where results are saved.
            fmt: Output format — ``"json"``, ``"txt"``, or ``"both"``.
            recursive: Watch sub-directories when True.
            skip_existing: Skip images that already have output files.
        """
        try:
            from watchdog.events import FileSystemEventHandler, FileCreatedEvent
            from watchdog.observers import Observer
        except ImportError as exc:
            raise ImportError(
                "watchdog is required for watch mode. "
                "Install it with: pip install watchdog"
            ) from exc

        processor = self
        _pending_lock = threading.Lock()
        _pending: Dict[str, float] = {}  # path → last-seen mtime

        class _Handler(FileSystemEventHandler):
            def on_created(self, event: FileCreatedEvent) -> None:
                if event.is_directory:
                    return
                path = Path(event.src_path)
                if not _is_image(path):
                    return
                with _pending_lock:
                    _pending[str(path)] = time.time()

        def _worker() -> None:
            """Poll _pending and process files whose size has stabilized."""
            while True:
                time.sleep(_STABLE_POLL_INTERVAL)
                now = time.time()

                # Collect candidates whose wait time has elapsed (under lock).
                candidates: List[str] = []
                with _pending_lock:
                    for path_str, enqueued_at in list(_pending.items()):
                        if now - enqueued_at >= _STABLE_WAIT_SEC:
                            candidates.append(path_str)

                # Perform the size-stability check outside the lock so that
                # the sleep does not block other threads from enqueueing files.
                ready: List[str] = []
                for path_str in candidates:
                    p = Path(path_str)
                    if not p.exists():
                        with _pending_lock:
                            _pending.pop(path_str, None)
                        continue
                    size_a = p.stat().st_size
                    time.sleep(_STABLE_POLL_INTERVAL)
                    if not p.exists():
                        with _pending_lock:
                            _pending.pop(path_str, None)
                        continue
                    size_b = p.stat().st_size
                    if size_a == size_b:
                        ready.append(path_str)
                        with _pending_lock:
                            _pending.pop(path_str, None)

                for path_str in ready:
                    img_path = Path(path_str)
                    # Find the closest matching input_dir
                    root = input_dirs[0]
                    for d in input_dirs:
                        try:
                            img_path.relative_to(d)
                            root = d
                            break
                        except ValueError:
                            pass
                    print(f"[watch] Processing: {img_path.name}")
                    res = process_single_image(
                        image_path=img_path,
                        input_dir=root,
                        output_dir=output_dir,
                        prompt_generator=processor._generator,
                        model_name=processor.model_name,
                        fmt=fmt,
                        skip_existing=skip_existing,
                    )
                    if res.get("status") == "success":
                        print(f"[watch] ✓ {img_path.name}")
                    elif res.get("skipped"):
                        print(f"[watch] — skipped: {img_path.name}")
                    else:
                        print(f"[watch] ✗ {img_path.name}: {res.get('error')}")

        observer = Observer()
        handler = _Handler()
        for d in input_dirs:
            observer.schedule(handler, str(d), recursive=recursive)
        observer.start()

        worker_thread = threading.Thread(target=_worker, daemon=True)
        worker_thread.start()

        dir_list = ", ".join(str(d) for d in input_dirs)
        print(f"[watch] Watching: {dir_list}  (Ctrl+C to stop)")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[watch] Stopping…")
        finally:
            observer.stop()
            observer.join()
