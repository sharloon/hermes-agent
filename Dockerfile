FROM ghcr.io/astral-sh/uv:0.11.6-python3.13-trixie@sha256:b3c543b6c4f23a5f2df22866bd7857e5d304b67a564f4feab6ac22044dde719b AS uv_source
FROM tianon/gosu:1.19-trixie@sha256:3b176695959c71e123eb390d427efc665eeb561b1540e82679c15e992006b8b9 AS gosu_source
FROM debian:13.4

# Disable Python stdout buffering to ensure logs are printed immediately
ENV PYTHONUNBUFFERED=1

# Store Playwright browsers outside the volume mount so the build-time
# install survives the /opt/data volume overlay at runtime.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/hermes/.playwright

# Install system dependencies in one layer, clear APT cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential nodejs npm python3 ripgrep ffmpeg gcc python3-dev libffi-dev procps git && \
    rm -rf /var/lib/apt/lists/*

# Non-root user for runtime; UID can be overridden via HERMES_UID at runtime
RUN useradd -u 10000 -m -d /opt/data hermes

COPY --chmod=0755 --from=gosu_source /gosu /usr/local/bin/
COPY --chmod=0755 --from=uv_source /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

WORKDIR /opt/hermes

# ── Docker Cache Optimization ───────────────────────────────────────────────
# Copy dependency files FIRST, install dependencies, THEN copy source code
# This way pip install is cached unless pyproject.toml changes

# Step 1: Copy only dependency configuration files
COPY pyproject.toml setup.py* MANIFEST.in* requirements*.txt* package.json package-lock.json* /opt/hermes/

# Step 2: Install Node dependencies (cached unless package.json changes)
RUN npm install --prefer-offline --no-audit && \
    npm cache clean --force || true

# Step 3: Install Python dependencies (cached unless pyproject.toml changes)
RUN chown -R hermes:hermes /opt/hermes
USER hermes
RUN uv venv && \
    uv pip install --no-cache-dir ".[all]"
USER root

# Step 4: Now copy source code (frequent changes don't trigger pip reinstall)
COPY . /opt/hermes

# Step 5: Install Playwright and WhatsApp bridge (after code copy since they need code)
RUN npx playwright install --with-deps chromium --only-shell && \
    cd /opt/hermes/scripts/whatsapp-bridge && \
    npm install --prefer-offline --no-audit && \
    npm cache clean --force

# Final setup
RUN chown -R hermes:hermes /opt/hermes
RUN chmod +x /opt/hermes/docker/entrypoint.sh

ENV HERMES_HOME=/opt/data
VOLUME [ "/opt/data" ]
ENTRYPOINT [ "/opt/hermes/docker/entrypoint.sh" ]
