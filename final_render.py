import json
import subprocess
from pathlib import Path

INPUT_VIDEO = Path("uploads/uploadstest_with_audio.mp4")
SOURCE_ASS = Path("captions.ass")
OUTPUT_DIR = Path("outputs/final_shorts")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))

    if cs >= 100:
        s += 1
        cs = 0

    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def create_caption_file(start_time, end_time, output_ass):
    lines = SOURCE_ASS.read_text(encoding="utf-8").splitlines()

    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Gaming,Arial,82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,6,3,5,50,50,150,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
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

    output_lines = header

    for line in lines:

        if not line.startswith("Dialogue:"):
            continue

        parts = line.split(",", 9)

        if len(parts) < 10:
            continue

        original_start = ass_to_seconds(parts[1])
        original_end = ass_to_seconds(parts[2])

        if original_end <= start_time:
            continue

        if original_start >= end_time:
            continue

        new_start = max(original_start, start_time) - start_time
        new_end = min(original_end, end_time) - start_time

        text = parts[9].strip()

        for word in important_words:
            text = text.replace(
                word,
                r"{\c&H00FFFF&}" + word + r"{\c&HFFFFFF&}"
            )

        output_lines.append(
            f"Dialogue: 0,"
            f"{seconds_to_ass(new_start)},"
            f"{seconds_to_ass(new_end)},"
            f"Gaming,,0,0,0,,{text}"
        )

    output_ass.write_text(
        "\n".join(output_lines),
        encoding="utf-8"
    )


with open("highlights.json", "r", encoding="utf-8") as f:
    data = json.load(f)

highlights = data["highlights"]

for item in highlights:

    rank = item["rank"]
    start = float(item["start"])
    end = float(item["end"])
    duration = end - start

    caption_file = OUTPUT_DIR / f"captions_{rank:02d}.ass"
    output_file = OUTPUT_DIR / f"short_{rank:02d}_final.mp4"

    print(f"\n🎬 Creating Short #{rank}")
    print(f"Start: {start:.2f}s")
    print(f"End: {end:.2f}s")
    print(f"Duration: {duration:.2f}s")

    create_caption_file(
        start,
        end,
        caption_file
    )

    command = [
        "ffmpeg",
        "-y",

        "-ss", str(start),
        "-i", str(INPUT_VIDEO),

        "-t", str(duration),

        "-vf",
        f"scale=1188:2112,"
        f"crop=1080:1920:(iw-1080)/2:(ih-1920)/2,"
        f"ass={caption_file.as_posix()}",

        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",

        str(output_file)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"✅ Created: {output_file}")
    else:
        print(f"❌ Failed Short #{rank}")
        print(result.stderr[-2000:])


print("\n🎉 FINAL SHORTS CREATED!")
print(f"Output folder: {OUTPUT_DIR}")