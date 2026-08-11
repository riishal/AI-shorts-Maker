# AI Shorts Maker backend - Cloud Run ready.
FROM python:3.12-slim

# FFmpeg (+ffprobe) for rendering. fonts-liberation gives an Arial-compatible
# bold sans-serif so burned-in captions render identically to local Windows;
# fontconfig lets libass resolve the "Arial" family to it.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg fonts-liberation fontconfig \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Local working directories (also created at runtime by config.py).
RUN mkdir -p uploads outputs/auto_shorts

# Cloud Run injects PORT; default to 8000 for local docker runs.
ENV PORT=8000
EXPOSE 8000

# Bind to 0.0.0.0 and honor the dynamic PORT. Single worker keeps the
# in-memory job store consistent.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
