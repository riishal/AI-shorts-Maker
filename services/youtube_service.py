"""YouTube source service.

Responsibilities:
    * validate and normalize a YouTube URL
    * fetch lightweight metadata (no download) for the analyze step
    * download the video via yt-dlp into the shared upload/source storage
    * map yt-dlp/network failures to friendly, non-technical messages

This is the ONLY place that knows about YouTube. The rest of the pipeline
consumes a normalized local file path, identical to an uploaded video, so
both inputs share a single downstream pipeline.

yt-dlp is used because it is the standard, actively maintained tool for this
task. Livestreams that are still live cannot be processed and are rejected
with a clear message rather than pretending to work.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse, parse_qs

from . import config

log = logging.getLogger("youtube")

# Accepted host suffixes.
_YT_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
             "music.youtube.com")

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class YouTubeError(Exception):
    """User-friendly YouTube processing error (safe to show to the client)."""


# --------------------------------------------------------------------------
# URL VALIDATION / NORMALIZATION
# --------------------------------------------------------------------------

def extract_video_id(url: str) -> Optional[str]:
    """Extract an 11-char video id from the common YouTube URL formats."""
    if not url:
        return None
    url = url.strip()
    if not re.match(r"^https?://", url):
        url = "https://" + url

    try:
        parsed = urlparse(url)
    except ValueError:
        return None

    host = (parsed.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _YT_HOSTS):
        return None

    # youtu.be/<id>
    if host.endswith("youtu.be"):
        candidate = parsed.path.lstrip("/").split("/")[0]
        return candidate if _VIDEO_ID_RE.match(candidate) else None

    # /watch?v=<id>
    if parsed.path == "/watch":
        vid = parse_qs(parsed.query).get("v", [None])[0]
        return vid if vid and _VIDEO_ID_RE.match(vid) else None

    # /live/<id>, /shorts/<id>, /embed/<id>, /v/<id>
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[0] in {"live", "shorts", "embed", "v"}:
        candidate = parts[1]
        return candidate if _VIDEO_ID_RE.match(candidate) else None

    return None


def normalize_url(url: str) -> str:
    """Return a canonical watch URL for a supported YouTube link."""
    video_id = extract_video_id(url)
    if not video_id:
        raise YouTubeError("This does not look like a supported YouTube URL.")
    return f"https://www.youtube.com/watch?v={video_id}"


def is_supported(url: str) -> bool:
    return extract_video_id(url) is not None


# --------------------------------------------------------------------------
# ERROR MAPPING
# --------------------------------------------------------------------------

def _friendly_error(message: str) -> str:
    text = (message or "").lower()
    table = [
        ("private", "This video is private and cannot be processed."),
        ("members-only", "This is a members-only video and cannot be processed."),
        ("sign in to confirm your age", "This video is age-restricted and cannot be processed."),
        ("age", "This video is age-restricted and cannot be processed."),
        ("removed", "This video has been removed and is no longer available."),
        ("deleted", "This video has been deleted and is no longer available."),
        ("unavailable", "This video is unavailable."),
        ("not available in your country", "This video is not available in your region."),
        ("geo", "This video is not available in your region."),
        ("blocked", "This video is blocked and cannot be processed."),
        ("copyright", "This video is blocked and cannot be processed."),
        ("live event will begin", "This livestream has not started yet."),
        ("this live event has ended", "This livestream has ended and its recording is not ready yet."),
        ("is live", "Live streams cannot be processed while still live."),
        ("premiere", "This premiere has not started yet."),
        ("timed out", "The video took too long to download. Please try again."),
        ("timeout", "The video took too long to download. Please try again."),
        ("http error 429", "YouTube is rate-limiting requests. Please try again later."),
        ("unable to download", "Could not download this video."),
    ]
    for needle, friendly in table:
        if needle in text:
            return friendly
    return "Could not process this YouTube video."


# --------------------------------------------------------------------------
# METADATA (analyze) - no download
# --------------------------------------------------------------------------

def get_metadata(url: str) -> dict[str, Any]:
    """Return lightweight video info without downloading. Raises YouTubeError."""
    try:
        import yt_dlp
    except Exception as exc:  # pragma: no cover - install-time issue
        log.error("yt-dlp import failed: %s", exc)
        raise YouTubeError(
            "YouTube support is not available on the server."
        ) from exc

    watch_url = normalize_url(url)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(watch_url, download=False)
    except Exception as exc:
        log.warning("yt-dlp metadata error: %s", exc)
        raise YouTubeError(_friendly_error(str(exc))) from exc

    if info.get("is_live"):
        raise YouTubeError(
            "This is a live stream. Live streams cannot be processed while "
            "still live. Try again once the stream has ended and its "
            "recording is available."
        )

    duration = int(info.get("duration") or 0)
    if duration and duration > config.YOUTUBE_MAX_DURATION:
        mins = config.YOUTUBE_MAX_DURATION // 60
        raise YouTubeError(
            f"This video is too long to process (limit is {mins} minutes)."
        )

    return {
        "video_id": info.get("id"),
        "title": info.get("title") or "YouTube video",
        "duration": duration,
        "channel": info.get("uploader") or info.get("channel") or "",
        "thumbnail": info.get("thumbnail") or "",
        "url": watch_url,
        "supported": True,
    }


# --------------------------------------------------------------------------
# DOWNLOAD (process) -> normalized local source path
# --------------------------------------------------------------------------

def download(url: str, on_progress=None) -> tuple[Path, dict[str, Any]]:
    """Download the video into the upload/source dir.

    Returns ``(local_path, metadata)``. Raises :class:`YouTubeError` with a
    friendly message on any failure.
    """
    try:
        import yt_dlp
    except Exception as exc:  # pragma: no cover
        raise YouTubeError(
            "YouTube support is not available on the server."
        ) from exc

    meta = get_metadata(url)  # validates + enforces limits first
    video_id = meta["video_id"] or uuid.uuid4().hex[:8]
    token = uuid.uuid4().hex[:8]
    out_stem = config.UPLOAD_DIR / f"yt_{video_id}_{token}"

    def _hook(status: dict[str, Any]) -> None:
        if on_progress is None:
            return
        try:
            if status.get("status") == "downloading":
                total = status.get("total_bytes") or status.get(
                    "total_bytes_estimate") or 0
                done = status.get("downloaded_bytes") or 0
                frac = (done / total) if total else None
                on_progress(frac)
        except Exception:
            pass

    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": config.YT_DLP_FORMAT,
        "merge_output_format": "mp4",
        "outtmpl": str(out_stem) + ".%(ext)s",
        "socket_timeout": 30,
        "retries": 3,
        "progress_hooks": [_hook],
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
        ],
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([meta["url"]])
    except Exception as exc:
        log.warning("yt-dlp download error: %s", exc)
        raise YouTubeError(_friendly_error(str(exc))) from exc

    # Locate the produced file (extension may vary before/after conversion).
    produced = sorted(config.UPLOAD_DIR.glob(f"{out_stem.name}.*"))
    mp4 = [p for p in produced if p.suffix.lower() == ".mp4"]
    final = mp4[0] if mp4 else (produced[0] if produced else None)

    if final is None or not final.exists():
        raise YouTubeError("Could not download this video.")

    return final, meta
