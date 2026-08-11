"""Filename sanitization and safe path handling.

Never trust a user-supplied filename. These helpers strip path components,
whitelist characters, enforce allowed extensions, and guarantee that a
resolved path stays inside its intended base directory (no path traversal).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from pathlib import Path

from . import config

_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_MULTI_DASH = re.compile(r"[-_]{2,}")


class UnsafeFilenameError(ValueError):
    """Raised when a filename cannot be made safe or has a bad extension."""


def sanitize_filename(filename: str) -> str:
    """Return a safe basename with a whitelisted set of characters.

    Strips any directory components, normalizes unicode, removes unsafe
    characters, and ensures a non-empty result. Does not validate the
    extension - use :func:`safe_video_filename` for uploads.
    """
    if not filename:
        raise UnsafeFilenameError("Empty filename.")

    # Drop any path components a client may have smuggled in.
    name = Path(filename.replace("\\", "/")).name

    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = _SAFE_CHARS.sub("_", name).strip("._-")
    name = _MULTI_DASH.sub("_", name)

    if not name or name in {".", ".."}:
        raise UnsafeFilenameError("Filename resolves to an unsafe value.")

    return name


def safe_video_filename(filename: str) -> str:
    """Sanitize an uploaded video filename and validate its extension.

    Prepends a short unique token so repeated uploads of the same name do not
    clobber each other while remaining human-readable.
    """
    name = sanitize_filename(filename)
    suffix = Path(name).suffix.lower()

    if suffix not in config.ALLOWED_VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_VIDEO_EXTENSIONS))
        raise UnsafeFilenameError(
            f"Unsupported file type '{suffix or '?'}'. Allowed: {allowed}"
        )

    stem = Path(name).stem[:60] or "video"
    token = uuid.uuid4().hex[:8]
    return f"{stem}_{token}{suffix}"


def resolve_within(base_dir: Path, filename: str) -> Path:
    """Resolve ``filename`` inside ``base_dir`` and reject traversal.

    Returns the resolved path only if it is genuinely contained within
    ``base_dir``. Raises :class:`UnsafeFilenameError` otherwise.
    """
    safe_name = sanitize_filename(filename)
    base = base_dir.resolve()
    candidate = (base / safe_name).resolve()

    if base != candidate and base not in candidate.parents:
        raise UnsafeFilenameError("Path escapes the allowed directory.")

    return candidate
