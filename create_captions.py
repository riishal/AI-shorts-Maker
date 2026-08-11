from faster_whisper import WhisperModel
from pathlib import Path

VIDEO = "uploads/uploadstest_with_audio.mp4"
OUTPUT = "captions.ass"

model = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8"
)

segments, info = model.transcribe(
    VIDEO,
    vad_filter=True,
    word_timestamps=True
)

def ass_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int((seconds - int(seconds)) * 100)

    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


with open(OUTPUT, "w", encoding="utf-8") as f:

    f.write("""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,70,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,5,40,40,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""")

    for segment in segments:
        for word in segment.words:

            start = ass_time(word.start)
            end = ass_time(word.end)

            text = word.word.strip()

            if not text:
                continue

            f.write(
                f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"
            )

print(f"Caption file created: {OUTPUT}")