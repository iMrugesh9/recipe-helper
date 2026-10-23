#!/usr/bin/env python3
"""
Recipe Helper Agent — Flask Web Server
=======================================
Run: python server.py
Then open: http://localhost:5000
"""

import os
import sys
import json
import tempfile
import subprocess
import re
import traceback
import base64
import threading
from pathlib import Path
from datetime import datetime

import cv2
import shutil
import socket

from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
from google import genai

from export_static import auto_sync_github, generate_static_site

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌  No GEMINI_API_KEY found in .env file.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

app = Flask(__name__, static_folder="static")

# ─────────────────────────────────────────────
# Helpers — Video Extraction
# ─────────────────────────────────────────────

def is_instagram_url(url: str) -> bool:
    return "instagram.com" in url.lower()


def parse_vtt_text(content: str) -> str:
    """Parse raw VTT or SRT subtitle content into clean, deduplicated sentences."""
    lines = content.split("\n")
    clean_lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:") or line.startswith("NOTE"):
            continue
        if re.match(r"^\d{2}:\d{2}", line) or re.match(r"^\d+$", line) or "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line and (not clean_lines or clean_lines[-1] != line):
            clean_lines.append(line)
    return " ".join(clean_lines)


def extract_captions_from_info(info: dict) -> str:
    """Directly fetch captions from signed URLs in yt-dlp metadata, bypassing 429 errors."""
    import urllib.request
    subs_sources = [info.get("subtitles") or {}, info.get("automatic_captions") or {}]

    preferred_langs = [
        "hi-orig", "en-orig", "en", "hi", "en-US", "en-GB", "en-IN", "hi-Latn"
    ]

    for source in subs_sources:
        if not source:
            continue
        ordered_keys = []
        for pl in preferred_langs:
            if pl in source and pl not in ordered_keys:
                ordered_keys.append(pl)
        for k in source:
            if k.endswith("-orig") and k not in ordered_keys:
                ordered_keys.append(k)
        for k in source:
            if k not in ordered_keys:
                ordered_keys.append(k)

        for lang in ordered_keys:
            formats = source.get(lang) or []
            vtt_fmts = [f for f in formats if f.get("ext") == "vtt"]
            target_fmt = vtt_fmts[0] if vtt_fmts else (formats[0] if formats else None)
            if not target_fmt or not target_fmt.get("url"):
                continue

            try:
                req = urllib.request.Request(
                    target_fmt["url"],
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                    cleaned = parse_vtt_text(raw)
                    if len(cleaned.strip()) > 25:
                        print(f"[captions] Successfully fetched {lang} captions ({len(cleaned)} chars)")
                        return cleaned
            except Exception as e:
                print(f"[captions warning] Failed for {lang}: {e}")

    return ""


def get_yt_dlp_bin() -> str:
    local_bin = Path(__file__).parent / ".venv" / "bin" / "yt-dlp"
    if local_bin.exists():
        return str(local_bin)
    system_bin = shutil.which("yt-dlp")
    if system_bin:
        return system_bin
    return "yt-dlp"


def fetch_video_info(url: str, tmpdir: str) -> dict:
    """Use yt-dlp to fetch video metadata, video file + subtitles/description."""
    yt_dlp_bin = get_yt_dlp_bin()

    # Step 1: ALWAYS fetch metadata via --dump-json (never fails on 429 subtitle errors or format issues)
    cmd_meta = [str(yt_dlp_bin), "--dump-json", "--no-warnings", url]
    res_meta = subprocess.run(cmd_meta, capture_output=True, text=True, timeout=25)
    info = {}
    if res_meta.returncode == 0 and res_meta.stdout.strip():
        try:
            info = json.loads(res_meta.stdout)
        except Exception:
            pass

    title       = info.get("title", "Untitled Recipe")
    description = info.get("description", "")

    # Thumbnail: prefer highest resolution
    thumbnail_url = ""
    thumbs = info.get("thumbnails", [])
    if thumbs:
        best = max(thumbs, key=lambda t: (t.get("width") or 0) * (t.get("height") or 0), default={})
        thumbnail_url = best.get("url", "")
    if not thumbnail_url:
        thumbnail_url = info.get("thumbnail", "")

    # Step 2: Try fetching subtitles directly from signed URLs in metadata (immune to 429)
    transcript = extract_captions_from_info(info)

    # Secondary fallback: yt-dlp subtitle download
    if not transcript:
        try:
            cmd_sub = [
                str(yt_dlp_bin),
                "--write-auto-subs",
                "--sub-langs", "hi-orig,hi,en-orig,en",
                "--skip-download",
                "--no-playlist",
                "--no-warnings",
                "-o", f"{tmpdir}/subs",
                url,
            ]
            subprocess.run(cmd_sub, capture_output=True, text=True, timeout=15)
            sub_files = list(Path(tmpdir).glob("subs*.vtt")) + list(Path(tmpdir).glob("subs*.srt"))
            if sub_files:
                transcript = parse_subtitle_file(sub_files[0])
        except Exception as e:
            print(f"[subtitles warning]: {e}")

    # Fallback to description if no subtitles (or combine if description has ingredients)
    if not transcript or len(transcript.strip()) < 30:
        if description:
            transcript = description
    elif description and len(description) > len(transcript):
        transcript = transcript + "\n\n" + description

    # Step 3: Download video stream for frame extraction and playback
    # Format selector works on both landscape and portrait (Shorts/Reels) without needing ffmpeg
    cmd_vid = [
        str(yt_dlp_bin),
        "--no-playlist",
        "--no-warnings",
        "-f", "best[ext=mp4]/bestvideo[height<=1280][ext=mp4]/bestvideo[width<=1280][ext=mp4]/best[height<=720]/best",
        "-o", f"{tmpdir}/video.%(ext)s",
        url,
    ]
    subprocess.run(cmd_vid, capture_output=True, text=True, timeout=40)

    # Find downloaded video file
    video_files = [
        str(p) for p in Path(tmpdir).glob("video.*")
        if p.suffix.lower() in [".mp4", ".mkv", ".webm", ".mov"]
    ]
    video_path = video_files[0] if video_files else None
    print(f"[video_file]: {video_path}")
    print(f"[info] Title: {title}")
    print(f"[info] Transcript length: {len(transcript)} chars")
    print(f"[info] Thumbnail: {thumbnail_url[:80]}")

    return {
        "title": title,
        "description": description,
        "transcript": transcript,
        "thumbnail_url": thumbnail_url,
        "video_path": video_path,
        "source_url": url,
    }


def parse_subtitle_file(path: Path) -> str:
    """Parse VTT or SRT subtitle file into plain text."""
    content = path.read_text(encoding="utf-8", errors="ignore")
    suffix = path.suffix.lower()

    if suffix == ".vtt":
        lines = content.split("\n")
        text_lines = []
        for line in lines:
            line = line.strip()
            if not line or line.startswith("WEBVTT") or line.startswith("NOTE"):
                continue
            if re.match(r"^\d{2}:\d{2}", line) or re.match(r"^\d+$", line):
                continue
            line = re.sub(r"<[^>]+>", "", line)
            if line:
                text_lines.append(line)
        deduped = []
        for line in text_lines:
            if not deduped or deduped[-1] != line:
                deduped.append(line)
        return " ".join(deduped)

    elif suffix == ".srt":
        content = re.sub(r"\d+\n\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}\n", "", content)
        content = re.sub(r"<[^>]+>", "", content)
        return " ".join(content.split())

    return content


def transcribe_audio(url: str, tmpdir: str, yt_dlp_bin) -> str:
    """Download audio and transcribe with Whisper."""
    cmd = [
        str(yt_dlp_bin), "-x", "--audio-format", "mp3",
        "--no-playlist", "-o", f"{tmpdir}/audio", url,
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    audio_files = list(Path(tmpdir).glob("*.mp3")) + list(Path(tmpdir).glob("*.m4a"))
    if audio_files:
        try:
            import whisper
            model = whisper.load_model("base")
            result = model.transcribe(str(audio_files[0]))
            return result["text"]
        except ImportError:
            pass
    return ""


def extract_visual_snippets(video_path: str, recipe_data: dict) -> dict:
    """Extract clear visual frames from video for steps and ingredients."""
    if not video_path or not os.path.exists(video_path):
        return recipe_data
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print("[cv2] Failed to open video:", video_path)
            return recipe_data

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0 or fps <= 0:
            cap.release()
            return recipe_data

        duration = total_frames / fps
        print(f"[cv2] Video duration: {duration:.1f}s, total frames: {total_frames}, fps: {fps:.1f}")

        def get_sharpest_frame_base64(target_sec, max_w=640, quality=75):
            center_frame = int(target_sec * fps)
            best_frame = None
            best_score = -1

            # Sample 5 neighboring frames to avoid motion blur
            offsets = [-4, -2, 0, 2, 4]
            for off in offsets:
                idx = max(0, min(total_frames - 1, center_frame + off))
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret or frame is None:
                    continue
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                score = cv2.Laplacian(gray, cv2.CV_64F).var()
                if score > best_score:
                    best_score = score
                    best_frame = frame

            if best_frame is None:
                return None

            h, w = best_frame.shape[:2]
            if w > max_w:
                new_h = int(h * (max_w / w))
                best_frame = cv2.resize(best_frame, (max_w, new_h), interpolation=cv2.INTER_AREA)

            _, buf = cv2.imencode('.jpg', best_frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
            b64 = base64.b64encode(buf).decode('utf-8')
            return f"data:image/jpeg;base64,{b64}"

        # 1. Process / Steps frames
        steps = recipe_data.get("steps", [])
        num_steps = len(steps)
        for i, step in enumerate(steps):
            pct = step.get("timestamp_percent")
            if pct is not None and isinstance(pct, (int, float)) and 5 <= pct <= 95:
                target_sec = (pct / 100.0) * duration
            else:
                if num_steps <= 1:
                    frac = 0.5
                else:
                    frac = 0.22 + (i / max(1, num_steps - 1)) * 0.63
                target_sec = frac * duration

            img_b64 = get_sharpest_frame_base64(target_sec, max_w=640, quality=78)
            if img_b64:
                step["image"] = img_b64
                step["timestamp_formatted"] = f"{int(target_sec // 60)}:{int(target_sec % 60):02d}"

        # 2. Ingredient snapshots gallery
        prep_points = [
            (0.08, "Ingredients Setup"),
            (0.18, "Chop & Prep"),
            (0.28, "Seasonings & Spices"),
            (0.38, "Bowl Mix"),
        ]
        prep_gallery = []
        for frac, label in prep_points:
            t_sec = frac * duration
            img_b64 = get_sharpest_frame_base64(t_sec, max_w=480, quality=75)
            if img_b64:
                prep_gallery.append({
                    "label": label,
                    "time": f"{int(t_sec // 60)}:{int(t_sec % 60):02d}",
                    "image": img_b64,
                })
        recipe_data["ingredient_snapshots"] = prep_gallery

        # 3. Individual ingredient thumbnails
        ingredients = recipe_data.get("ingredients", [])
        num_ings = len(ingredients)
        if num_ings > 0:
            for j, ing in enumerate(ingredients):
                ing_pct = ing.get("timestamp_percent")
                if ing_pct is not None and isinstance(ing_pct, (int, float)) and 5 <= ing_pct <= 95:
                    ing_sec = (ing_pct / 100.0) * duration
                else:
                    ing_frac = 0.06 + (j / max(1, num_ings - 1)) * 0.32
                    ing_sec = ing_frac * duration
                ing_thumb = get_sharpest_frame_base64(ing_sec, max_w=240, quality=70)
                if ing_thumb:
                    ing["image"] = ing_thumb

        cap.release()
        print(f"[cv2] Extracted visual snippets: {len(steps)} step images, {len(prep_gallery)} prep snapshots, {len(ingredients)} ingredient thumbnails")
    except Exception as e:
        print(f"[cv2 error]: {e}")

    return recipe_data


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
      "note": "optional preparation note, e.g. finely chopped (or empty string)",
      "timestamp_percent": 15
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
      "title": "Short step title",
      "instruction": "Detailed instruction for this step",
      "duration": "Time for this step (or empty string)",
      "timestamp_percent": 35
    }
  ],
  "tips": ["Tip 1", "Tip 2"],
  "tags": ["tag1", "tag2"]
}

