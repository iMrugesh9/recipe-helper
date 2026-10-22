#!/usr/bin/env python3
"""
Recipe Helper Agent
===================
Extracts recipe info from YouTube Shorts or Instagram Reels
and generates a beautiful standalone HTML page.

Usage:
    python recipe_agent.py <video_url>
    python recipe_agent.py https://www.youtube.com/shorts/abc123
    python recipe_agent.py https://www.instagram.com/reel/abc123/
"""

import os
import sys
import json
import tempfile
import subprocess
import re
import webbrowser
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from google import genai
from google.genai import types
from jinja2 import Environment, FileSystemLoader, StrictUndefined

# ─────────────────────────────────────────────
# Load environment
# ─────────────────────────────────────────────
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌  No GEMINI_API_KEY found in .env file.")
    print("    Create a .env file with: GEMINI_API_KEY=your_key_here")
    print("    Get your key at: https://aistudio.google.com/app/apikey")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def detect_platform(url: str) -> str:
    """Detect whether URL is YouTube or Instagram."""
    url = url.lower()
    if "youtube.com/shorts" in url or "youtu.be" in url or "youtube.com/watch" in url:
        return "youtube"
    elif "instagram.com" in url:
        return "instagram"
    else:
        return "unknown"


def fetch_video_info(url: str, tmpdir: str) -> dict:
    """
    Use yt-dlp to fetch video metadata and subtitles/transcript.
    Returns a dict with title, description, transcript, thumbnail_url.
    """
    print(f"📥  Fetching video info from: {url}")

    # Build yt-dlp command — get metadata + subtitles
    cmd = [
        "yt-dlp",
        "--write-auto-subs",
        "--sub-langs", "en.*",
        "--skip-download",
        "--write-info-json",
        "--write-thumbnail",
        "--convert-thumbnails", "jpg",
        "-o", f"{tmpdir}/video",
        url,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        # If subtitles fail, try without subtitle flags
        print("⚠️   Subtitle fetch failed, trying audio transcription fallback...")
        return fetch_via_audio(url, tmpdir)

    # Load metadata JSON
    info_json_paths = list(Path(tmpdir).glob("video.info.json"))
    if not info_json_paths:
        info_json_paths = list(Path(tmpdir).glob("*.info.json"))

    info = {}
    if info_json_paths:
        with open(info_json_paths[0], "r", encoding="utf-8") as f:
            info = json.load(f)

    title = info.get("title", "Untitled Recipe")
    description = info.get("description", "")
    thumbnail_url = info.get("thumbnail", "")

    # Try to find subtitle/transcript file
    transcript = ""
    sub_files = list(Path(tmpdir).glob("*.vtt")) + \
                list(Path(tmpdir).glob("*.srt")) + \
                list(Path(tmpdir).glob("*.json3"))

    if sub_files:
        transcript = parse_subtitle_file(sub_files[0])
        print(f"✅  Found subtitles: {sub_files[0].name}")
    else:
        print("⚠️   No subtitles found — falling back to audio transcription...")
        audio_info = fetch_via_audio(url, tmpdir)
        transcript = audio_info.get("transcript", "")

    if not transcript and description:
        print("ℹ️   Using video description as fallback context.")
        transcript = description

    return {
        "title": title,
        "description": description,
        "transcript": transcript,
        "thumbnail_url": thumbnail_url,
        "source_url": url,
    }


def parse_subtitle_file(path: Path) -> str:
    """Parse VTT or SRT subtitle file into plain text."""
    content = path.read_text(encoding="utf-8", errors="ignore")
    suffix = path.suffix.lower()

    if suffix == ".vtt":
        # Remove WEBVTT header and timestamp lines
        lines = content.split("\n")
        text_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("WEBVTT") or line.startswith("NOTE"):
                continue
            if re.match(r"^\d{2}:\d{2}", line) or re.match(r"^\d+$", line):
                continue
            # Remove HTML tags
            line = re.sub(r"<[^>]+>", "", line)
            if line:
                text_lines.append(line)
        # Remove duplicate consecutive lines
        deduped = []
        for line in text_lines:
            if not deduped or deduped[-1] != line:
                deduped.append(line)
        return " ".join(deduped)

    elif suffix == ".srt":
        # Remove SRT timestamps and indices
        content = re.sub(r"\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n", "", content)
        content = re.sub(r"<[^>]+>", "", content)
        return " ".join(content.split())

    return content


def fetch_via_audio(url: str, tmpdir: str) -> dict:
    """
    Download audio and transcribe with Whisper as fallback.
    """
    print("🎙️   Downloading audio for Whisper transcription...")

    cmd = [
        "yt-dlp",
        "-x", "--audio-format", "mp3",
        "--write-info-json",
        "--write-thumbnail",
        "--convert-thumbnails", "jpg",
        "-o", f"{tmpdir}/audio",
        url,
    ]
    subprocess.run(cmd, capture_output=True, text=True)

    audio_files = list(Path(tmpdir).glob("*.mp3")) + list(Path(tmpdir).glob("*.m4a"))
    info_json_paths = list(Path(tmpdir).glob("*.info.json"))

    info = {}
    if info_json_paths:
        with open(info_json_paths[0], "r", encoding="utf-8") as f:
            info = json.load(f)

    title = info.get("title", "Untitled Recipe")
    description = info.get("description", "")
    thumbnail_url = info.get("thumbnail", "")
    transcript = ""

    if audio_files:
        try:
            import whisper
            print("🔊  Transcribing audio with Whisper (this may take a moment)...")
            model = whisper.load_model("base")
            result = model.transcribe(str(audio_files[0]))
            transcript = result["text"]
            print("✅  Transcription complete.")
        except ImportError:
            print("⚠️   Whisper not installed. Using description as fallback.")
            transcript = description

    return {
        "title": title,
        "description": description,
        "transcript": transcript,
        "thumbnail_url": thumbnail_url,
        "source_url": url,
    }


# ─────────────────────────────────────────────
# AI Extraction
# ─────────────────────────────────────────────

RECIPE_PROMPT = """
You are a professional recipe analyst. I will give you the transcript and title of a cooking video.
Extract ALL recipe information and return it as a valid JSON object with EXACTLY this structure:

{
  "recipe_name": "Name of the dish",
  "cuisine_type": "e.g. Italian, Indian, Mexican, etc.",
  "servings": "e.g. 2-4 servings",
  "prep_time": "e.g. 15 minutes (or null if not mentioned)",
  "cook_time": "e.g. 30 minutes (or null if not mentioned)",
  "difficulty": "Easy | Medium | Hard",
  "description": "A 2-3 sentence description of this dish",
  "ingredients": [
    {
      "name": "ingredient name",
      "quantity": "amount + unit, e.g. 2 cups",
      "note": "optional preparation note, e.g. finely chopped (or empty string)"
    }
  ],
  "tools": [
    {
      "name": "tool or equipment name",
      "purpose": "brief description of why it is needed"
    }
  ],
  "steps": [
    {
      "step_number": 1,
      "title": "Short step title, e.g. Marinate the chicken",
      "instruction": "Detailed instruction for this step",
      "duration": "Time for this step, e.g. 10 minutes (or empty string if not applicable)"
    }
  ],
  "tips": [
    "Tip 1 as a string",
    "Tip 2 as a string"
  ],
  "tags": ["tag1", "tag2"]
}

Rules:
- Be thorough. Extract every ingredient with quantity if mentioned.
- If quantities are not mentioned, make reasonable estimates and note them.
- Tools include bowls, pans, knives, blenders, etc.
- Tips can come from the chef's commentary or best practices.
- If any field cannot be determined, use null or an empty array.
- RETURN ONLY THE JSON OBJECT. No markdown, no explanation, just the JSON.

Video Title: __TITLE__

Transcript:
__TRANSCRIPT__
"""

GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
]


