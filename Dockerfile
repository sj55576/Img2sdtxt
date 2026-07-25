FROM python:3.12-slim

# ------------------------------------------------------------------ #
# System dependencies
#   - openssl: required for auto-generating self-signed TLS certs
#     (see main.py HTTPS_ENABLED handling)
# Pillow ships manylinux wheels for CPython 3.12, so no image codec
# headers or compiler toolchain are needed here.
# ------------------------------------------------------------------ #
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies first so this layer is cached unless
# requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create a non-root user and make sure the directories that are
# typically bind-mounted (data/outputs/ssl) are writable by it.
RUN useradd --uid 1000 --create-home --shell /bin/bash app \
    && mkdir -p /app/data /app/outputs /app/ssl \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Note: assumes plain HTTP inside the container. With HTTPS_ENABLED=true,
# override HEALTHCHECK (or disable it) in docker-compose.yml.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

# Run the same way run.sh does, so the existing HTTPS / self-signed
# certificate generation logic in main.py still applies.
CMD ["python", "main.py"]