Rules:
- Be thorough. Extract every ingredient with quantity if mentioned.
- If quantities are not mentioned, make reasonable estimates and note them.
- Tools include bowls, pans, knives, blenders, etc.
- Tips can come from the chef's commentary or best practices.
- For steps and ingredients, estimate timestamp_percent (0-100 approximate position in video). Ingredients appear early (5-35%), cooking steps throughout middle & end (25-90%).
- If any field cannot be determined, use null or an empty array.
- RETURN ONLY THE JSON OBJECT. No markdown, no explanation.

Video Title: __TITLE__

Transcript:
__TRANSCRIPT__
"""



# Models to try in order (fastest & most reliable first)
GEMINI_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
]


def extract_recipe_with_gemini(video_info: dict) -> dict:
    """Send transcript or uploaded video to Gemini and extract structured recipe data."""
    import time

    transcript = (video_info.get("transcript") or "").strip()
    video_path = video_info.get("video_path")
    file_ref = None

    if len(transcript) >= 25:
        prompt = (
            RECIPE_PROMPT
            .replace("__TITLE__", str(video_info.get("title", "Untitled Recipe")))
            .replace("__TRANSCRIPT__", transcript[:12000])
        )
        content_payload = prompt
    elif video_path and os.path.exists(video_path):
        print("[gemini] No transcript found. Uploading video directly for multimodal analysis...")
        try:
            file_ref = client.files.upload(file=video_path)
            print(f"[gemini] Video uploaded: {file_ref.name}")
        except Exception as ue:
            print(f"[gemini] File upload error: {ue}")
            file_ref = None

        prompt = (
            RECIPE_PROMPT
            .replace("__TITLE__", str(video_info.get("title", "Untitled Recipe")))
            .replace("__TRANSCRIPT__", "Observe the video visuals, listen to commentary, and read any on-screen text to identify all ingredients, quantities, tools, and step-by-step instructions.")
        )
        content_payload = [file_ref, prompt] if file_ref else prompt
    else:
        prompt = (
            RECIPE_PROMPT
            .replace("__TITLE__", str(video_info.get("title", "Untitled Recipe")))
            .replace("__TRANSCRIPT__", f"Video Title: {video_info.get('title')}. Estimate standard recipe details.")
        )
        content_payload = prompt

    last_error = None
    raw = None
    for model in GEMINI_MODELS:
        try:
            print(f"[gemini] Trying model: {model}")
            response = client.models.generate_content(
                model=model,
                contents=content_payload,
            )
            raw = response.text.strip()
            print(f"[gemini] Success with {model}, response len: {len(raw)}")
            break
        except Exception as e:
            print(f"[gemini] {model} failed: {str(e)[:120]}")
            last_error = e
            time.sleep(1)
            continue

    # Clean up uploaded file reference
    if file_ref:
        try:
            client.files.delete(name=file_ref.name)
        except Exception:
            pass

    if raw is None:
        raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")

    # Strip markdown fences
    cleaned = re.sub(r"^```[a-z]*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```$", "", cleaned).strip()

    # Find the JSON object even if there's surrounding text
    json_match = re.search(r'\{[\s\S]+\}', cleaned)
    if json_match:
        cleaned = json_match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"[json] Parse error: {e}\nRaw snippet: {cleaned[:300]}")
        return {
            "recipe_name": video_info["title"],
            "description": video_info.get("description", "")[:300],
            "ingredients": [],
            "tools": [],
            "steps": [],
            "tips": [],
            "tags": [],
            "difficulty": "Unknown",
            "cuisine_type": "",
            "servings": "",
            "prep_time": None,
            "cook_time": None,
        }


# ─────────────────────────────────────────────
# Recipe Persistence & Video Storage
# ─────────────────────────────────────────────
DATA_FILE = Path(__file__).parent / "data" / "recipes.json"
VIDEOS_DIR = Path(__file__).parent / "static" / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)

def load_recipes() -> list:
    """Load saved recipes from JSON storage."""
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[storage] Load error: {e}")
        return []


def trigger_github_sync_async():
    """Trigger background regeneration of docs/ and git push to GitHub Pages."""
    t = threading.Thread(target=auto_sync_github, daemon=True)
    t.start()


def save_recipe(recipe_entry: dict):
    """Save or update recipe in JSON storage."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    recipes = load_recipes()
    # Deduplicate by source_url (update existing or prepend new)
    recipes = [r for r in recipes if r.get("source_url") != recipe_entry.get("source_url")]
    recipes.insert(0, recipe_entry)
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(recipes, f, ensure_ascii=False, indent=2)
        print(f"[storage] Saved recipe: {recipe_entry.get('recipe', {}).get('recipe_name')}")
        trigger_github_sync_async()
    except Exception as e:
        print(f"[storage] Save error: {e}")


