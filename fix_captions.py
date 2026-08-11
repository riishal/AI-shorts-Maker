from pathlib import Path
import re

INPUT_ASS = Path("captions.ass")
OUTPUT_ASS = Path("captions_short_01.ass")

CLIP_START = 141.31
CLIP_END = 168.61


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
    if seconds < 0:
        seconds = 0

    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))

    if cs >= 100:
        s += 1
        cs = 0

    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


lines = INPUT_ASS.read_text(encoding="utf-8").splitlines()

output_lines = []

for line in lines:

    if not line.startswith("Dialogue:"):
        output_lines.append(line)
        continue

    parts = line.split(",", 9)

    if len(parts) < 10:
        continue

    start = ass_to_seconds(parts[1])
    end = ass_to_seconds(parts[2])

    # Skip captions outside this Short
    if end <= CLIP_START or start >= CLIP_END:
        continue

    # Convert original timestamps to Short timestamps
    new_start = max(start, CLIP_START) - CLIP_START
    new_end = min(end, CLIP_END) - CLIP_START

    parts[1] = seconds_to_ass(new_start)
    parts[2] = seconds_to_ass(new_end)

    output_lines.append(",".join(parts))


OUTPUT_ASS.write_text(
    "\n".join(output_lines),
    encoding="utf-8"
)

print("Short #1 captions created:")
print(OUTPUT_ASS)