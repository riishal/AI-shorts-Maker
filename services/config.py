"""Central configuration, driven entirely by environment variables.

Nothing here is hard-coded to a production URL. Every value has a sane
local-development default so the app runs out of the box, while allowing a
deployment (Cloud Run, etc.) to override via environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _get_list(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# --------------------------------------------------------------------------
# Paths (relative to project root so the existing scripts keep working)
# --------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "uploads")))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "outputs")))
SHORTS_DIR = OUTPUT_DIR / "auto_shorts"

for _d in (UPLOAD_DIR, OUTPUT_DIR, SHORTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# CORS
# --------------------------------------------------------------------------
# Explicit production origins come from ALLOWED_ORIGINS (comma separated).
# Localhost/127.0.0.1 on any port is always allowed via a regex so local
# Flutter web development (which uses random ports) never breaks.

ALLOWED_ORIGINS = _get_list("ALLOWED_ORIGINS", [])
ALLOWED_ORIGIN_REGEX = os.getenv(
    "ALLOWED_ORIGIN_REGEX",
    r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
)


# --------------------------------------------------------------------------
# Upload / security limits
# --------------------------------------------------------------------------

MAX_UPLOAD_MB = _get_int("MAX_UPLOAD_MB", 2048)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

ALLOWED_VIDEO_EXTENSIONS = {
    ext.lower()
    for ext in _get_list(
        "ALLOWED_VIDEO_EXTENSIONS",
        [".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"],
    )
}


# --------------------------------------------------------------------------
# AI / pipeline settings
# --------------------------------------------------------------------------

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

# Greedy decoding (beam_size=1) is markedly faster than the default beam of 5
# and is plenty accurate for highlight timing. 0 cpu_threads = auto.
WHISPER_BEAM_SIZE = _get_int("WHISPER_BEAM_SIZE", 1)
WHISPER_CPU_THREADS = _get_int("WHISPER_CPU_THREADS", 0)

# Voice-activity filtering skips silence/music. Occasionally nudges word
# timing; set false if captions feel out of sync and the offset isn't enough.
WHISPER_VAD = _get_bool("WHISPER_VAD", True)

# Bound transcription time on very long sources. 0 = transcribe everything.
# When set, only the first N seconds are transcribed/considered for highlights.
MAX_TRANSCRIBE_SECONDS = _get_int("MAX_TRANSCRIBE_SECONDS", 0)

# How many Shorts to produce.
TARGET_SHORTS = _get_int("TARGET_SHORTS", 10)

# Clip length bounds (seconds).
MIN_CLIP_SECONDS = _get_int("MIN_CLIP_SECONDS", 18)
MAX_CLIP_SECONDS = _get_int("MAX_CLIP_SECONDS", 60)
DEFAULT_CLIP_SECONDS = _get_int("DEFAULT_CLIP_SECONDS", 30)

# Enable/disable the AI transcription step. When disabled (or when
# faster-whisper is unavailable), the pipeline still renders Shorts using the
# heuristic highlight selector, just without burned-in captions.
ENABLE_TRANSCRIPTION = _get_bool("ENABLE_TRANSCRIPTION", True)


# --------------------------------------------------------------------------
# "Edited-look" render effects (TikTok / Hormozi style)
# --------------------------------------------------------------------------

# Master switch for the enhanced render path. When off, the classic simple
# render (static captions, no effects) is used.
ENHANCED_EDIT = _get_bool("ENHANCED_EDIT", True)

# Animated phrase captions with pop/overshoot + important-word emphasis.
ANIMATED_CAPTIONS = _get_bool("ANIMATED_CAPTIONS", True)

# How the source frame is placed into the 1080x1920 canvas:
#   crop  - fill the whole portrait frame, cropping the sides (aspect kept)
#   fit   - keep the original aspect ratio, pad with black bars (letterbox)
#   blur  - keep aspect ratio, fill the bars with a blurred copy of the video
VIDEO_FIT = os.getenv("VIDEO_FIT", "crop").lower().strip()
PAD_COLOR = os.getenv("PAD_COLOR", "black")

# Subtle punch-in / slow zoom (applied in 'crop' mode only).
ENABLE_ZOOM = _get_bool("ENABLE_ZOOM", True)


def _get_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


ZOOM_MAX = _get_float("ZOOM_MAX", 1.12)  # 1.0 = no zoom

# Color grading (punchier contrast / saturation).
ENABLE_COLOR_GRADE = _get_bool("ENABLE_COLOR_GRADE", True)
COLOR_CONTRAST = _get_float("COLOR_CONTRAST", 1.08)
COLOR_SATURATION = _get_float("COLOR_SATURATION", 1.20)

# Background music. Only used when the file exists and is non-empty; otherwise
# silently skipped (no fake audio). Point BACKGROUND_MUSIC at an mp3/wav.
BACKGROUND_MUSIC = os.getenv("BACKGROUND_MUSIC", str(PROJECT_ROOT / "background.mp3"))
BG_MUSIC_VOLUME = _get_float("BG_MUSIC_VOLUME", 0.12)


def background_music_path() -> Path | None:
    """Return a usable background-music path, or None if not configured."""
    if not BACKGROUND_MUSIC:
        return None
    p = Path(BACKGROUND_MUSIC)
    try:
        if p.exists() and p.stat().st_size > 0:
            return p
    except OSError:
        return None
    return None


# --------------------------------------------------------------------------
# Caption style (see services/caption_style.py for the full engine)
# --------------------------------------------------------------------------

CAPTION_STYLE = os.getenv("CAPTION_STYLE", "minecraft")  # minecraft|gaming|minimal


def _get_opt_int(name: str):
    raw = os.getenv(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _get_opt_float(name: str):
    raw = os.getenv(name)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def caption_style_config():
    """Build the active CaptionStyleConfig from the preset + env overrides."""
    from . import caption_style

    cfg = caption_style.get_preset(CAPTION_STYLE)
    return cfg.with_overrides(
        font=os.getenv("CAPTION_FONT"),
        font_size=_get_opt_int("CAPTION_FONT_SIZE"),
        primary_color=os.getenv("CAPTION_COLOR"),
        outline_color=os.getenv("CAPTION_OUTLINE_COLOR"),
        outline_width=_get_opt_float("CAPTION_OUTLINE_WIDTH"),
        shadow=_get_opt_float("CAPTION_SHADOW"),
        margin_v=_get_opt_int("CAPTION_MARGIN_V"),
        max_words=_get_opt_int("CAPTION_MAX_WORDS"),
        highlight_color=os.getenv("CAPTION_HIGHLIGHT_COLOR"),
        offset_ms=_get_opt_int("CAPTION_OFFSET_MS"),
    )


# --------------------------------------------------------------------------
# YouTube settings
# --------------------------------------------------------------------------

# Reject sources longer than this (seconds) to keep processing bounded.
YOUTUBE_MAX_DURATION = _get_int("YOUTUBE_MAX_DURATION", 3 * 60 * 60)

# yt-dlp format selection. Caps height to keep downloads reasonable.
YT_DLP_FORMAT = os.getenv(
    "YT_DLP_FORMAT",
    "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
)

# Seconds before a YouTube download is aborted.
YOUTUBE_DOWNLOAD_TIMEOUT = _get_int("YOUTUBE_DOWNLOAD_TIMEOUT", 20 * 60)


# --------------------------------------------------------------------------
# Storage backend
# --------------------------------------------------------------------------

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local")  # local | gcs
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
