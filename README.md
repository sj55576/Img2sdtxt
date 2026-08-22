# 🎨 Img2sdtxt — Image to Stable Diffusion Prompt Generator

A web application that analyzes images (or text descriptions) with a local LLM and generates ready-to-use Stable Diffusion prompts.  
It also integrates directly with the **AUTOMATIC1111 Stable Diffusion WebUI API** so you can generate images without leaving the app.

> ⚠️ **Work in Progress**: This repository is still under verification. Its functionality has **not** been fully tested or confirmed to work. Use at your own risk.

> 📖 **Japanese documentation**: [README-ja.md](README-ja.md)

---

## Features

| Feature | Description |
|---------|-------------|
| 📸 **Single Image → Prompt** | Upload one image to generate positive & negative prompts |
| 🧩 **Blend References** | Combine 2–3 labelled reference images into one prompt |
| 🗂️ **Batch Processing** | Upload up to 10 images and generate prompts for all at once |
| ✍️ **Text → Prompt** | Describe an image in plain text and get SD prompts |
| ✨ **Prompt Refinement** | Refine and enhance existing prompts with LLM (optional custom instruction) |
| ⚙️ **Style / Tone / Quality** | Customize output with 8 styles, 8 tones, and 3 quality levels |
| 🎨 **Presets** | 12 built-in style presets (Anime, Photorealistic, Portrait, etc.) + custom presets |
| 🖼️ **SD txt2img** | Generate images directly via the A1111 API |
| 🔄 **SD img2img** | Transform an existing image using SD |
| 🖌️ **SD Inpaint** | Inpaint selected areas of an image |
| 🌟 **Multi-Model Generation** | Generate images sequentially with multiple models from a single prompt |
| 📋 **History** | SQLite-based history with full-text search, style/quality filters, and favorites |
| ⭐ **Favorites** | Mark history entries as favorites for quick access |
| 📤 **History Export** | Download the full prompt history as a JSON file |
| 🗃️ **Gallery** | Browse, filter, and paginate generated images |
| 💾 **Parameter Persistence** | Last-used parameters are restored automatically |
| 📁 **Random Folder Load** | Pick a random image from a local folder |
| 🖥️ **CLI Batch Mode** | Process a whole directory of images from the command line |
| 👁️ **CLI Watch Mode** | Monitor a folder and auto-process new images as they arrive |
| 🧩 **Dynamic Prompts** | Expand `{a|b}` groups and `__wildcard__` files for prompt variants, including once per SD output |
| 🎛️ **ControlNet** | Configure ControlNet models, preprocessors, and reference images from the UI |
| 🧪 **A/B Comparison & XY Plot** | Compare prompt variants and Stable Diffusion parameter grids |
| ⏳ **Job Queue** | Queue generation jobs with priority, ETA, cancellation, and WebSocket updates |
| 🔌 **LLM Fallback** | Automatically switch between configured providers and record the actual provider/model |
| 📊 **Runtime Observability** | Request IDs, JSON logs, `/metrics`, cache, queue, and provider metrics |
| 🌐 **Internationalization** | Japanese and English UI translations with keyboard shortcuts |

---

## Requirements

### 1. LLM Server (choose one)

#### LM Studio
- Download: <https://lmstudio.ai>
- Load any vision-capable model (e.g. LLaVA, BakLLaVA)
- Open the **Server** tab and start the local server
- Default URL: `http://localhost:1234/v1`

#### Lemonade Server
```bash
pip install lemonade-server
lemonade-server --port 8000
```
Set `LLM_SERVER_URL=http://localhost:8000/api/v1` in `.env`.

