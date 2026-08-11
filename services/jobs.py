"""In-memory job store and state machine for long-running pipeline work.

A single-worker uvicorn / single Cloud Run instance keeps this simple: jobs
live in a process-local dict guarded by a lock. Each job exposes a coarse
state plus a human-readable status message and (optional) progress numbers so
the frontend can render meaningful, non-fake progress.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class JobState(str, Enum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"       # fetching / normalizing the source video
    UPLOADED = "UPLOADED"
    ANALYZING = "ANALYZING"       # transcription
    PROCESSING = "PROCESSING"     # highlight selection
    GENERATING = "GENERATING"     # rendering Shorts
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


@dataclass
class Job:
    id: str
    source_type: str                       # "upload" | "youtube"
    state: JobState = JobState.QUEUED
    message: str = "Queued..."
    stage: str = ""                        # e.g. "Rendering Short 3 of 10"
    progress: Optional[float] = None       # 0..1, or None for indeterminate
    source_filename: Optional[str] = None  # normalized source video filename
    shorts: list[dict[str, Any]] = field(default_factory=list)
    highlight_source: Optional[str] = None  # "ai" | "heuristic"
    error: Optional[str] = None            # user-friendly error message
    title: Optional[str] = None            # source title (YouTube)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        data["elapsed"] = round(time.time() - self.created_at, 1)
        return data


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, source_type: str, **kwargs: Any) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], source_type=source_type, **kwargs)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: Any) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = time.time()
            return job

    def set_state(
        self,
        job_id: str,
        state: JobState,
        message: str,
        *,
        stage: str = "",
        progress: Optional[float] = None,
    ) -> Optional[Job]:
        return self.update(
            job_id,
            state=state,
            message=message,
            stage=stage,
            progress=progress,
        )


store = JobStore()
