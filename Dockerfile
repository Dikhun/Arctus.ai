FROM python:3.11-slim

# ── System packages: Node.js (OmniRoute), git, display server, browser automation ──
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg git \
        xvfb xdotool scrot python3-tk python3-dev \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

RUN npm install -g omniroute

# ── Python: framework + computer-use deps ──
WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -e ".[server]" \
    && pip install --no-cache-dir pyautogui playwright pillow \
    && playwright install chromium

EXPOSE 7860 20128

ENV OPENAI_API_BASE="http://localhost:20128/v1"
ENV OPENAI_API_KEY="free-local-key"
# Default subscription tier for hosted deployments.
ENV ARCTUS_TIER="free"
# Sandbox isolation mode: "restricted-subprocess" (default) or "bubblewrap" (if bwrap available).
ENV ARCTUS_SANDBOX="auto"

# Start Xvfb (virtual display for computer-use) + OmniRoute (free-model router),
# then run the FastAPI dashboard as the foreground process.
# HF Spaces only exposes port 7860; 20128 is the internal OmniRoute port.
CMD Xvfb :99 -screen 0 1024x768x24 & \
    export DISPLAY=:99 && \
    omniroute & sleep 2 && \
    exec python -m server.app
