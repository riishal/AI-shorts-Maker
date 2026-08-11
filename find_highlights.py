import json
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=api_key)

with open("transcript.txt", "r", encoding="utf-8") as f:
    transcript = f.read()

prompt = f"""
You are an expert gaming Shorts editor.

Analyze this transcript from a gaming video.

Find the 10 BEST moments that could work as YouTube Shorts.

Look for:
- funny moments
- surprising moments
- emotional moments
- reactions
- suspense
- unexpected events
- arguments or funny conversations
- strong hooks
- moments that make viewers want to keep watching

Rules:
1. Use ONLY timestamps that actually exist in the transcript.
2. Each clip should normally be 20–60 seconds.
3. The clip must make sense by itself.
4. Prefer moments with a strong hook near the beginning.
5. Avoid repetitive or boring sections.
6. Rank the clips from best to worst.
7. Return ONLY valid JSON.

Return exactly this structure:

{{
  "highlights": [
    {{
      "rank": 1,
      "start": 145.17,
      "end": 168.61,
      "score": 95,
      "title": "They Thought They Found a Player",
      "reason": "The suspense builds before the reveal that it is actually a skeleton."
    }}
  ]
}}

Transcript:

{transcript}
"""

response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents=prompt
)

text = response.text.strip()

# Remove markdown code fences if Gemini adds them
if text.startswith("```"):
    lines = text.splitlines()

    if lines[0].startswith("```"):
        lines = lines[1:]

    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    text = "\n".join(lines)

highlights = json.loads(text)

with open("highlights.json", "w", encoding="utf-8") as f:
    json.dump(highlights, f, indent=2, ensure_ascii=False)

print("\n--- BEST SHORTS ---\n")

for item in highlights["highlights"]:
    print(
        f"#{item['rank']} | "
        f"{item['start']} - {item['end']} | "
        f"Score: {item['score']} | "
        f"{item['title']}"
    )

print("\nSaved to highlights.json")