### 2. Stable Diffusion WebUI (optional, for image generation)
- Install [AUTOMATIC1111 WebUI](https://github.com/AUTOMATIC1111/stable-diffusion-webui)
- Launch with the `--api` flag:
  ```bash
  python launch.py --api
  ```
- Default URL: `http://localhost:7860`

### 3. Python 3.10+

---

## Quick Start

### Windows
```cmd
run.bat
```

### Linux / macOS
```bash
bash run.sh
```

Both scripts automatically create a virtual environment, install dependencies, generate a default `.env`, and start the server.

---

## Manual Installation

```bash
# 1. Clone the repository
git clone https://github.com/kumakumapon/Img2sdtxt.git
cd Img2sdtxt

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create .env from template
cp .env.example .env
# Edit .env as needed

# 4. Start the application
python main.py
```

Open <http://localhost:8000> in your browser.

---

## Docker

### Quick start

```bash
cp .env.example .env
# Edit .env as needed (see below)
docker compose up -d
```

Open <http://localhost:8000> in your browser. Logs: `docker compose logs -f img2sdtxt`.

The image is built from the included `Dockerfile` (Python 3.12-slim, non-root
user, `HEALTHCHECK` on `/health`) and `docker-compose.yml` mounts `./data`,
`./outputs`, and `./ssl` as volumes so history, generated images, and TLS
certificates persist across container restarts/rebuilds.

### Connecting to your LLM server

#### Option A — Ollama in a container

Start Ollama alongside the app using the `ollama` Compose profile:

```bash
docker compose --profile ollama up -d
```

In `.env`, point the app at the Ollama service by its container name (both
services share the `img2sdtxt-net` Docker network):

```env
LLM_SERVER_URL=http://ollama:11434/v1
LLM_PROVIDER=openai_compatible
```

Then pull a vision-capable model into the running container, e.g.:

```bash
docker compose exec ollama ollama pull llava
```

#### Option B — LM Studio / A1111 / Ollama running on the host

If your LLM server (or A1111) runs directly on the host machine rather than
in a container, use `host.docker.internal` to reach it:

```env
LLM_SERVER_URL=http://host.docker.internal:1234/v1
SD_API_URL=http://host.docker.internal:7860
```

- **Docker Desktop (Mac/Windows)**: `host.docker.internal` resolves
  automatically — no extra configuration needed.
- **Linux**: `host.docker.internal` is not resolved by default, so the
  `img2sdtxt` service in `docker-compose.yml` ships with:
  ```yaml
      extra_hosts:
        - "host.docker.internal:host-gateway"
  ```
  If you run the image without Compose (`docker run`), pass
  `--add-host=host.docker.internal:host-gateway`, or use the host's
  LAN/Docker-bridge IP directly (e.g. `http://172.17.0.1:1234/v1`).

### Stable Diffusion WebUI (A1111)

Most users run A1111 on the host for direct GPU access and easier updates,
and point `SD_API_URL` at it as shown above (`--api` flag required). A
minimal, commented-out `sd-webui` service is included in
`docker-compose.yml` (behind the `sd-webui` profile) if you'd rather
containerize it yourself.

### GPU usage

To give the containerized `ollama` (or `sd-webui`) service access to an
NVIDIA GPU, install the [NVIDIA Container
Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
on the host, then uncomment the `deploy.resources.reservations.devices`
block under the relevant service in `docker-compose.yml`:

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

### Volumes / persistence

| Host path | Container path | Contents |
|-----------|-----------------|----------|
| `./data` | `/app/data` | SQLite history DB, presets, last-used parameters |
| `./outputs` | `/app/outputs` | Generated images and metadata |
| `./ssl` | `/app/ssl` | Auto-generated or provided TLS certificate/key |
| `ollama-data` (named volume) | `/root/.ollama` | Downloaded Ollama models (only with the `ollama` profile) |

### Reverse proxy

Example Nginx server block terminating TLS in front of the container:

```nginx
server {
    listen 443 ssl;
    server_name example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Equivalent Caddyfile:

```
example.com {
    reverse_proxy 127.0.0.1:8000
}
```

When running behind a reverse proxy, set `TRUST_PROXY_HEADERS=true` in
`.env` so rate limiting sees the real client IP, and leave `HTTPS_ENABLED=false`
on the container itself (the proxy handles TLS termination).

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_SERVER_URL` | `http://localhost:1234/v1` | LLM server endpoint |
| `LLM_MODEL` | `gpt-3.5-turbo` | Model name to use |
| `LLM_PROVIDER` | `openai_compatible` | Active provider (`openai_compatible`, `anthropic`, or `gemini`) |
| `LLM_CACHE_ENABLED` | `true` | Enable the persistent LLM response cache |
| `LLM_CACHE_TTL` | `3600` | Cache lifetime in seconds |
| `LLM_FALLBACK_CHAIN` | *(empty)* | Comma-separated provider IDs tried after a failure |
| `LLM_HEALTH_CHECK_INTERVAL` | `60` | Fallback-provider health check interval in seconds |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key when the provider is enabled |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Anthropic model name |
| `GEMINI_API_KEY` | *(empty)* | Google Gemini API key when the provider is enabled |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `SD_API_URL` | `http://localhost:7860` | AUTOMATIC1111 API URL |
| `API_HOST` | `127.0.0.1` | API server bind address; set `0.0.0.0` only for an intentional network deployment |
| `API_PORT` | `8000` | API server port |
| `DEBUG` | `false` | Enable debug / hot-reload |
| `LOG_LEVEL` | `INFO` | Python log level |
| `LOG_FORMAT` | `text` | Log format: `text` or `json` (JSON includes request IDs) |
| `CORS_ALLOWED_ORIGINS` | *(empty)* | Comma-separated allowed browser origins. Empty means same-origin only; never use `*` unless you understand the exposure |
| `CORS_ALLOW_CREDENTIALS` | `false` | Allow credentialed CORS requests; enable only with restricted origins |
| `API_TOKEN` | *(empty)* | Optional bearer token for backups, history export/deletion, runtime provider changes, and cache/wildcard deletion; set when exposing the API beyond localhost |
| `TRUST_PROXY_HEADERS` | `false` | Trust `X-Forwarded-For` / `X-Real-IP` only behind a trusted reverse proxy |
| `HTTPS_ENABLED` | `false` | Serve over HTTPS |
| `SSL_CERTFILE` | *(auto)* | Path to TLS certificate file (PEM) |
| `SSL_KEYFILE` | *(auto)* | Path to TLS private key file (PEM) |
| `RATE_LIMIT_ENABLED` | `true` | Enable IP-based sliding-window rate limiting |
| `RATE_LIMIT_GENERATION` | `10` | Generation requests per minute per client |
| `RATE_LIMIT_API` | `60` | Other API requests per minute per client |
| `JOB_QUEUE_MAX_SIZE` | `20` | Maximum pending generation jobs |
| `XY_PLOT_MAX_CELLS` | `36` | Maximum XY Plot cells / safe prompt variants |
| `WEBHOOK_URL` | *(empty)* | Webhook endpoint URL; empty disables notifications |
| `WEBHOOK_EVENTS` | `job_completed,job_failed,batch_completed` | Comma-separated events to notify on (`job_completed`, `job_failed`, `job_cancelled`, `batch_completed`) |
| `WEBHOOK_FORMAT` | `generic` | Payload format: `generic`, `discord`, or `slack` |
| `WEBHOOK_TIMEOUT` | `5` | Webhook request timeout in seconds |
| `BACKUP_DIR` | `data/backups` | Directory for backup archives |
| `AUTO_BACKUP_ENABLED` | `false` | Enable scheduled automatic backups |
| `AUTO_BACKUP_RETENTION` | `7` | Number of automatic backups to retain |
| `AUTO_BACKUP_INTERVAL_HOURS` | `24` | Automatic backup interval |
| `MAX_BACKUP_UPLOAD_SIZE` | `2147483648` | Maximum uploaded restore archive size in bytes |

---

## Observability

Every response includes an `X-Request-ID` header. Send an existing ID in the
same header to correlate a request with application logs; otherwise the server
generates a UUID. Set `LOG_FORMAT=json` for JSON Lines containing `ts`,
`level`, `logger`, `msg`, `request_id`, and request duration fields.

Prometheus metrics are available at `GET /metrics` (and require
`Authorization: Bearer <API_TOKEN>` when `API_TOKEN` is configured):

```yaml
scrape_configs:
  - job_name: img2sdtxt
    static_configs:
      - targets: ["localhost:8000"]
```

The endpoint exposes HTTP, LLM provider/fallback, Stable Diffusion, cache,
rate-limit, and job-queue counters/histograms/gauges. The Prometheus client
is included in `requirements.txt`.

A ready-to-import Grafana dashboard for these metrics is included at
[`docs/grafana/img2sdtxt-dashboard.json`](docs/grafana/img2sdtxt-dashboard.json)
(Dashboards → New → Import, then point it at your Prometheus data source).

### Distributed tracing (OpenTelemetry)

Tracing is disabled by default. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to an
OTLP/HTTP collector endpoint (e.g. `http://localhost:4318/v1/traces`) to
enable it:

```env
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318/v1/traces
OTEL_SERVICE_NAME=img2sdtxt
```

`OTEL_SERVICE_NAME` (default `img2sdtxt`) sets the traced service name.

When enabled, FastAPI requests and outgoing `requests` calls (Stable
Diffusion, the OpenAI-compatible LLM provider) are auto-instrumented, and
each LLM call is recorded as an `llm.generate` span with `llm.provider`,
`llm.model`, `llm.mode`, `llm.status`, and `llm.duration_seconds`
attributes. If the `opentelemetry-*` packages aren't installed, tracing is
skipped with a warning instead of failing the app.

---

## HTTPS

To enable HTTPS, set `HTTPS_ENABLED=true` in your `.env` file.

### Option 1 — Auto-generated self-signed certificate (development)

Simply set `HTTPS_ENABLED=true`. If no certificate files are found, the app
generates a self-signed certificate in `ssl/cert.pem` and `ssl/key.pem`
automatically (requires `openssl` to be installed).

```env
HTTPS_ENABLED=true
```

Then open <https://localhost:8000> in your browser.  
Your browser will show a security warning for self-signed certificates — click
**Advanced → Proceed** to continue.

### Option 2 — Bring your own certificate (production)

Point the app at your CA-signed or Let's Encrypt certificate:

```env
HTTPS_ENABLED=true
SSL_CERTFILE=/etc/letsencrypt/live/example.com/fullchain.pem
SSL_KEYFILE=/etc/letsencrypt/live/example.com/privkey.pem
```

### Generate a self-signed certificate manually

```bash
mkdir -p ssl
openssl req -x509 -newkey rsa:4096 \
  -keyout ssl/key.pem -out ssl/cert.pem \
  -days 365 -nodes -subj "/CN=localhost"
```

---

## Prompt Customization Options

### Styles
`photorealistic`, `anime`, `painting`, `watercolor`, `concept_art`, `sketch`, `pixel_art`, `3d_render`

### Tones
`natural`, `vibrant`, `warm`, `cool`, `dark`, `soft`, `dramatic`, `cinematic`

### Quality Levels
| Level | Added keywords |
|-------|----------------|
| `standard` | `best quality` |
| `high` | `best quality, masterpiece, highly detailed` |
| `ultra` | `best quality, masterpiece, highly detailed, 8k uhd, sharp focus, professional` |

---

## Built-in Presets

| Preset | Description |
|--------|-------------|
| Anime Style | Anime / manga style |
| Photorealistic | 8K photorealistic |
| Oil Painting | Classical oil painting |
| Watercolor | Soft watercolor |
| Fantasy Art | Epic fantasy concept art |
| Portrait Photo | Bokeh portrait photography |
| Realistic Portrait | Hyper-realistic face rendering |
| Fashion Photo | Editorial / Vogue-style photo |
| Cinematic Portrait | Movie-still cinematic lighting |
| Street Snap | Candid street photography |
| Studio Portrait | Professional studio headshot |
| Natural Light Portrait | Golden-hour outdoor portrait |

Custom presets can be created and saved from the **Presets** page.

---


## CLI Batch & Watch Mode

In addition to the web UI, `main.py` can be used as a command-line tool to
process entire directories of images.

### Basic batch processing

```bash
python main.py --input-dir ./my_images --output-dir ./outputs
```

### Multiple input directories

```bash
python main.py --input-dir ./photos --input-dir ./screenshots --output-dir ./out
```

### Recursive scan + TXT output

```bash
python main.py --input-dir ./images --recursive --format txt
```

### Skip already-processed images

```bash
python main.py --input-dir ./images --skip-existing
```

### Parallel processing (increase with care due to LLM rate limits)

```bash
python main.py --input-dir ./images --concurrency 3
```

### Watch mode — auto-process new files

```bash
python main.py --input-dir ./inbox --output-dir ./processed --watch
```

Drop any `jpg`, `jpeg`, `png`, `webp`, `gif`, or `bmp` image into `./inbox`
while the watcher is running and it will be processed automatically. The watcher
waits until the file size has been stable for ~1.5 s before starting, to avoid
reading partially-written files.

### All CLI options

| Option | Default | Description |
|--------|---------|-------------|
| `--input-dir PATH` | *(required)* | Input directory (repeat for multiple) |
| `--output-dir PATH` | `./outputs` | Where to save results |
| `--format {json,txt,both}` | `json` | Output format |
| `--recursive` | off | Scan sub-directories |
| `--concurrency N` | `1` | Parallel worker threads |
| `--skip-existing` | off | Skip images with existing output |
| `--watch` | off | Watch for new files instead of exiting |

> **Note:** Omit `--input-dir` entirely to start the normal web server.

---

## Backup & Restore

Everything under `data/` — prompt history, LLM cache, rate-limit state,
presets, and wildcards — can be archived into a single timestamped ZIP.

**From the UI:** open the **💾 Backup** page to create a backup, download or
delete existing ones, and restore either a stored backup or an uploaded ZIP.

**From the CLI:**

```bash
python main.py --backup ./backups/            # create (data/ only)
python main.py --backup ./backups/ --include-outputs   # also archive outputs/
python main.py --restore ./backups/img2sdtxt-backup-20260724-120000.zip
```

**Automatic backups** — set in `.env`:

```env
AUTO_BACKUP_ENABLED=true
AUTO_BACKUP_INTERVAL_HOURS=24
AUTO_BACKUP_RETENTION=7      # older backups beyond this are rotated out
#BACKUP_DIR=/path/to/backups # default: data/backups
```

Notes:

- SQLite databases are snapshotted with SQLite's online backup API, so an
  archive is consistent even if it is taken while the app is running.
- A restore creates a safety backup of the current data first (unless you
  opt out), and never deletes files that are absent from the archive.
- **Restart the server after a restore.** Modules hold their own open SQLite
  connections and keep serving pre-restore data until the process restarts.
- When `API_TOKEN` is set, backup endpoints require
  `Authorization: Bearer <API_TOKEN>`. A backup archive contains your full
  history, so always set a token and restrict access at the reverse proxy when
  exposing the app beyond localhost.

---

## Project Structure

```
Img2sdtxt/
├── main.py                  # FastAPI app, middleware, pages, health, metrics
├── config.py                # Environment configuration and option lists
├── routes/                  # API routers (prompts, SD, jobs, history, backup, etc.)
├── providers/               # Anthropic and Gemini provider adapters
├── llm_client.py            # OpenAI-compatible LLM communication
├── fallback.py              # Ordered provider fallback chain
├── prompt_generator.py      # Prompt generation and response normalization
├── sd_client.py             # Stable Diffusion API client and output metadata
├── history.py               # SQLite history, tags, versions, and A/B records
├── job_queue.py             # Async generation queue and WebSocket subscriptions
├── dynamic_prompts.py       # Wildcard / `{a|b}` expansion engine
├── metrics.py               # Prometheus instrumentation
├── logging_utils.py         # Request correlation and JSON log formatter
├── tests/                   # Unit and API regression tests
├── scripts/                 # CI checks such as documentation consistency
├── requirements.txt         # Runtime dependencies
├── .env.example             # Environment variable template
├── run.bat / run.sh         # One-click launch scripts
├── setup.bat / setup.sh     # Setup-only scripts
├── data/                    # Runtime data (DB, presets, last params)
├── outputs/                 # Generated images and metadata (auto-created)
└── static/                  # Web UI, CSS, JavaScript, and translations
```

---

## API Endpoints

The complete interactive schema is available at `/docs` and `/openapi.json`
when the server is running. The table below lists the public routes by area.

### Prompt generation and comparison

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/generate-prompts` | Single image → prompts |
| `POST` | `/api/generate-prompts-batch` | Up to 10 images → independent prompts |
| `POST` | `/api/generate-prompts-blend` | 2–3 labelled reference images → one combined prompt |
| `POST` | `/api/generate-prompts-stream` | SSE prompt generation |
| `POST` | `/api/generate-prompts-text` | Text description → prompts |
| `POST` | `/api/generate-prompts-compare` | Compare prompt variants |
| `POST` | `/api/refine-prompt` | Refine and enhance a prompt |
| `POST` | `/api/compare/ab-generate` | Generate two SD variants with a shared seed |
| `GET` | `/api/compare/ab-history` | List A/B comparisons |
| `POST` | `/api/compare/ab/{id}/vote` | Record the preferred variant |

### History, tags, and versions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/history` | List history (`limit`, `offset`, `search`, `style`, `quality`, `favorites_only`, `tag`) |
| `GET` | `/api/history/export` | Download history as JSON, CSV, or XLSX (`format`) |
| `GET` | `/api/history/diff` | Compare two prompt versions |
| `GET` | `/api/history/{id}/versions` | List a version tree |
| `POST` | `/api/history/{id}/rollback` | Create a rollback version |
| `PUT` | `/api/history/{id}/favorite` | Toggle a favorite |
| `DELETE` | `/api/history/{id}` | Delete one entry |
| `DELETE` | `/api/history` | Clear all history |
| `GET` | `/api/tags` | List tags and usage counts |
| `GET` | `/api/tags/suggest` | Suggest tags |
| `GET` | `/api/tags/categories` | List tag categories |
| `POST` | `/api/history/{id}/tags` | Add tags to a history entry |
| `DELETE` | `/api/history/{id}/tags/{tag}` | Remove a tag |

### Stable Diffusion

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sd/status` | Check A1111 and ControlNet status |
| `GET` | `/api/sd/models` | List available models |
| `GET` | `/api/sd/loras` | List available LoRAs |
| `GET` | `/api/sd/upscalers` | List available upscalers |
| `GET` | `/api/sd/progress` | Current generation progress |
| `WS` | `/api/sd/progress/ws` | Stream generation progress |
| `GET` | `/api/sd/controlnet/models` | List ControlNet models (empty when unavailable) |
| `GET` | `/api/sd/controlnet/modules` | List ControlNet preprocessors |
| `POST` | `/api/sd/generate` | txt2img generation |
| `POST` | `/api/sd/generate-multi-model` | Sequential generation with multiple models |
| `POST` | `/api/sd/img2img` | img2img generation |
| `POST` | `/api/sd/inpaint` | Inpainting with optional ControlNet units |
| `POST` | `/api/interrogate` | CLIP Interrogator / DeepDanbooru tagging |
| `POST` | `/api/png-info` | Read A1111 PNG metadata |

### Job queue and dynamic prompts

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/jobs/submit` | Submit `txt2img`, `multi_model`, or `xy_plot` job |
| `GET` | `/api/jobs` | List jobs |
| `GET` | `/api/jobs/{id}` | Get job status, queue position, and ETA |
| `POST` | `/api/jobs/{id}/cancel` | Cancel a pending/running job |
| `POST` | `/api/jobs/{id}/priority` | Change pending-job priority |
| `GET` | `/api/jobs/queue/stats` | Queue counts by status |
| `WS` | `/api/jobs/{id}/ws` | Stream job progress |
| `GET` | `/api/wildcards/` | List wildcard files |
| `POST` | `/api/wildcards/` | Create a wildcard file |
| `GET` | `/api/wildcards/{name}` | Read a wildcard file |
| `PUT` | `/api/wildcards/{name}` | Update a wildcard file |
| `DELETE` | `/api/wildcards/{name}` | Delete a wildcard file |
| `POST` | `/api/wildcards/expand` | Preview or enumerate prompt expansions |

### Gallery, cache, backups, and providers

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/outputs` | Browse generated images (`date`, `mode`, `limit`, `offset`, filters) |
| `GET` | `/api/outputs/filters` | List model and sampler filters |
| `POST` | `/api/outputs/download-zip` | Download selected outputs as ZIP |
| `GET` | `/api/cache/stats` | LLM cache hit/miss statistics |
| `DELETE` | `/api/cache` | Clear the LLM cache (token-protected when configured) |
| `POST` | `/api/backup/create` | Create a backup archive |
| `GET` | `/api/backup/list` | List backup archives |
| `GET` | `/api/backup/download/{id}` | Download a backup |
| `POST` | `/api/backup/restore` | Upload and restore a backup |
| `POST` | `/api/backup/restore/{id}` | Restore a listed backup |
| `DELETE` | `/api/backup/{id}` | Delete a backup |
| `GET` | `/api/llm/providers` | List provider configuration and fallback state |
| `GET` | `/api/llm/health` | List provider health and response time |
| `POST` | `/api/llm/provider` | Switch the active provider (token-protected when configured) |

### Configuration and observability

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/config` | App configuration and available providers |
| `GET` | `/api/stats` | History, gallery, tag, and activity statistics |
| `GET` | `/metrics` | Prometheus metrics (token-protected when configured) |
| `GET` | `/health` | LLM/SD availability and uptime |
| `GET` | `/api/last-params/{feature}` | Restore last parameters |
| `POST` | `/api/last-params/{feature}` | Save last parameters |

Valid `feature` values: `generate`, `sd`, `img2img`, `inpaint`, `multi_model`, `xyplot`

---

## Running Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

---

## Troubleshooting

### "LLM server is not available"
1. Make sure your LLM server is running
2. Check `LLM_SERVER_URL` in `.env`
3. Test connectivity:
   ```bash
   curl http://localhost:1234/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"any","messages":[{"role":"user","content":"test"}],"max_tokens":10}'
   ```

### "Stable Diffusion API is not available"
1. Launch A1111 WebUI with the `--api` flag
2. Check `SD_API_URL` in `.env`
3. Test: `curl http://localhost:7860/config`

### Image won't upload
- File size must not exceed **10 MB**
- Supported formats: **JPG, PNG, WebP, GIF**

### API documentation (interactive)
- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

---

## License

See [LICENSE](LICENSE).