def update_recipe_difficulty(recipe_id: str, new_difficulty: str) -> bool:
    """Update difficulty rating for a saved recipe."""
    return update_recipe_fields(recipe_id, {"difficulty": new_difficulty})


def update_recipe_fields(recipe_id: str, updates: dict) -> bool:
    """Update fields like difficulty, recipe_type, cuisine_type for a saved recipe."""
    recipes = load_recipes()
    updated = False
    for r in recipes:
        if r.get("id") == recipe_id:
            if "recipe" in r:
                for k, v in updates.items():
                    r["recipe"][k] = v
                updated = True
            break
    if updated:
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(recipes, f, ensure_ascii=False, indent=2)
            print(f"[storage] Updated recipe {recipe_id} fields: {updates}")
            trigger_github_sync_async()
            return True
        except Exception as e:
            print(f"[storage] Update fields error: {e}")
    return False


def delete_recipe(recipe_id: str) -> bool:
    """Delete recipe by ID and remove video stream."""
    recipes = load_recipes()
    new_recipes = [r for r in recipes if r.get("id") != recipe_id]
    if len(new_recipes) != len(recipes):
        try:
            for ext in [".mp4", ".webm", ".mkv"]:
                vpath = VIDEOS_DIR / f"{recipe_id}{ext}"
                if vpath.exists():
                    try:
                        vpath.unlink()
                    except Exception:
                        pass
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(new_recipes, f, ensure_ascii=False, indent=2)
            print(f"[storage] Deleted recipe: {recipe_id}")
            trigger_github_sync_async()
            return True
        except Exception as e:
            print(f"[storage] Delete error: {e}")
    return False


