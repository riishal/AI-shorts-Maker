import json
import subprocess
from pathlib import Path

INPUT_DIR = Path("outputs/final_shorts")
OUTPUT_DIR = Path("outputs/final_shorts/hooks")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

with open("highlights.json", "r", encoding="utf-8") as f:
    data = json.load(f)

for item in data["highlights"]:
    rank = item["rank"]
    title = item["title"].upper()

    input_file = INPUT_DIR / f"short_{rank:02d}_final.mp4"
    output_file = OUTPUT_DIR / f"short_{rank:02d}_hook.mp4"

    # Make the hook shorter and more punchy
    hook = title

    # Escape characters for FFmpeg drawtext
    hook = hook.replace("'", r"\'")
    hook = hook.replace(":", r"\:")

    print(f"\n🎬 Short #{rank}")
    print(f"Hook: {hook}")

    command = [
        "ffmpeg",
        "-y",
        "-i", str(input_file),

        "-vf",
        (
            "drawtext="
            "fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
            f"text='{hook}':"
            "fontcolor=white:"
            "fontsize=42:"
            "borderw=4:"
            "bordercolor=black:"
            "x=(w-text_w)/2:"
            "y=120:"
            "enable='between(t,0,2.5)'"
        ),

        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "copy",

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
        print(result.stderr[-1500:])

print("\n🎉 ALL HOOKS CREATED!")