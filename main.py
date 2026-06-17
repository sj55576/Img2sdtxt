from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import logging
import time as _time

import config
from config import (
    API_HOST, API_PORT, DEBUG,
    HTTPS_ENABLED, SSL_CERTFILE, SSL_KEYFILE,
    STYLES, TONES, QUALITY_LEVELS
)
from deps import llm_client, sd_client

from routes.prompts import router as prompts_router
from routes.history import router as history_router
from routes.sd import router as sd_router
from routes.presets import router as presets_router
from routes.gallery import router as gallery_router

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("img2sdtxt")
APP_START_TIME = _time.time()

app = FastAPI(
    title="Image to Stable Diffusion Prompt",
    description="Convert images to SD prompts using local LLM",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = _time.time()
    response = await call_next(request)
    elapsed = (_time.time() - t0) * 1000
    logger.info("%s %s %d %.1fms", request.method, request.url.path, response.status_code, elapsed)
    return response


static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

outputs_dir = Path(__file__).parent / "outputs"
outputs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/outputs", StaticFiles(directory=str(outputs_dir)), name="outputs")

# Include route modules
app.include_router(prompts_router)
app.include_router(history_router)
app.include_router(sd_router)
app.include_router(presets_router)
app.include_router(gallery_router)


# ------------------------------------------------------------------ #
# Pages
# ------------------------------------------------------------------ #

@app.get("/")
async def root():
    return FileResponse("static/index.html")


# ------------------------------------------------------------------ #
# Health / Config
# ------------------------------------------------------------------ #

@app.get("/health")
async def health():
    """Check all component status and return uptime."""
    llm_ok = await run_in_threadpool(llm_client.is_available)
    sd_ok = await run_in_threadpool(sd_client.is_available)

    overall = "ok" if llm_ok else "degraded"

    return {
        "status": overall,
        "components": {
            "llm": {
                "available": llm_ok,
                "url": config.LLM_SERVER_URL,
            },
            "sd_api": {
                "available": sd_ok,
                "url": config.SD_API_URL,
            },
        },
        "uptime_seconds": int(_time.time() - APP_START_TIME),
    }


@app.get("/api/config")
def get_config():
    from config import LLM_SERVER_URL, LLM_MODEL, SD_API_URL
    return {
        "llm_server": LLM_SERVER_URL,
        "model": LLM_MODEL,
        "sd_api": SD_API_URL,
        "styles": STYLES,
        "tones": TONES,
        "quality_levels": list(QUALITY_LEVELS.keys())
    }


# ------------------------------------------------------------------ #
# CLI / batch mode
# ------------------------------------------------------------------ #

def _run_batch_cli() -> None:
    """Parse CLI arguments and run batch or watch mode when --input-dir is given."""
    import argparse
    from batch_processor import BatchProcessor

    parser = argparse.ArgumentParser(
        prog="main.py",
        description=(
            "Img2sdtxt — Image to Stable Diffusion Prompt Generator.\n"
            "Run without --input-dir to start the web server."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input-dir",
        dest="input_dirs",
        metavar="PATH",
        action="append",
        default=None,
        help="Directory containing images to process (can be specified multiple times).",
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        metavar="PATH",
        default="./outputs",
        help="Directory where results are saved (default: ./outputs).",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode: monitor input directories and process new files automatically.",
    )
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=["json", "txt", "both"],
        default="json",
        help="Output format (default: json).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan sub-directories.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel workers (default: 1). Increase with care due to LLM rate limits.",
    )
    parser.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        help="Skip images that already have an output file.",
    )

    args, _unknown = parser.parse_known_args()

    if args.input_dirs is None:
        # No --input-dir → start the web server
        import uvicorn

        ssl_certfile = None
        ssl_keyfile = None

        if HTTPS_ENABLED:
            certfile = SSL_CERTFILE or str(Path(__file__).parent / "ssl" / "cert.pem")
            keyfile = SSL_KEYFILE or str(Path(__file__).parent / "ssl" / "key.pem")

            if not (Path(certfile).exists() and Path(keyfile).exists()):
                # Auto-generate a self-signed certificate with openssl
                import subprocess
                import shutil

                if shutil.which("openssl") is None:
                    print(
                        "[ERROR] HTTPS_ENABLED=true but 'openssl' was not found in PATH.\n"
                        "Please either:\n"
                        "  1. Install openssl (e.g. 'sudo apt install openssl' / 'brew install openssl')\n"
                        "  2. Generate a certificate manually and set SSL_CERTFILE / SSL_KEYFILE in .env\n"
                        "     openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'"
                    )
                    raise SystemExit(1)

                ssl_dir = Path(__file__).parent / "ssl"
                ssl_dir.mkdir(parents=True, exist_ok=True)

                print("[INFO] Generating self-signed certificate in ssl/ ...")
                try:
                    subprocess.run(
                        [
                            "openssl", "req", "-x509",
                            "-newkey", "rsa:4096",
                            "-keyout", str(ssl_dir / "key.pem"),
                            "-out", str(ssl_dir / "cert.pem"),
                            "-days", "365",
                            "-nodes",
                            "-subj", "/CN=localhost",
                        ],
                        check=True,
                    )
                except subprocess.CalledProcessError as exc:
                    print(
                        f"[ERROR] Failed to generate self-signed certificate (exit code {exc.returncode}).\n"
                        "To generate one manually:\n"
                        "  mkdir -p ssl\n"
                        "  openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem -out ssl/cert.pem"
                        " -days 365 -nodes -subj '/CN=localhost'\n"
                        "Then set SSL_CERTFILE and SSL_KEYFILE in .env."
                    )
                    raise SystemExit(1) from exc
                print("[INFO] Self-signed certificate generated.")

            ssl_certfile = certfile
            ssl_keyfile = keyfile
            protocol = "https"
        else:
            protocol = "http"

        host_display = "localhost" if API_HOST in ("0.0.0.0", "::") else API_HOST
        print(f"[INFO] Starting server at {protocol}://{host_display}:{API_PORT}")

        uvicorn.run(
            app,
            host=API_HOST,
            port=API_PORT,
            reload=DEBUG,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )
        return

    input_paths = [Path(d) for d in args.input_dirs]
    for p in input_paths:
        if not p.is_dir():
            parser.error(f"--input-dir '{p}' is not a valid directory.")

    output_path = Path(args.output_dir)

    processor = BatchProcessor(llm_client, concurrency=args.concurrency)

    if args.watch:
        processor.watch(
            input_dirs=input_paths,
            output_dir=output_path,
            fmt=args.fmt,
            recursive=args.recursive,
            skip_existing=args.skip_existing,
        )
    else:
        processor.run(
            input_dirs=input_paths,
            output_dir=output_path,
            fmt=args.fmt,
            recursive=args.recursive,
            skip_existing=args.skip_existing,
        )


if __name__ == "__main__":
    _run_batch_cli()
