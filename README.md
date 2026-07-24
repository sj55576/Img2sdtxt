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

### 3. Python 3.8+

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
git clone https://github.com/sj55576/Img2sdtxt.git
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
| `SD_API_URL` | `http://localhost:7860` | AUTOMATIC1111 API URL |
| `API_HOST` | `0.0.0.0` | API server bind address |
| `API_PORT` | `8000` | API server port |
| `DEBUG` | `false` | Enable debug / hot-reload |
| `CORS_ALLOWED_ORIGINS` | `*` | Comma-separated allowed browser origins; use explicit origins in production |
| `CORS_ALLOW_CREDENTIALS` | `false` | Allow credentialed CORS requests; enable only with restricted origins |
| `TRUST_PROXY_HEADERS` | `false` | Trust `X-Forwarded-For` / `X-Real-IP` only behind a trusted reverse proxy |
| `HTTPS_ENABLED` | `false` | Serve over HTTPS |
| `SSL_CERTFILE` | *(auto)* | Path to TLS certificate file (PEM) |
| `SSL_KEYFILE` | *(auto)* | Path to TLS private key file (PEM) |
| `WEBHOOK_URL` | *(empty)* | Webhook endpoint URL; empty disables notifications |
| `WEBHOOK_EVENTS` | `job_completed,job_failed,batch_completed` | Comma-separated events to notify on (`job_completed`, `job_failed`, `job_cancelled`, `batch_completed`) |
| `WEBHOOK_FORMAT` | `generic` | Payload format: `generic`, `discord`, or `slack` |
| `WEBHOOK_TIMEOUT` | `5` | Webhook request timeout in seconds |

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
- The backup endpoints are unauthenticated, like the rest of the API. A
  backup archive contains your full history — do not expose the app to an
  untrusted network without putting authentication in front of it (see the
  reverse-proxy example in the Docker section).

---

## Project Structure

```
Img2sdtxt/
├── main.py                  # FastAPI application & all API routes
├── config.py                # App configuration & option lists
├── llm_client.py            # LLM server communication
├── prompt_generator.py      # Prompt generation logic
├── sd_client.py             # Stable Diffusion API client
├── history.py               # SQLite history management
├── presets.py               # Preset template management
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── run.bat / run.sh         # One-click launch scripts
├── setup.bat / setup.sh     # Setup-only scripts
├── data/                    # Runtime data (DB, presets, last params)
│   ├── history.db
│   ├── presets.json
│   └── last_params.json
├── outputs/                 # Generated images (auto-created)
│   └── YYYY-MM-DD/
│       ├── *.png
│       ├── *_metadata.json
│       └── thumbs/
└── static/
    ├── index.html           # Web UI
    ├── style.css
    └── script.js
```

---

## API Endpoints

### Prompt Generation

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/generate-prompts` | Single image → prompts |
| `POST` | `/api/generate-prompts-batch` | Up to 10 images → prompts |
| `POST` | `/api/generate-prompts-text` | Text description → prompts |
| `POST` | `/api/refine-prompt` | Refine & enhance existing prompts |

### History

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/history` | List history (`limit`, `offset`, `search`, `style`, `quality`, `favorites_only`) |
| `GET` | `/api/history/export` | Download all history as JSON, CSV, or XLSX (`format`) |
| `PUT` | `/api/history/{id}/favorite` | Toggle favorite on a history entry |
| `DELETE` | `/api/history/{id}` | Delete one entry |
| `DELETE` | `/api/history` | Clear all history |

### Presets

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/presets` | List all presets |
| `POST` | `/api/presets` | Create custom preset |
| `DELETE` | `/api/presets/{id}` | Delete custom preset |

### Stable Diffusion

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/sd/status` | Check A1111 connection |
| `GET` | `/api/sd/models` | List available models |
| `GET` | `/api/sd/loras` | List available LoRAs |
| `GET` | `/api/sd/upscalers` | List available upscalers |
| `GET` | `/api/sd/progress` | Current generation progress (for progress bar) |
| `POST` | `/api/sd/generate` | txt2img generation |
| `POST` | `/api/sd/generate-multi-model` | txt2img generation with multiple models sequentially |
| `POST` | `/api/sd/img2img` | img2img generation |
| `POST` | `/api/sd/inpaint` | Inpainting |

### Other

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/config` | App configuration |
| `GET` | `/health` | Health check |
| `GET` | `/api/outputs` | Gallery images (`date`, `mode`, `limit`, `offset`) |
| `GET` | `/api/last-params/{feature}` | Restore last parameters |
| `POST` | `/api/last-params/{feature}` | Save last parameters |

Valid `feature` values: `generate`, `sd`, `img2img`, `inpaint`, `multi_model`

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
