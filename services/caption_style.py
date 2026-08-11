"""Reusable animated-caption engine (TikTok / Minecraft Shorts style).

All visual values live in :class:`CaptionStyleConfig` (no magic numbers
scattered through the render code). Named presets (``minecraft``, ``gaming``,
``minimal``) can be selected/overridden via environment, and new styles can be
added without touching the pipeline.

The output is an ASS subtitle file whose events contain REAL animation baked
in via libass ``\\t`` transforms, so the effect is present in the final MP4 -
not only in a preview:

* short phrases (2-5 words) tightly synced to speech
* a subtle pop/overshoot on appearance: start small -> overshoot -> settle
  (e.g. 88% -> 106% -> 100%)
* important/emotional words emphasised in a highlight colour
* bold uppercase white text, strong black outline + shadow, centred lower-mid
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

# Default set of emphasis words (matched case-insensitively, punctuation
# stripped). The AI decides WHAT is said; the engine decides which of those
# words get extra punch.
DEFAULT_IMPORTANT_WORDS: tuple[str, ...] = (
    "WAIT", "WHAT", "HOW", "WHY", "NO", "BRO", "CRAZY", "WRONG", "DIED",
    "DIE", "DEAD", "KILL", "KILLED", "RUN", "LOOK", "OMG", "INSANE", "STOP",
    "OH", "WHOA", "GG", "WIN", "WON", "LOST", "HELP", "YES", "NEVER", "BRUH",
    "IMPOSSIBLE", "FINALLY", "ACTUALLY", "SUDDENLY", "BOOM", "NOOO",
)


@dataclass
class CaptionStyleConfig:
    """Every configurable caption/animation value in one place."""

    name: str = "Minecraft"

    # -- typography --
    font: str = "Arial"
    font_size: int = 84
    bold: bool = True
    # ASS colours are &HAABBGGRR (AA=00 -> opaque).
    primary_color: str = "&H00FFFFFF"   # white
    outline_color: str = "&H00000000"   # black
    back_color: str = "&HA0000000"      # soft drop shadow
    outline_width: float = 6.0
    shadow: float = 2.5
    spacing: float = 0.0                # letter spacing (px); tight = 0

    # -- layout (1080x1920 canvas) --
    alignment: int = 2                  # 2 = bottom-centre anchor
    margin_l: int = 40
    margin_r: int = 40
    margin_v: int = 900                 # distance from bottom -> centre/lower

    # -- phrasing --
    max_words: int = 4
    pause_gap: float = 0.35             # start a new phrase after this silence
    min_display: float = 0.5            # min seconds a phrase stays up

    # -- sync --
    # Global timing nudge in milliseconds. Negative shows captions EARLIER
    # (compensates Whisper's tendency to timestamp words slightly late);
    # positive shows them later. Applied to every caption.
    offset_ms: int = -120
    # Small gap kept between consecutive phrases so one clears before the next.
    inter_gap: float = 0.04

    # -- emphasis --
    highlight_color: str = "&H0000FFFF"  # yellow (&HAABBGGRR)
    important_words: tuple[str, ...] = field(default_factory=lambda: DEFAULT_IMPORTANT_WORDS)

    # -- pop / overshoot animation --
    uppercase: bool = True
    pop_start_scale: int = 88
    pop_overshoot_scale: int = 106
    pop_settle_scale: int = 100
    pop_overshoot_ms: int = 70          # small -> overshoot
    pop_settle_ms: int = 150            # overshoot -> settle
    fade_in_ms: int = 40
    fade_out_ms: int = 20

    def with_overrides(self, **kwargs) -> "CaptionStyleConfig":
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean)


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------

PRESETS: dict[str, CaptionStyleConfig] = {
    "minecraft": CaptionStyleConfig(name="Minecraft"),
    "gaming": CaptionStyleConfig(
        name="Gaming",
        font_size=90,
        outline_width=7.0,
        highlight_color="&H00FFFF00",   # cyan
        margin_v=880,
        pop_overshoot_scale=110,
    ),
    "minimal": CaptionStyleConfig(
        name="Minimal",
        font_size=76,
        outline_width=4.0,
        shadow=1.5,
        highlight_color="&H00FFFFFF",   # no colour emphasis (white)
        pop_start_scale=95,
        pop_overshoot_scale=102,
        max_words=5,
    ),
}


def get_preset(name: str) -> CaptionStyleConfig:
    return PRESETS.get((name or "minecraft").lower().strip(), PRESETS["minecraft"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _inline_color(ass_color: str) -> str:
    """Convert an &HAABBGGRR style colour to the inline \\c&HBBGGRR& form."""
    hexpart = ass_color.replace("&H", "").replace("&", "")
    bgr = hexpart[-6:] if len(hexpart) >= 6 else hexpart
    return f"&H{bgr}&"


_WORD_KEY = re.compile(r"[^A-Za-z0-9]")


def _is_important(token: str, important: set[str]) -> bool:
    key = _WORD_KEY.sub("", token).upper()
    return bool(key) and key in important


# --------------------------------------------------------------------------
# ASS header / style line
# --------------------------------------------------------------------------

def build_header(cfg: CaptionStyleConfig) -> str:
    bold = 1 if cfg.bold else 0
    style = (
        f"Style: Cap,{cfg.font},{cfg.font_size},"
        f"{cfg.primary_color},{cfg.primary_color},"
        f"{cfg.outline_color},{cfg.back_color},"
        f"{bold},0,0,0,100,100,{cfg.spacing},0,1,"
        f"{cfg.outline_width},{cfg.shadow},"
        f"{cfg.alignment},{cfg.margin_l},{cfg.margin_r},{cfg.margin_v},1"
    )
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "WrapStyle: 0\n"
        "ScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"{style}\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
    )


# --------------------------------------------------------------------------
# Phrase grouping
# --------------------------------------------------------------------------

def group_phrases(
    words: list[tuple[float, float, str]], cfg: CaptionStyleConfig
) -> list[list[tuple[float, float, str]]]:
    """Split a word list into short, speech-synced phrases."""
    phrases: list[list[tuple[float, float, str]]] = []
    current: list[tuple[float, float, str]] = []

    for w in words:
        if current:
            gap = w[0] - current[-1][1]
            prev_token = current[-1][2]
            ends_sentence = prev_token.endswith((".", "!", "?"))
            if (
                len(current) >= cfg.max_words
                or gap > cfg.pause_gap
                or ends_sentence
            ):
                phrases.append(current)
                current = []
        current.append(w)

    if current:
        phrases.append(current)
    return phrases


# --------------------------------------------------------------------------
# Event builder
# --------------------------------------------------------------------------

def _anim_prefix(cfg: CaptionStyleConfig) -> str:
    """The per-phrase pop/overshoot + fade override placed at line start."""
    t1 = cfg.pop_overshoot_ms
    t2 = cfg.pop_overshoot_ms + cfg.pop_settle_ms
    return (
        f"{{\\fad({cfg.fade_in_ms},{cfg.fade_out_ms})"
        f"\\fscx{cfg.pop_start_scale}\\fscy{cfg.pop_start_scale}"
        f"\\t(0,{t1},\\fscx{cfg.pop_overshoot_scale}\\fscy{cfg.pop_overshoot_scale})"
        f"\\t({t1},{t2},\\fscx{cfg.pop_settle_scale}\\fscy{cfg.pop_settle_scale})}}"
    )


def _phrase_spans(
    phrases: list[list[tuple[float, float, str]]], cfg: CaptionStyleConfig
) -> list[tuple[float, float]]:
    """Compute (start, end) per phrase, tightly synced and non-overlapping.

    * end = last spoken word's end, extended to ``min_display`` only when the
      next phrase leaves room (so a caption never lingers over the next one).
    * a small ``inter_gap`` is kept between consecutive phrases.
    * a global ``offset_ms`` nudge is applied last (negative = earlier).
    """
    spans: list[tuple[float, float]] = []
    offset = cfg.offset_ms / 1000.0

    for i, phrase in enumerate(phrases):
        start = phrase[0][0]
        natural_end = phrase[-1][1]
        end = max(natural_end, start + cfg.min_display)

        # Never overlap the next phrase's first word.
        if i + 1 < len(phrases):
            next_start = phrases[i + 1][0][0]
            end = min(end, next_start - cfg.inter_gap)

        # Guard against degenerate/negative spans after clamping.
        if end <= start:
            end = start + max(0.2, natural_end - start)

        s = max(0.0, start + offset)
        e = max(s + 0.2, end + offset)
        spans.append((s, e))

    return spans


def build_events(
    words: list[tuple[float, float, str]], cfg: CaptionStyleConfig
) -> list[str]:
    """Return ASS Dialogue lines for the given clip-relative words."""
    important = {w.upper() for w in cfg.important_words}
    primary_inline = _inline_color(cfg.primary_color)
    highlight_inline = _inline_color(cfg.highlight_color)

    phrases = group_phrases(words, cfg)
    spans = _phrase_spans(phrases, cfg)

    lines: list[str] = []
    for phrase, (start, end) in zip(phrases, spans):
        tokens = []
        for _s, _e, token in phrase:
            text = token.upper() if cfg.uppercase else token
            text = text.replace("{", "").replace("}", "").replace("\\", "")
            if _is_important(token, important) and highlight_inline != primary_inline:
                tokens.append(
                    f"{{\\c{highlight_inline}}}{text}{{\\c{primary_inline}}}"
                )
            else:
                tokens.append(text)

        body = " ".join(tokens)
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Cap,,0,0,0,,"
            f"{_anim_prefix(cfg)}{body}"
        )
    return lines


def build_caption_file(
    words: list[tuple[float, float, str]],
    cfg: CaptionStyleConfig,
    out_path: Path,
) -> bool:
    """Write a full animated ASS file. Returns False if there are no words."""
    if not words:
        return False
    content = build_header(cfg) + "\n".join(build_events(words, cfg))
    out_path.write_text(content, encoding="utf-8")
    return True