# ─────────────────────────────────────────────
# Flask Routes
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/sync", methods=["GET", "POST"])
def sync_github():
    """Manual trigger to regenerate docs/ and push to GitHub."""
    res = auto_sync_github()
    return jsonify(res)


@app.route("/api/recipes", methods=["GET"])
def get_recipes():
    """Return all saved recipes."""
    recipes = load_recipes()
    return jsonify({"recipes": recipes, "count": len(recipes)})


@app.route("/api/recipes/<recipe_id>", methods=["PATCH"])
def update_recipe(recipe_id):
    """Update recipe properties such as difficulty or recipe_type."""
    data = request.get_json() or {}
    updates = {}
    if "difficulty" in data and data["difficulty"]:
        norm_diff = data["difficulty"].strip().capitalize()
        if norm_diff not in ["Easy", "Medium", "Hard"]:
            norm_diff = data["difficulty"].strip()
        updates["difficulty"] = norm_diff
    if "recipe_type" in data and data["recipe_type"]:
        updates["recipe_type"] = data["recipe_type"].strip()
    if "meal_type" in data and data["meal_type"]:
        updates["recipe_type"] = data["meal_type"].strip()
    if "cuisine_type" in data and data["cuisine_type"]:
        updates["cuisine_type"] = data["cuisine_type"].strip()

    if not updates:
        return jsonify({"error": "No valid fields provided to update"}), 400

    success = update_recipe_fields(recipe_id, updates)
    return jsonify({"success": success, "updates": updates})


