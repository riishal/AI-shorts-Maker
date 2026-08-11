"""Service layer for the AI Shorts Maker backend.

Modules:
    config           - environment-driven settings
    security         - filename sanitization and safe path handling
    storage_service  - local / cloud storage abstraction
    jobs             - in-memory job store and state machine
    youtube_service  - YouTube source preparation via yt-dlp
    shorts_service   - unified AI pipeline (transcribe -> highlights -> render)
"""
