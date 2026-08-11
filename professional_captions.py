from pathlib import Path

INPUT_ASS = Path("captions_short_01.ass")
OUTPUT_ASS = Path("professional_captions.ass")


def ass_time_to_seconds(value):
    h, m, s = value.split(":")
    sec, cs = s.split(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(cs) / 100


def make_style():
    return """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Gaming,Arial,82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,6,3,5,50,50,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


lines = INPUT_ASS.read_text(encoding="utf-8").splitlines()

with open(OUTPUT_ASS, "w", encoding="utf-8") as f:

    f.write(make_style())

    for line in lines:

        if not line.startswith("Dialogue:"):
            continue

        parts = line.split(",", 9)

        if len(parts) < 10:
            continue

        start = parts[1]
        end = parts[2]
        text = parts[9].strip()

        # Highlight important gaming words
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

        for word in important_words:
            text = text.replace(
                word,
                r"{\c&H00FFFF&}" + word + r"{\c&HFFFFFF&}"
            )

        f.write(
            f"Dialogue: 0,{start},{end},Gaming,,0,0,0,,{text}\n"
        )

print("Professional gaming captions created!")
print(OUTPUT_ASS)