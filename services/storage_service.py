"""Storage abstraction so we can switch local disk <-> Cloud Storage later.

Local development uses :class:`LocalStorageService`. A future Cloud Run
deployment can set ``STORAGE_BACKEND=gcs`` and supply ``GCS_BUCKET`` to use
:class:`CloudStorageService` without touching the pipeline code.

The pipeline itself always works against local file paths (FFmpeg/Whisper need
real files); the cloud backend is responsible for syncing finished Shorts to
the bucket and producing public/download URLs.
"""

from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from . import config


class StorageService(ABC):
    """Common interface for storing source uploads and generated Shorts."""

    @abstractmethod
    def save_upload(self, file_obj: BinaryIO, filename: str) -> Path:
        """Persist an uploaded source video and return its local path."""

    @abstractmethod
    def source_path(self, filename: str) -> Path:
        """Return the local path where a source video lives."""

    @abstractmethod
    def short_path(self, filename: str) -> Path:
        """Return the local path of a generated Short."""

    @abstractmethod
    def publish_shorts(self) -> None:
        """Publish generated Shorts to their final location (no-op locally)."""


class LocalStorageService(StorageService):
    """Reads and writes everything on the local filesystem."""

    def __init__(self) -> None:
        self.upload_dir = config.UPLOAD_DIR
        self.shorts_dir = config.SHORTS_DIR
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.shorts_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file_obj: BinaryIO, filename: str) -> Path:
        target = self.upload_dir / filename
        with open(target, "wb") as out:
            shutil.copyfileobj(file_obj, out, length=1024 * 1024)
        return target

    def source_path(self, filename: str) -> Path:
        return self.upload_dir / filename

    def short_path(self, filename: str) -> Path:
        return self.shorts_dir / filename

    def publish_shorts(self) -> None:  # Nothing to do for local storage.
        return None


class CloudStorageService(LocalStorageService):
    """Local-disk pipeline that also mirrors finished Shorts to GCS.

    We still process on local disk (FFmpeg/Whisper require real files), then
    upload the results. Falls back gracefully if the GCS client or bucket is
    not configured so it never breaks a running instance.
    """

    def __init__(self) -> None:
        super().__init__()
        self.bucket_name = config.GCS_BUCKET
        self._bucket = None

    def _bucket_handle(self):
        if self._bucket is not None:
            return self._bucket
        if not self.bucket_name:
            return None
        try:  # Imported lazily so local dev needs no GCS dependency.
            from google.cloud import storage  # type: ignore

            client = storage.Client()
            self._bucket = client.bucket(self.bucket_name)
            return self._bucket
        except Exception:  # pragma: no cover - depends on cloud env
            return None

    def publish_shorts(self) -> None:
        bucket = self._bucket_handle()
        if bucket is None:
            return
        for short in sorted(self.shorts_dir.glob("short_*.mp4")):
            blob = bucket.blob(f"auto_shorts/{short.name}")
            blob.upload_from_filename(str(short))


def get_storage() -> StorageService:
    """Factory that returns the configured storage backend."""
    if config.STORAGE_BACKEND.lower() == "gcs":
        return CloudStorageService()
    return LocalStorageService()


storage = get_storage()