def extract_recipe_with_gemini(video_info: dict) -> dict:
    """Send transcript to Gemini and extract structured recipe data."""
    print("🤖  Sending to Gemini for recipe extraction...")

    prompt = (
        RECIPE_PROMPT
        .replace("__TITLE__", str(video_info.get("title", "Untitled Recipe")))
        .replace("__TRANSCRIPT__", str(video_info.get("transcript", ""))[:12000])
    )

    raw = None
    for model in GEMINI_MODELS:
        try:
            print(f"    Trying model: {model}...")
            response = client.models.generate_content(
                model=model,
                contents=prompt,
            )
            raw = response.text.strip()
            print(f"    ✅ Success with {model}")
            break
        except Exception as e:
            print(f"    ⚠️  {model} failed: {e}")
            continue

    if raw is None:
        raise RuntimeError("All Gemini models failed.")


    # Clean up response (remove markdown code fences if present)
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        recipe_data = json.loads(raw)
        print("✅  Recipe extracted successfully.")
        return recipe_data
    except json.JSONDecodeError as e:
        print(f"⚠️   JSON parse error: {e}")
        print("    Raw response snippet:", raw[:200])
        # Return a minimal structure
        return {
            "recipe_name": video_info["title"],
            "description": video_info["transcript"][:300],
            "ingredients": [],
            "tools": [],
            "steps": [],
            "tips": [],
            "tags": [],
            "difficulty": "Unknown",
        }


