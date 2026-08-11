import subprocess

INPUT = "outputs/final_shorts/short_01_final.mp4"
OUTPUT = "outputs/final_shorts/short_01_hook.mp4"

HOOK = "THEY THOUGHT IT WAS A PLAYER..."

command = [
    "ffmpeg",
    "-y",
    "-i", INPUT,

    "-vf",
    (
        "drawtext="
        "fontfile='C\\:/Windows/Fonts/arialbd.ttf':"
        f"text='{HOOK}':"
        "fontcolor=white:"
        "fontsize=42:"
        "borderw=5:"
        "bordercolor=black:"
        "x=(w-text_w)/2:"
        "y=120:"
        "enable='between(t,0,2.5)'"
    ),

    "-c:v", "libx264",
    "-preset", "veryfast",
    "-c:a", "copy",

    OUTPUT
]

result = subprocess.run(
    command,
    capture_output=True,
    text=True
)

if result.returncode == 0:
    print("✅ Hook added successfully!")
    print(OUTPUT)
else:
    print("❌ FFmpeg failed")
    print(result.stderr[-2000:])