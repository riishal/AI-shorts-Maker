"""AI Shorts Maker - FastAPI entry point.

Thin HTTP layer. All real work lives in ``services/``:
    * services.youtube_service - YouTube source preparation (yt-dlp)
    * services.shorts_service   - unified AI pipeline (transcribe/highlight/render)
    * services.storage_service  - local/cloud storage abstraction
    * services.jobs             - background job state machine

Both the local-upload flow and the YouTube flow converge on the SAME pipeline
(`shorts_service.run_pipeline`) via a normalized local source video.

Run locally:
    uvicorn main:app --reload --port 8000

Run in Cloud Run (see Dockerfile):
    uvicorn main:app --host 0.0.0.0 --port ${PORT}
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from services import config
from services import security
from services import youtube_service
from services import shorts_service
from services.jobs import JobState, store
from services.storage_service import storage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("main")

app = FastAPI(title="AI Shorts Maker")


# ==========================================================================
# CORS  (configurable via env; localhost always allowed for dev)
# ==========================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_origin_regex=config.ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================================================
# HELPERS
# ==========================================================================

def _run_job_in_thread(job_id: str, source_video: Path) -> None:
    thread = threading.Thread(
        target=shorts_service.run_pipeline,
        args=(job_id, source_video),
        daemon=True,
    )
    thread.start()


def _error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


# ==========================================================================
# HEALTH
# ==========================================================================

@app.get("/")
def home():
    return {"message": "AI Shorts Maker API is running!"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ==========================================================================
# LOCAL UPLOAD
# ==========================================================================

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Accept a local video upload and store it as a normalized source."""
    try:
        safe_name = security.safe_video_filename(file.filename or "")
    except security.UnsafeFilenameError as exc:
        return _error(str(exc))

    target = config.UPLOAD_DIR / safe_name
    written = 0
    try:
        with open(target, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > config.MAX_UPLOAD_BYTES:
                    buffer.close()
                    target.unlink(missing_ok=True)
                    return _error(
                        f"File too large. Maximum size is "
                        f"{config.MAX_UPLOAD_MB} MB.",
                        status=413,
                    )
                buffer.write(chunk)
    except Exception:
        log.exception("Upload failed")
        target.unlink(missing_ok=True)
        return _error("Upload failed. Please try again.", status=500)

    return {
        "message": "Video uploaded successfully!",
        "filename": safe_name,
    }


# ==========================================================================
# AI SHORTS FROM AN UPLOADED FILE  (starts a background job)
# ==========================================================================

@app.post("/create-ai-shorts/{filename}")
def create_ai_shorts(filename: str):
    try:
        source = security.resolve_within(config.UPLOAD_DIR, filename)
    except security.UnsafeFilenameError as exc:
        return _error(str(exc))

    if not source.exists():
        return _error("Video not found. Please upload it again.", status=404)

    job = store.create("upload", source_filename=source.name)
    store.set_state(job.id, JobState.QUEUED, "Preparing video...")
    _run_job_in_thread(job.id, source)

    return {"job_id": job.id, "status": job.state.value}


# ==========================================================================
# YOUTUBE: ANALYZE (validate + metadata, no download)
# ==========================================================================

class YouTubeRequest(BaseModel):
    url: str


@app.post("/youtube/analyze")
def youtube_analyze(payload: YouTubeRequest):
    if not youtube_service.is_supported(payload.url):
        return _error("Unsupported YouTube URL.")
    try:
        info = youtube_service.get_metadata(payload.url)
    except youtube_service.YouTubeError as exc:
        return _error(str(exc))
    except Exception:
        log.exception("YouTube analyze failed")
        return _error("Could not analyze this YouTube video.", status=500)
    return info


# ==========================================================================
# YOUTUBE: PROCESS (download -> pipeline, as a background job)
# ==========================================================================

@app.post("/youtube/process")
def youtube_process(payload: YouTubeRequest):
    if not youtube_service.is_supported(payload.url):
        return _error("Unsupported YouTube URL.")

    job = store.create("youtube")
    store.set_state(job.id, JobState.PREPARING, "Preparing video...")

    def _worker() -> None:
        try:
            def _dl_progress(frac):
                pct = f" ({int(frac * 100)}%)" if frac else ""
                store.set_state(
                    job.id, JobState.PREPARING,
                    f"Downloading video from YouTube...{pct}",
                    progress=frac,
                )

            source, meta = youtube_service.download(
                payload.url, on_progress=_dl_progress
            )
            store.update(job.id, source_filename=source.name,
                         title=meta.get("title"))
            store.set_state(job.id, JobState.PREPARING,
                            "Video ready. Starting analysis...")
            shorts_service.run_pipeline(job.id, source)
        except youtube_service.YouTubeError as exc:
            store.set_state(job.id, JobState.ERROR, str(exc))
            store.update(job.id, error=str(exc))
        except Exception:
            log.exception("YouTube job failed")
            store.set_state(job.id, JobState.ERROR,
                            "Could not process this YouTube video.")
            store.update(job.id, error="Could not process this YouTube video.")

    threading.Thread(target=_worker, daemon=True).start()
    return {"job_id": job.id, "status": job.state.value}


# ==========================================================================
# JOB STATUS
# ==========================================================================

@app.get("/status/{job_id}")
def job_status(job_id: str):
    job = store.get(job_id)
    if job is None:
        return _error("Job not found.", status=404)
    return job.to_dict()


# ==========================================================================
# LIST GENERATED SHORTS
# ==========================================================================

@app.get("/shorts")
def get_shorts():
    files = sorted(config.SHORTS_DIR.glob("short_*.mp4"))
    return {
        "shorts": [
            {
                "filename": f.name,
                "url": f"/video/{f.name}",
                "download_url": f"/download/{f.name}",
            }
            for f in files
        ]
    }


# ==========================================================================
# SERVE / DOWNLOAD  (path-traversal safe)
# ==========================================================================

@app.get("/video/{filename}")
def get_video(filename: str):
    try:
        path = security.resolve_within(config.SHORTS_DIR, filename)
    except security.UnsafeFilenameError:
        return _error("Invalid filename.")
    if not path.exists():
        return _error("Video not found.", status=404)
    return FileResponse(
        path=path,
        media_type="video/mp4",
        filename=path.name,
        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"},
    )


@app.get("/download/{filename}")
def download_video(filename: str):
    try:
        path = security.resolve_within(config.SHORTS_DIR, filename)
    except security.UnsafeFilenameError:
        return _error("Invalid filename.")
    if not path.exists():
        return _error("Video not found.", status=404)
    return FileResponse(
        path=path,
        media_type="application/octet-stream",
        filename=path.name,
        headers={
            "Content-Disposition": f'attachment; filename="{path.name}"',
        },
    )