# ─────────────────────────────────────────────
# HTML Generation
# ─────────────────────────────────────────────

def generate_html(recipe_data: dict, video_info: dict) -> str:
    """Render the HTML template with extracted recipe data."""
    template_dir = Path(__file__).parent / "template"
    env = Environment(loader=FileSystemLoader(str(template_dir)))
    template = env.get_template("recipe.html.jinja")

    return template.render(
        recipe=recipe_data,
        source_url=video_info["source_url"],
        thumbnail_url=video_info.get("thumbnail_url", ""),
        generated_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
    )


def save_html(html_content: str, recipe_name: str) -> Path:
    """Save HTML to output directory."""
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    # Sanitize filename
    safe_name = re.sub(r"[^\w\s-]", "", recipe_name).strip()
    safe_name = re.sub(r"[\s]+", "_", safe_name)[:60]
    filename = f"recipe_{safe_name}.html"

    output_path = output_dir / filename
    output_path.write_text(html_content, encoding="utf-8")
    return output_path


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python recipe_agent.py <video_url>")
        print()
        print("Examples:")
        print("  python recipe_agent.py https://www.youtube.com/shorts/abc123")
        print("  python recipe_agent.py https://www.instagram.com/reel/abc123/")
        sys.exit(1)

    url = sys.argv[1].strip()
    platform = detect_platform(url)

    if platform == "unknown":
        print("⚠️   Unrecognized URL. Attempting anyway...")
    else:
        print(f"🎬  Detected platform: {platform.upper()}")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Step 1: Fetch video info
        video_info = fetch_video_info(url, tmpdir)

        if not video_info["transcript"]:
            print("❌  Could not extract any text from the video.")
            print("    Try a video with captions, or ensure ffmpeg is installed for audio transcription.")
            sys.exit(1)

        print(f"📝  Video: {video_info['title']}")
        print(f"📜  Transcript length: {len(video_info['transcript'])} characters")

        # Step 2: Extract recipe with Gemini
        recipe_data = extract_recipe_with_gemini(video_info)

        # Step 3: Generate HTML
        print("🎨  Generating recipe page...")
        html_content = generate_html(recipe_data, video_info)

        # Step 4: Save
        output_path = save_html(html_content, recipe_data.get("recipe_name", "recipe"))
        print(f"\n✅  Recipe page saved to: {output_path}")

        # Step 5: Open in browser
        webbrowser.open(f"file://{output_path.resolve()}")
        print("🌐  Opening in your browser...")


if __name__ == "__main__":
    main()
