import json
import subprocess
from pathlib import Path

INPUT_VIDEO = Path("uploads/uploadstest_with_audio.mp4")
OUTPUT_DIR = Path("outputs/shorts")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with open("highlights.json", "r", encoding="utf-8") as f:
    data = json.load(f)

highlights = data["highlights"]

for item in highlights:
    rank = item["rank"]
    start = item["start"]
    end = item["end"]

    output_file = OUTPUT_DIR / f"short_{rank:02d}.mp4"

    duration = end - start

    print(f"\nCreating Short #{rank}")
    print(f"Start: {start}")
    print(f"End: {end}")
    print(f"Duration: {duration:.2f}s")

    command = [
        "ffmpeg",
        "-y",
        "-ss", str(start),
        "-i", str(INPUT_VIDEO),
        "-t", str(duration),

        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920",

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
        print(result.stderr[-1000:])

print("\n🎉 All Shorts processed!")