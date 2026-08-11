import json
import subprocess
import sys
from pathlib import Path


# ============================================================
# WINDOWS UTF-8 OUTPUT FIX
# ============================================================

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="replace",
    )

if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(
        encoding="utf-8",
        errors="replace",
    )


# ============================================================
# INPUT VIDEO
# ============================================================

if len(sys.argv) < 2:
    print("ERROR: No input video supplied.")
    print("Usage: python create_shorts.py <video_path>")
    sys.exit(1)

INPUT_VIDEO = Path(sys.argv[1])

if not INPUT_VIDEO.exists():
    print(f"ERROR: Video not found: {INPUT_VIDEO}")
    sys.exit(1)


# ============================================================
# FILES
# ============================================================

SOURCE_ASS = Path("captions.ass")
HIGHLIGHTS_FILE = Path("highlights.json")

OUTPUT_DIR = Path("outputs/auto_shorts")
OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# ASS TIME HELPERS
# ============================================================

def ass_to_seconds(value):
    h, m, s = value.split(":")

    sec, cs = s.split(".")

    return (
        int(h) * 3600
        + int(m) * 60
        + int(sec)
        + int(cs) / 100
    )


def seconds_to_ass(seconds):
    seconds = max(0, seconds)

    h = int(seconds // 3600)

    m = int(
        (seconds % 3600) // 60
    )

    s = int(seconds % 60)

    cs = int(
        round(
            (seconds - int(seconds)) * 100
        )
    )

    if cs >= 100:
        s += 1
        cs = 0

    return (
        f"{h}:"
        f"{m:02d}:"
        f"{s:02d}."
        f"{cs:02d}"
    )


# ============================================================
# CREATE CAPTIONS FOR CLIP
# ============================================================

def create_captions(
    clip_start,
    clip_end,
    output_ass,
):

    if not SOURCE_ASS.exists():
        print(
            "WARNING: captions.ass not found."
        )
        return False

    lines = SOURCE_ASS.read_text(
        encoding="utf-8"
    ).splitlines()

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, "
            "PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, "
            "ScaleX, ScaleY, Spacing, Angle, "
            "BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, "
            "MarginV, Encoding"
        ),
        (
            "Style: Gaming,Arial,82,"
            "&H00FFFFFF,&H00FFFFFF,"
            "&H00000000,&H80000000,"
            "1,0,0,0,100,100,0,0,1,"
            "6,3,5,50,50,150,1"
        ),
        "",
        "[Events]",
        (
            "Format: Layer, Start, End, Style, "
            "Name, MarginL, MarginR, MarginV, "
            "Effect, Text"
        ),
    ]

    important_words = [
        "WAIT",
        "WHAT",
        "NO",
        "OH",
        "WHOA",
        "GUYS",
        "SOMEONE",
        "SKELETON",
        "KILL",
        "DIE",
        "CRAZY",
        "20,000",
    ]

    output = header

    for line in lines:

        if not line.startswith(
            "Dialogue:"
        ):
            continue

        parts = line.split(",", 9)

        if len(parts) < 10:
            continue

        original_start = ass_to_seconds(
            parts[1]
        )

        original_end = ass_to_seconds(
            parts[2]
        )

        # Caption is outside the clip
        if original_end <= clip_start:
            continue

        if original_start >= clip_end:
            continue

        # Shift timestamp relative to Short
        new_start = (
            max(
                original_start,
                clip_start,
            )
            - clip_start
        )

        new_end = (
            min(
                original_end,
                clip_end,
            )
            - clip_start
        )

        if new_end <= new_start:
            continue

        text = parts[9].strip()

        # Highlight important words
        for word in important_words:
            text = text.replace(
                word,
                r"{\c&H00FFFF&}"
                + word
                + r"{\c&HFFFFFF&}",
            )

        output.append(
            "Dialogue: 0,"
            + seconds_to_ass(new_start)
            + ","
            + seconds_to_ass(new_end)
            + ",Gaming,,0,0,0,,"
            + text
        )

    output_ass.write_text(
        "\n".join(output),
        encoding="utf-8",
    )

    return True


# ============================================================
# LOAD HIGHLIGHTS
# ============================================================

if not HIGHLIGHTS_FILE.exists():
    print(
        "ERROR: highlights.json not found."
    )
    sys.exit(1)


with open(
    HIGHLIGHTS_FILE,
    "r",
    encoding="utf-8",
) as f:

    data = json.load(f)


highlights = data.get(
    "highlights",
    [],
)

if not highlights:
    print(
        "ERROR: No highlights found."
    )
    sys.exit(1)


# ============================================================
# PROCESS ALL HIGHLIGHTS
# ============================================================

created = 0


for item in highlights:

    rank = item["rank"]

    start = float(
        item["start"]
    )

    end = float(
        item["end"]
    )

    title = item.get(
        "title",
        f"Short {rank}",
    )

    duration = end - start

    caption_file = (
        OUTPUT_DIR
        / f"captions_{rank:02d}.ass"
    )

    output_file = (
        OUTPUT_DIR
        / f"short_{rank:02d}.mp4"
    )

    print()
    print("=" * 60)

    print(
        f"🎬 SHORT #{rank}"
    )

    print(
        f"Title: {title}"
    )

    print(
        f"Start: {start:.2f}s"
    )

    print(
        f"End: {end:.2f}s"
    )

    print(
        f"Duration: {duration:.2f}s"
    )

    # --------------------------------------------------------
    # CAPTIONS
    # --------------------------------------------------------

    captions_created = create_captions(
        start,
        end,
        caption_file,
    )

    if not captions_created:
        print(
            "⚠️ Captions could not be created."
        )

    # --------------------------------------------------------
    # FFMPEG ASS PATH
    # --------------------------------------------------------

    caption_path = (
        caption_file
        .resolve()
        .as_posix()
    )

    # Escape Windows drive colon
    caption_path = caption_path.replace(
        ":",
        r"\:",
    )

    # --------------------------------------------------------
    # FFMPEG
    # --------------------------------------------------------

    command = [
        "ffmpeg",
        "-y",

        "-ss",
        str(start),

        "-i",
        str(INPUT_VIDEO),

        "-t",
        str(duration),

        "-vf",
        (
            "scale=1188:2112,"
            "crop=1080:1920:"
            "(iw-1080)/2:"
            "(ih-1920)/2,"
            f"ass='{caption_path}'"
        ),
"-c:v",
"libx264",

"-preset",
"veryfast",

"-pix_fmt",
"yuv420p",

"-profile:v",
"high",

"-level",
"4.1",

"-c:a",
"aac",

"-b:a",
"128k",

"-movflags",
"+faststart",

str(output_file),
    ]

    print(
        "⚙️ Rendering..."
    )

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

    except Exception as e:

        print(
            f"❌ FFmpeg exception: {e}"
        )

        continue

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    if result.returncode == 0:

        created += 1

        print(
            f"✅ Created: {output_file}"
        )

    else:

        print(
            f"❌ Failed Short #{rank}"
        )

        print(
            result.stderr[-2000:]
        )


# ============================================================
# FINAL RESULT
# ============================================================

print()
print("=" * 60)

print(
    f"🎉 Created {created}/{len(highlights)} Shorts"
)

print(
    f"Output folder: {OUTPUT_DIR.resolve()}"
)

if created != len(highlights):

    print(
        "⚠️ Some Shorts failed."
    )

    sys.exit(1)


print(
    "✅ All Shorts created successfully!"
)