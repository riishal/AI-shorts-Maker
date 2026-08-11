from faster_whisper import WhisperModel

model = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8"
)

segments, info = model.transcribe(
    "uploads/uploadstest_with_audio.mp4",
    vad_filter=True,
    word_timestamps=True
)

print("\n--- TRANSCRIPT ---\n")

with open("transcript.txt", "w", encoding="utf-8") as f:
   for segment in segments:
    print(f"\n[{segment.start:.2f} - {segment.end:.2f}]")

    for word in segment.words:
        print(
            f"{word.start:.2f} - {word.end:.2f}: "
            f"{word.word}"
        )