@app.route("/api/recipes/<recipe_id>/difficulty", methods=["POST"])
def set_recipe_difficulty(recipe_id):
    """Update recipe difficulty via POST."""
    data = request.get_json() or {}
    new_difficulty = data.get("difficulty", "")
    if not new_difficulty:
        return jsonify({"error": "No difficulty provided"}), 400
    norm_diff = new_difficulty.strip().capitalize()
    success = update_recipe_difficulty(recipe_id, norm_diff)
    return jsonify({"success": success, "difficulty": norm_diff})


@app.route("/api/recipes/<recipe_id>", methods=["DELETE"])
def remove_recipe(recipe_id):
    """Delete a recipe by ID."""
    success = delete_recipe(recipe_id)
    return jsonify({"success": success})


@app.route("/api/extract", methods=["POST"])
def extract():
    data = request.get_json()
    url = (data or {}).get("url", "").strip()

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    # Basic URL validation — accept YouTube and all Instagram post/reel formats
    url_lower = url.lower()
    is_youtube  = "youtube.com/shorts" in url_lower or "youtu.be" in url_lower or "youtube.com/watch" in url_lower
    is_instagram = "instagram.com" in url_lower  # covers /reel/, /p/, /tv/
    if not is_youtube and not is_instagram:
        return jsonify({"error": "Please enter a YouTube Shorts or Instagram Reel/Post URL"}), 400

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_info = fetch_video_info(url, tmpdir)

            if not video_info.get("transcript") and not video_info.get("video_path"):
                return jsonify({
                    "error": "Could not extract video content. Please check the URL and try again."
                }), 422

            recipe_data = extract_recipe_with_gemini(video_info)

            # Extract visual frames from downloaded video for steps and ingredients
            if video_info.get("video_path"):
                recipe_data = extract_visual_snippets(video_info["video_path"], recipe_data)

            recipe_id = f"rec_{int(datetime.now().timestamp())}"
            video_url = None

            # Copy video file to static/videos for embedded player
            raw_video_path = video_info.get("video_path")
            if raw_video_path and os.path.exists(raw_video_path):
                try:
                    ext = Path(raw_video_path).suffix or ".mp4"
                    saved_video_filename = f"{recipe_id}{ext}"
                    dest_path = VIDEOS_DIR / saved_video_filename
                    shutil.copy2(raw_video_path, dest_path)
                    video_url = f"/static/videos/{saved_video_filename}"
                    print(f"[storage] Persisted video to: {video_url}")
                except Exception as ve:
                    print(f"[storage] Video persist warning: {ve}")

            recipe_entry = {
                "id": recipe_id,
                "recipe": recipe_data,
                "thumbnail_url": video_info.get("thumbnail_url", ""),
                "source_url": url,
                "video_url": video_url,
                "generated_at": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            }

            # Persist recipe
            save_recipe(recipe_entry)

            return jsonify(recipe_entry)

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Video download timed out. Please try again."}), 504
    except Exception as e:
        tb = traceback.format_exc()
        print("[ERROR]\n" + tb)
        return jsonify({"error": f"Something went wrong: {str(e)}"}), 500


def get_local_ip() -> str:
    """Detect LAN IP address for mobile / local network access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    local_ip = get_local_ip()
    print("\n🍽️  Recipe Helper Agent")
    print("━" * 40)
    print(f"🌐  Local:   http://localhost:{port}")
    print(f"📱  Mobile:  http://{local_ip}:{port}")
    print("━" * 40)
    try:
        generate_static_site()
        print("📄  Static GitHub Pages site compiled in docs/")
    except Exception as e:
        print(f"⚠️  Static site generation warning: {e}")
    print("━" * 40 + "\n")
    app.run(debug=False, host="0.0.0.0", port=port)
