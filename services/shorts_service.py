"""Unified AI Shorts pipeline used by BOTH local uploads and YouTube sources.

Stages
------
1. Transcribe the source video with faster-whisper (word-level ASS captions).
2. Select the best moments with Gemini; fall back to a deterministic
   density-based heuristic when AI is unavailable (clearly labelled, not fake).
3. Render vertical 9:16 Shorts with FFmpeg, burning in per-clip captions.

The FFmpeg encoding (H.264 / yuv420p / AAC / +faststart) and the caption
styling are preserved exactly from the original working pipeline so browser
playback and download behaviour do not regress.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from . import config
from . import caption_style
from .jobs import JobState, store

log = logging.getLogger("shorts")

ProgressFn = Callable[[JobState, str, Optional[float], str], None]

# Words that get highlighted (yellow) inside burned-in captions.
IMPORTANT_WORDS = [
    "WAIT", "WHAT", "NO", "OH", "WHOA", "STOP", "GUYS", "OMG",
    "INSANE", "CRAZY", "KILL", "WIN", "LOST", "HOW", "WHY",
]


# ==========================================================================
# ASS TIME HELPERS  (preserved from create_shorts.py)
# ==========================================================================

def ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_to_seconds(value: str) -> float:
    h, m, rest = value.split(":")
    sec, cs = rest.split(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(cs) / 100


ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Gaming,Arial,82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,6,3,5,50,50,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""



# ==========================================================================
# FFPROBE
# ==========================================================================

def get_duration(video_path: Path) -> float:
    """Return the video duration in seconds (0 on failure)."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        return float(result.stdout.strip())
    except Exception:
        log.warning("ffprobe failed for %s", video_path, exc_info=True)
        return 0.0


# ==========================================================================
# STAGE 1: TRANSCRIPTION
# ==========================================================================

def transcribe(
    video_path: Path,
    master_ass: Path,
    job_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Transcribe with faster-whisper and write a word-level master ASS.

    Streams real progress into the job store (``segment.end / duration``) so
    the UI never looks frozen during a long transcription. Returns a list of
    segment dicts ({start, end, text}); empty if transcription is disabled or
    the model is unavailable (pipeline then continues without captions).
    """
    if not config.ENABLE_TRANSCRIPTION:
        return []

    try:
        from faster_whisper import WhisperModel
    except Exception:
        log.warning("faster-whisper not available; skipping captions.")
        return []

    if job_id:
        store.set_state(job_id, JobState.ANALYZING,
                        "Loading transcription model...", progress=None)

    model = WhisperModel(
        config.WHISPER_MODEL,
        device=config.WHISPER_DEVICE,
        compute_type=config.WHISPER_COMPUTE_TYPE,
        cpu_threads=config.WHISPER_CPU_THREADS,
    )

    segments_iter, info = model.transcribe(
        str(video_path),
        vad_filter=config.WHISPER_VAD,
        word_timestamps=True,
        beam_size=config.WHISPER_BEAM_SIZE,
    )

    total = float(getattr(info, "duration", 0) or 0)
    cap = config.MAX_TRANSCRIBE_SECONDS

    segments: list[dict[str, Any]] = []
    lines: list[str] = [ASS_HEADER]

    for segment in segments_iter:
        # Optional hard cap to bound processing time on very long videos.
        if cap and segment.start > cap:
            break

        seg_text = (segment.text or "").strip()
        if seg_text:
            segments.append(
                {"start": float(segment.start), "end": float(segment.end),
                 "text": seg_text}
            )
        for word in (segment.words or []):
            token = (word.word or "").strip()
            if not token:
                continue
            lines.append(
                f"Dialogue: 0,{ass_time(word.start)},{ass_time(word.end)},"
                f"Gaming,,0,0,0,,{token}"
            )

        if job_id and total:
            frac = min(segment.end / total, 0.99)
            store.set_state(
                job_id, JobState.ANALYZING,
                f"Analyzing content... {int(frac * 100)}%",
                stage=f"Transcribing ({int(frac * 100)}%)",
                progress=frac,
            )

    master_ass.write_text("\n".join(lines), encoding="utf-8")
    return segments


def build_transcript_text(segments: list[dict[str, Any]]) -> str:
    """Timestamped transcript string for the highlight-selection prompt."""
    out = []
    for seg in segments:
        out.append(f"[{seg['start']:.2f} - {seg['end']:.2f}] {seg['text']}")
    return "\n".join(out)


# ==========================================================================
# STAGE 2: HIGHLIGHT SELECTION
# ==========================================================================

def select_highlights(
    segments: list[dict[str, Any]],
    duration: float,
) -> tuple[list[dict[str, Any]], str]:
    """Return ``(highlights, source)`` where source is 'ai' or 'heuristic'."""
    if segments and config.GEMINI_API_KEY:
        try:
            highlights = _gemini_highlights(segments, duration)
            highlights = _sanitize_highlights(highlights, duration)
            if highlights:
                return highlights, "ai"
        except Exception:
            log.warning("Gemini highlight selection failed; using heuristic.",
                        exc_info=True)

    return _heuristic_highlights(segments, duration), "heuristic"


def _gemini_highlights(
    segments: list[dict[str, Any]], duration: float
) -> list[dict[str, Any]]:
    from google import genai

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    transcript = build_transcript_text(segments)

    prompt = f"""You are an expert short-form video editor.

Analyze this timestamped transcript and find the {config.TARGET_SHORTS} BEST
moments to turn into vertical Shorts.

Look for: strong hooks, funny/surprising/emotional moments, reactions,
suspense, and self-contained stories.

Rules:
1. Use ONLY timestamps that exist in the transcript (0 to {duration:.1f}s).
2. Each clip must be {config.MIN_CLIP_SECONDS}-{config.MAX_CLIP_SECONDS}s long.
3. Clips must not overlap.
4. Rank from best to worst.
5. Return ONLY valid JSON, no markdown.

Return exactly:
{{"highlights":[{{"rank":1,"start":12.5,"end":40.0,"score":95,"title":"...","reason":"..."}}]}}

Transcript:
{transcript}
"""

    response = client.models.generate_content(
        model=config.GEMINI_MODEL, contents=prompt
    )
    text = (response.text or "").strip()

    # Strip markdown fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text).strip()

    data = json.loads(text)
    return data.get("highlights", [])


def _sanitize_highlights(
    highlights: list[dict[str, Any]], duration: float
) -> list[dict[str, Any]]:
    """Clamp timestamps, drop invalid entries, cap to TARGET_SHORTS."""
    clean: list[dict[str, Any]] = []
    for item in highlights:
        try:
            start = max(0.0, float(item["start"]))
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if duration:
            end = min(end, duration)
        length = end - start
        if length < max(5, config.MIN_CLIP_SECONDS * 0.5):
            continue
        if length > config.MAX_CLIP_SECONDS:
            end = start + config.MAX_CLIP_SECONDS
        clean.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "score": int(item.get("score", 0) or 0),
            "title": str(item.get("title", "")).strip(),
            "reason": str(item.get("reason", "")).strip(),
        })

    clean.sort(key=lambda h: h.get("score", 0), reverse=True)
    clean = clean[: config.TARGET_SHORTS]
    for i, item in enumerate(clean, start=1):
        item["rank"] = i
    return clean


def _heuristic_highlights(
    segments: list[dict[str, Any]], duration: float
) -> list[dict[str, Any]]:
    """Deterministic fallback: pick the most 'talkative' non-overlapping windows.

    This is an honest, explainable heuristic (density of speech), NOT fake AI.
    When there is no transcript, it falls back to evenly spaced clips so any
    video still yields Shorts.
    """
    clip_len = float(config.DEFAULT_CLIP_SECONDS)
    target = config.TARGET_SHORTS

    if duration <= 0:
        duration = (segments[-1]["end"] if segments else clip_len * target)

    # No transcript -> evenly spaced clips across the whole video.
    if not segments:
        highlights = []
        usable = max(duration - clip_len, 0.0)
        step = usable / max(target - 1, 1) if target > 1 else 0
        for i in range(target):
            start = min(i * step, usable)
            end = min(start + clip_len, duration)
            if end - start < 5:
                break
            highlights.append({
                "rank": i + 1, "start": round(start, 2), "end": round(end, 2),
                "score": 50, "title": f"Highlight {i + 1}",
                "reason": "Evenly sampled segment.",
            })
        return highlights

    # Slide a window across the video; score = words spoken inside it.
    def words_in(a: float, b: float) -> int:
        total = 0
        for seg in segments:
            if seg["end"] <= a or seg["start"] >= b:
                continue
            total += len((seg["text"] or "").split())
        return total

    candidates = []
    step = max(clip_len / 2, 5.0)
    t = 0.0
    while t + 5 < duration:
        end = min(t + clip_len, duration)
        candidates.append((words_in(t, end), t, end))
        t += step

    candidates.sort(reverse=True)  # densest first

    chosen: list[tuple[float, float]] = []
    for _score, start, end in candidates:
        if all(end <= s or start >= e for s, e in chosen):
            chosen.append((start, end))
        if len(chosen) >= target:
            break

    chosen.sort()  # chronological order for stable ranks
    highlights = []
    for i, (start, end) in enumerate(chosen, start=1):
        highlights.append({
            "rank": i, "start": round(start, 2), "end": round(end, 2),
            "score": 60, "title": f"Highlight {i}",
            "reason": "High-activity spoken segment.",
        })
    return highlights


# ==========================================================================
# CAPTIONS PER CLIP  (preserved logic from create_shorts.py)
# ==========================================================================

def build_clip_captions(
    master_ass: Path, clip_start: float, clip_end: float, out_ass: Path
) -> bool:
    if not master_ass.exists():
        return False

    lines = master_ass.read_text(encoding="utf-8").splitlines()
    output = [ASS_HEADER.rstrip("\n")]

    for line in lines:
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue

        o_start = ass_to_seconds(parts[1])
        o_end = ass_to_seconds(parts[2])
        if o_end <= clip_start or o_start >= clip_end:
            continue

        new_start = max(o_start, clip_start) - clip_start
        new_end = min(o_end, clip_end) - clip_start
        if new_end <= new_start:
            continue

        text = parts[9].strip()
        for word in IMPORTANT_WORDS:
            text = text.replace(
                word, r"{\c&H00FFFF&}" + word + r"{\c&HFFFFFF&}"
            )

        output.append(
            f"Dialogue: 0,{ass_time(new_start)},{ass_time(new_end)},"
            f"Gaming,,0,0,0,,{text}"
        )

    out_ass.write_text("\n".join(output), encoding="utf-8")
    return True


def _parse_clip_words(
    master_ass: Path, clip_start: float, clip_end: float
) -> list[tuple[float, float, str]]:
    """Return clip-relative (start, end, word) tuples inside the clip window."""
    if not master_ass.exists():
        return []
    words: list[tuple[float, float, str]] = []
    for line in master_ass.read_text(encoding="utf-8").splitlines():
        if not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)
        if len(parts) < 10:
            continue
        o_start = ass_to_seconds(parts[1])
        o_end = ass_to_seconds(parts[2])
        if o_end <= clip_start or o_start >= clip_end:
            continue
        s = max(o_start, clip_start) - clip_start
        e = min(o_end, clip_end) - clip_start
        if e <= s:
            continue
        text = parts[9].strip()
        if text:
            words.append((s, e, text))
    return words


def build_animated_clip_captions(
    master_ass: Path, clip_start: float, clip_end: float, out_ass: Path
) -> bool:
    """Write animated phrase captions using the configurable caption engine.

    Delegates styling/animation to :mod:`services.caption_style` (pop /
    overshoot on appearance, important-word emphasis, bold uppercase). The
    animation is baked into the ASS events, so it renders into the MP4 itself.
    """
    words = _parse_clip_words(master_ass, clip_start, clip_end)
    if not words:
        return False
    cfg = config.caption_style_config()
    return caption_style.build_caption_file(words, cfg, out_ass)


def _escape_ass_path(path: Path) -> str:
    """Escape a path for use inside FFmpeg's ass= filter (cross-platform)."""
    posix = path.resolve().as_posix()
    # Escape the Windows drive colon (harmless on POSIX, which has no colon).
    return posix.replace(":", r"\:")


# ==========================================================================
# STAGE 3: RENDER ONE SHORT  (FFmpeg command preserved exactly)
# ==========================================================================

W, H = 1080, 1920  # portrait canvas


def _grade() -> Optional[str]:
    if config.ENHANCED_EDIT and config.ENABLE_COLOR_GRADE:
        return (f"eq=contrast={config.COLOR_CONTRAST}:"
                f"saturation={config.COLOR_SATURATION}")
    return None


def _zoom(duration: float) -> Optional[str]:
    if config.ENHANCED_EDIT and config.ENABLE_ZOOM and config.ZOOM_MAX > 1.0:
        fps = 30
        total = max(1, int(duration * fps))
        zmax = config.ZOOM_MAX
        return (
            "zoompan="
            f"z='min(1+({zmax}-1)*on/{total}\\,{zmax})':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d=1:s={W}x{H}:fps={fps}"
        )
    return None


def _video_filter_chain(caption_ass: Optional[Path], duration: float) -> str:
    """Build the video filtergraph [0:v] -> [v] for the configured fit mode.

    * crop  - aspect-preserving scale-up + centre crop (fills the frame)
    * fit   - aspect-preserving scale-down + letterbox padding (black bars)
    * blur  - same as fit, but the bars are filled with a blurred copy
    """
    fit = config.VIDEO_FIT
    grade = _grade()
    ass = f"ass='{_escape_ass_path(caption_ass)}'" if (
        caption_ass and caption_ass.exists()) else None

    if fit == "fit":
        parts = [f"scale={W}:{H}:force_original_aspect_ratio=decrease"]
        if grade:
            parts.append(grade)
        parts.append(
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={config.PAD_COLOR}")
        if ass:
            parts.append(ass)
        return "[0:v]" + ",".join(parts) + "[v]"

    if fit == "blur":
        fg = [f"scale={W}:{H}:force_original_aspect_ratio=decrease"]
        if grade:
            fg.append(grade)
        graph = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale={W}:{H}:force_original_aspect_ratio=increase,"
            f"crop={W}:{H},gblur=sigma=22[bgb];"
            f"[fg]{','.join(fg)}[fgb];"
            f"[bgb][fgb]overlay=(W-w)/2:(H-h)/2"
        )
        graph += f",{ass}[v]" if ass else "[v]"
        return graph

    # default: crop-to-fill (aspect preserved - no distortion, no black bars)
    parts = [
        f"scale={W}:{H}:force_original_aspect_ratio=increase",
        f"crop={W}:{H}",
        "setsar=1",  # square pixels -> exact 9:16, never stretched by players
    ]
    if grade:
        parts.append(grade)
    z = _zoom(duration)
    if z:
        parts.append(z)
    if ass:  # captions LAST so they never scale with the frame
        parts.append(ass)
    return "[0:v]" + ",".join(parts) + "[v]"


def render_short(
    input_video: Path,
    start: float,
    end: float,
    caption_ass: Optional[Path],
    output_file: Path,
) -> tuple[bool, str]:
    duration = max(0.1, end - start)

    music = config.background_music_path() if config.ENHANCED_EDIT else None

    video_chain = _video_filter_chain(caption_ass, duration)

    inputs = ["-ss", str(start), "-i", str(input_video)]
    maps = ["-map", "[v]"]

    if music is not None:
        inputs += ["-i", str(music)]
        filter_complex = (
            video_chain + ";"
            "[0:a]volume=1.0[a0];"
            f"[1:a]aloop=loop=-1:size=2e9,volume={config.BG_MUSIC_VOLUME}[a1];"
            "[a0][a1]amix=inputs=2:duration=first:dropout_transition=0[a]"
        )
        maps += ["-map", "[a]"]
    else:
        filter_complex = video_chain
        maps += ["-map", "0:a?"]  # optional: clips without audio still render

    command = [
        "ffmpeg", "-y",
        *inputs,
        "-t", str(duration),
        "-filter_complex", filter_complex,
        *maps,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-pix_fmt", "yuv420p",
        "-profile:v", "high",
        "-level", "4.1",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        "-shortest",
        str(output_file),
    ]

    result = subprocess.run(
        command, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode == 0:
        return True, ""
    return False, (result.stderr or "")[-1500:]


# ==========================================================================
# ORCHESTRATION
# ==========================================================================

def run_pipeline(job_id: str, input_video: Path) -> None:
    """Full pipeline for one job. Updates the job store as it progresses."""
    try:
        if not input_video.exists():
            store.set_state(job_id, JobState.ERROR,
                            "Source video not found.")
            store.update(job_id, error="Source video not found.")
            return

        # Clear previous run so a fresh gallery is produced.
        for old in config.SHORTS_DIR.glob("short_*.mp4"):
            old.unlink(missing_ok=True)

        store.set_state(job_id, JobState.ANALYZING,
                        "Analyzing content...", progress=None)

        master_ass = config.SHORTS_DIR / "master_captions.ass"
        segments = transcribe(input_video, master_ass, job_id=job_id)
        has_captions = master_ass.exists() and bool(segments)

        duration = get_duration(input_video)

        store.set_state(job_id, JobState.PROCESSING,
                        "Finding the best moments...", progress=None)
        highlights, source = select_highlights(segments, duration)
        store.update(job_id, highlight_source=source)

        if not highlights:
            store.set_state(job_id, JobState.ERROR,
                            "Could not find any usable moments in this video.")
            store.update(job_id,
                         error="Could not find any usable moments.")
            return

        total = len(highlights)
        shorts: list[dict[str, Any]] = []

        for idx, item in enumerate(highlights, start=1):
            rank = item.get("rank", idx)
            start = float(item["start"])
            end = float(item["end"])

            store.set_state(
                job_id, JobState.GENERATING,
                f"Rendering Short {idx} of {total}...",
                stage=f"Rendering Short {idx} of {total}",
                progress=idx / total,
            )

            caption_file = None
            if has_captions:
                caption_file = config.SHORTS_DIR / f"captions_{rank:02d}.ass"
                if config.ENHANCED_EDIT and config.ANIMATED_CAPTIONS:
                    ok_cap = build_animated_clip_captions(
                        master_ass, start, end, caption_file)
                    if not ok_cap:  # fall back to static captions
                        build_clip_captions(master_ass, start, end, caption_file)
                else:
                    build_clip_captions(master_ass, start, end, caption_file)

            output_file = config.SHORTS_DIR / f"short_{rank:02d}.mp4"
            ok, err = render_short(
                input_video, start, end, caption_file, output_file
            )
            if ok:
                shorts.append({
                    "filename": output_file.name,
                    "url": f"/video/{output_file.name}",
                    "download_url": f"/download/{output_file.name}",
                    "rank": rank,
                    "title": item.get("title", f"Short {rank}"),
                    "duration": round(end - start, 1),
                })
            else:
                log.error("Short #%s failed: %s", rank, err)

        if not shorts:
            store.set_state(job_id, JobState.ERROR,
                            "Video processing failed while rendering Shorts.")
            store.update(job_id,
                         error="Rendering failed for all Shorts.")
            return

        shorts.sort(key=lambda s: s["rank"])

        # Mirror to cloud storage when configured (no-op locally).
        try:
            from .storage_service import storage
            storage.publish_shorts()
        except Exception:
            log.warning("publish_shorts failed", exc_info=True)

        store.update(job_id, shorts=shorts)
        store.set_state(
            job_id, JobState.COMPLETED,
            f"{len(shorts)} Shorts created successfully!",
            progress=1.0,
        )
    except Exception as exc:  # Never leak a traceback to the client.
        log.exception("Pipeline crashed for job %s", job_id)
        store.set_state(job_id, JobState.ERROR, "Video processing failed.")
        store.update(job_id, error="Video processing failed.")
        _ = exc
