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


def get_cookie_args() -> list:
    """Return yt-dlp cookie arguments if configured in environment or project folder."""
    # Check for direct cookies.txt path in env
    cookies_path = os.getenv("INSTAGRAM_COOKIES_PATH") or os.getenv("COOKIES_PATH")
    if cookies_path and os.path.exists(cookies_path):
        return ["--cookies", cookies_path]

    # Check default cookies.txt in project root
    default_cookie_file = Path(__file__).parent / "cookies.txt"
    if default_cookie_file.exists():
        return ["--cookies", str(default_cookie_file)]

    # Check browser cookies
    browser = os.getenv("INSTAGRAM_BROWSER") or os.getenv("BROWSER_COOKIES")
    if browser:
        return ["--cookies-from-browser", browser]

    return []


def get_yt_dlp_bin() -> str:
    local_bin = Path(__file__).parent / ".venv" / "bin" / "yt-dlp"
    if local_bin.exists():
        return str(local_bin)
    system_bin = shutil.which("yt-dlp")
    if system_bin:
        return system_bin
    return "yt-dlp"


def fetch_video_info(url: str, tmpdir: str, custom_notes: str = "") -> dict:
    """Use yt-dlp to fetch video metadata, video file, subtitles, caption, and comments."""
    yt_dlp_bin = get_yt_dlp_bin()
    cookie_args = get_cookie_args()

    # Step 1: ALWAYS fetch metadata via --dump-json with comments (never fails on 429 subtitle errors or format issues)
    cmd_meta = [str(yt_dlp_bin), "--dump-json", "--no-warnings", "--write-comments"] + cookie_args + [url]
    res_meta = subprocess.run(cmd_meta, capture_output=True, text=True, timeout=30)
    info = {}
    if res_meta.returncode == 0 and res_meta.stdout.strip():
        # Handle cases where warnings might appear before json
        for line in res_meta.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    info = json.loads(line)
                    break
                except Exception:
                    pass

    title       = info.get("title", "Untitled Recipe")
    description = (info.get("description") or "").strip()
    uploader    = (info.get("uploader") or "").strip()
    channel     = (info.get("channel") or "").strip()
    comments_raw = info.get("comments") or []

    # Parse and structure comments
    uploader_comments = []
    recipe_comments = []
    other_comments = []

    recipe_keywords = [
        "recipe", "ingredient", "ingredients", "measure", "tsp", "tbsp", "tablespoon", "teaspoon",
        "cup", "cups", "gram", "grams", "gms", "g ", "kg", "pinch", "boiled", "chopped", "crumbled",
        "method", "step", "instruction", "bake", "air fry", "fry", "servings", "sauce"
    ]

    uploader_lower = uploader.lower().replace(" ", "")
    channel_lower = channel.lower().replace(" ", "")

    for c in comments_raw:
        if not isinstance(c, dict):
            continue
        author = (c.get("author") or "").strip()
        author_lower = author.lower().replace(" ", "")
        text = (c.get("text") or "").strip()
        if not text:
            continue

        is_uploader = False
        if channel_lower and (channel_lower in author_lower or author_lower in channel_lower):
            is_uploader = True
        elif uploader_lower and (uploader_lower in author_lower or author_lower in uploader_lower):
            is_uploader = True
        elif c.get("is_favorited") or c.get("is_pinned"):
            is_uploader = True

        entry = f"@{author}: {text}"
        if is_uploader:
            uploader_comments.append(entry)
        elif any(k in text.lower() for k in recipe_keywords):
            recipe_comments.append(entry)
        else:
            other_comments.append(entry)

    formatted_comments_list = []
    if uploader_comments:
        formatted_comments_list.append("=== UPLOADER / PINNED COMMENTS ===")
        formatted_comments_list.extend(uploader_comments)
    if recipe_comments:
        formatted_comments_list.append("=== COMMENTS MENTIONING RECIPES / INGREDIENTS ===")
        formatted_comments_list.extend(recipe_comments[:15])
    if other_comments and not uploader_comments and not recipe_comments:
        formatted_comments_list.append("=== TOP COMMENTS ===")
        formatted_comments_list.extend(other_comments[:10])

    if custom_notes and custom_notes.strip():
        formatted_comments_list.append("=== USER-PROVIDED RECIPE NOTES / PINNED COMMENT ===")
        formatted_comments_list.append(custom_notes.strip())

    comments_text = "\n".join(formatted_comments_list)

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
    subprocess.run(cmd_vid, capture_output=True, text=True, timeout=45)

    # Find downloaded video file
    video_files = [
        str(p) for p in Path(tmpdir).glob("video.*")
        if p.suffix.lower() in [".mp4", ".mkv", ".webm", ".mov"]
    ]
    video_path = video_files[0] if video_files else None
    print(f"[video_file]: {video_path}")
    print(f"[info] Title: {title}")
    print(f"[info] Creator: {uploader} ({channel})")
    print(f"[info] Caption length: {len(description)} chars")
    print(f"[info] Comments formatted: {len(comments_text)} chars ({len(comments_raw)} raw comments)")
    print(f"[info] Transcript length: {len(transcript)} chars")
    print(f"[info] Thumbnail: {thumbnail_url[:80]}")

    return {
        "title": title,
        "uploader": uploader,
        "channel": channel,
        "caption": description,
        "description": description,
        "comments_text": comments_text,
        "comments_raw": comments_raw,
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
You are a professional recipe analyst and culinary intelligence agent.
I will give you comprehensive information from a cooking video (YouTube Short or Instagram Reel), including the video title, creator/channel, post caption, comments (especially pinned or creator comments), and audio/subtitles transcript.

Extract ALL recipe information and return it as a valid JSON object with EXACTLY this structure:

{
  "recipe_name": "Name of the dish",
  "cuisine_type": "e.g. Italian, Indian, Mexican, Fusion, etc.",
  "servings": "e.g. 2 servings (or 2-4 servings)",
  "prep_time": "e.g. 10 minutes (or null if not mentioned)",
  "cook_time": "e.g. 15 minutes (or null if not mentioned)",
  "difficulty": "Easy | Medium | Hard",
  "description": "A 2-3 sentence description of this dish highlighting flavors, texture, and key characteristics",
  "ingredients": [
    {
      "name": "ingredient name",
      "quantity": "amount + unit, e.g. 2 cups, 100g, 1 tsp",
      "note": "optional preparation note, e.g. finely chopped, crumbled, boiled (or empty string)",
      "timestamp_percent": 15
    }
  ],
  "tools": [
    {
      "name": "tool or equipment name, e.g. Non-stick Pan, Air Fryer, Blender, Knife",
      "purpose": "brief description of why it is needed"
    }
  ],
  "steps": [
    {
      "step_number": 1,
      "title": "Short step title",
      "instruction": "Detailed instruction for this step including visual cues and techniques",
      "duration": "Time for this step (or empty string)",
      "timestamp_percent": 35
    }
  ],
  "tips": ["Tip 1", "Tip 2"],
  "tags": ["tag1", "tag2"]
}

Critical Extraction Rules:
1. CAPTION & COMMENTS PRIORITY:
   - On Instagram and YouTube Shorts, creators frequently put the full ingredient list with exact quantities (grams, tablespoons, teaspoons, cups, slices) and step-by-step notes in the **Post Caption** or in the **Comments** (specifically comments made by the uploader or pinned comments).
   - Thoroughly examine the **Post Caption** and all **Comments** first for explicit ingredient names, exact measurements, sauces, seasonings, and instructions.
   - Do NOT invent or estimate generic ingredients if specific ingredients or measurements are already stated in the caption or comments.
2. VISUAL CROSS-REFERENCING:
   - If video visuals are provided, cross-reference them with the caption/comments to verify steps, tools used (e.g., pan, air fryer, blender), and visual timestamps.
   - For steps and ingredients, estimate timestamp_percent (0-100 approximate position in video). Ingredients appear early (5-35%), cooking steps throughout middle & end (25-90%).
3. APPLIANCES & COOKING METHODS:
   - If the recipe uses an Air Fryer, specify air fryer temperature (e.g. 180°C–200°C) and time. If it uses a pressure cooker, skillet, or oven, specify exact settings.
4. COMPLETENESS:
   - If any field cannot be determined, use null or an empty array.
   - RETURN ONLY THE JSON OBJECT. No markdown code fences, no explanatory text outside the JSON.

Cooking Video & Post Information:
__CONTEXT__
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
    """Send multimodal video visuals, post caption, comments, and transcript to Gemini to extract structured recipe data."""
    import time

    title = str(video_info.get("title", "Untitled Recipe"))
    uploader = str(video_info.get("uploader", "")).strip()
    channel = str(video_info.get("channel", "")).strip()
    caption = (video_info.get("caption") or video_info.get("description") or "").strip()
    comments_text = (video_info.get("comments_text") or "").strip()
    transcript = (video_info.get("transcript") or "").strip()
    video_path = video_info.get("video_path")

    # Build comprehensive context payload
    context_sections = []
    context_sections.append(f"Video Title: {title}")
    if uploader or channel:
        context_sections.append(f"Creator / Channel: {uploader} ({channel})")

    if caption:
        context_sections.append(f"\n--- POST CAPTION / DESCRIPTION ---\n{caption}")

    if comments_text:
        context_sections.append(f"\n--- COMMENTS & PINNED RECIPE DETAILS ---\n{comments_text}")

    if transcript and transcript != caption:
        context_sections.append(f"\n--- AUDIO / SUBTITLE TRANSCRIPT ---\n{transcript[:6000]}")

    full_context_text = "\n".join(context_sections)

    prompt = (
        RECIPE_PROMPT
        .replace("__CONTEXT__", full_context_text[:15000])
    )

    file_ref = None
    if video_path and os.path.exists(video_path):
        print(f"[gemini] Uploading video for multimodal analysis: {video_path}")
        try:
            file_ref = client.files.upload(file=video_path)
            # Wait for file processing to complete
            for _ in range(30):
                file_status = client.files.get(name=file_ref.name)
                if file_status.state.name == "ACTIVE":
                    break
                elif file_status.state.name == "FAILED":
                    print("[gemini] Video processing failed on Gemini server.")
                    file_ref = None
                    break
                time.sleep(1)
            if file_ref:
                print(f"[gemini] Video uploaded and active: {file_ref.name}")
        except Exception as ue:
            print(f"[gemini] File upload error: {ue}")
            file_ref = None

    if file_ref:
        content_payload = [file_ref, prompt]
    else:
        content_payload = prompt

    last_error = None
    raw = None
    try:
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
    finally:
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
            "description": caption[:300] if caption else transcript[:300],
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


def classify_recipe(r: dict) -> str:
    """Infer recipe category type based on title, description, tags, and ingredients."""
    if r.get("recipe_type"):
        return r.get("recipe_type")
    if r.get("meal_type") and r.get("meal_type") in ["Main Course", "High Protein", "Snack", "Breakfast", "Dessert", "Salad", "Drink"]:
        return r.get("meal_type")
    name = (r.get("recipe_name") or "").lower()
    desc = (r.get("description") or "").lower()
    tags = " ".join(r.get("tags") or []).lower()
    ings = " ".join([i.get("name", "") if isinstance(i, dict) else str(i) for i in r.get("ingredients") or []]).lower()
    text = f"{name} {desc} {tags} {ings}"
    if any(k in text for k in ["shake", "smoothie", "drink", "juice", "tea", "coffee", "cooler", "mocktail", "beverage", "lassi"]):
        return "Drink"
    if any(k in text for k in ["cake", "cookie", "sweet", "halwa", "dessert", "pudding", "ice cream", "kheer", "brownie", "mousse", "chocolate", "jalebi", "pastry"]):
        return "Dessert"
    if any(k in text for k in ["salad", "raita", "dressing", "slaw", "kosambari"]):
        return "Salad"
    if any(k in text for k in ["high protein", "highprotein", "whey", "soya rice", "moong dal pizza", "paneer roll", "soya chilli"]):
        return "High Protein"
    if any(k in text for k in ["paratha", "poha", "upma", "chilla", "oats", "pancake", "toast", "sandwich", "dosa", "idli", "breakfast"]):
        return "Breakfast"
    if any(k in text for k in ["cracker", "crispy", "snack", "tikki", "roll", "chaat", "samosa", "pakora", "chips", "dip", "finger", "fries", "bites", "manchurian", "spread", "bhel"]):
        return "Snack"
    return "Main Course"


def save_recipe(recipe_entry: dict):
    """Save or update recipe in JSON storage."""
    if recipe_entry.get("recipe") and not recipe_entry["recipe"].get("recipe_type"):
        recipe_entry["recipe"]["recipe_type"] = classify_recipe(recipe_entry["recipe"])
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
# Grocery Checklist Persistence & Operations
# ─────────────────────────────────────────────
GROCERY_FILE = Path(__file__).parent / "data" / "grocery.json"

def load_grocery_list() -> dict:
    """Load grocery checklist from JSON storage."""
    if not GROCERY_FILE.exists():
        return {"items": [], "updated_at": None}
    try:
        with open(GROCERY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return {"items": data, "updated_at": None}
            if not isinstance(data, dict):
                return {"items": [], "updated_at": None}
            if "items" not in data or not isinstance(data["items"], list):
                data["items"] = []
            return data
    except Exception as e:
        print(f"[grocery] Load error: {e}")
        return {"items": [], "updated_at": None}


def save_grocery_list(data: dict) -> bool:
    """Save grocery checklist atomically to JSON storage."""
    try:
        GROCERY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data["updated_at"] = datetime.now().isoformat()
        temp_file = GROCERY_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        temp_file.replace(GROCERY_FILE)
        return True
    except Exception as e:
        print(f"[grocery] Save error: {e}")
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


# ─────────────────────────────────────────────
# Grocery Checklist API Endpoints
# ─────────────────────────────────────────────

@app.route("/api/grocery", methods=["GET"])
def get_grocery_list():
    """Retrieve full grocery checklist."""
    data = load_grocery_list()
    return jsonify(data)


@app.route("/api/grocery/item", methods=["POST"])
def add_grocery_item():
    """Add a single item manually to the grocery checklist."""
    payload = request.get_json() or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Item name is required"}), 400

    quantity = (payload.get("quantity") or "").strip()
    note = (payload.get("note") or "").strip()
    recipe_id = (payload.get("recipe_id") or "").strip()
    recipe_title = (payload.get("recipe_title") or "Manual / Custom").strip()
    category = (payload.get("category") or "General").strip()

    import time
    item_id = f"g_{int(time.time()*1000)}_{os.urandom(3).hex()}"
    new_item = {
        "id": item_id,
        "name": name,
        "quantity": quantity,
        "note": note,
        "checked": False,
        "recipe_id": recipe_id,
        "recipe_title": recipe_title,
        "category": category,
        "created_at": datetime.now().isoformat()
    }

    data = load_grocery_list()
    data["items"].insert(0, new_item)
    save_grocery_list(data)
    return jsonify({"success": True, "item": new_item, "items": data["items"]})


@app.route("/api/grocery/item/<item_id>", methods=["PATCH"])
def update_grocery_item(item_id):
    """Toggle checked status or edit item properties."""
    payload = request.get_json() or {}
    data = load_grocery_list()
    target = None
    for item in data.get("items", []):
        if item.get("id") == item_id:
            target = item
            break

    if not target:
        return jsonify({"error": "Item not found"}), 404

    if "checked" in payload:
        target["checked"] = bool(payload["checked"])
    if "name" in payload and str(payload["name"]).strip():
        target["name"] = str(payload["name"]).strip()
    if "quantity" in payload:
        target["quantity"] = str(payload["quantity"]).strip()
    if "note" in payload:
        target["note"] = str(payload["note"]).strip()

    save_grocery_list(data)
    return jsonify({"success": True, "item": target, "items": data["items"]})


@app.route("/api/grocery/item/<item_id>", methods=["DELETE"])
def delete_grocery_item(item_id):
    """Delete a single grocery item by ID."""
    data = load_grocery_list()
    initial_count = len(data.get("items", []))
    data["items"] = [i for i in data.get("items", []) if i.get("id") != item_id]
    if len(data["items"]) != initial_count:
        save_grocery_list(data)
    return jsonify({"success": True, "items": data["items"]})


@app.route("/api/grocery/import", methods=["POST"])
def import_grocery_items():
    """Import ingredients from a recipe into the grocery checklist."""
    payload = request.get_json() or {}
    recipe_id = (payload.get("recipe_id") or "").strip()
    recipe_title = (payload.get("recipe_title") or "").strip()
    ingredients = payload.get("ingredients") or []
    mode = payload.get("mode", "append")  # "append" or "replace"

    # If ingredients not passed directly, look up recipe from recipes.json
    if not ingredients and recipe_id:
        recipes = load_recipes()
        for r in recipes:
            if r.get("id") == recipe_id:
                recipe_title = recipe_title or r.get("recipe", {}).get("recipe_name", "Recipe")
                ingredients = r.get("recipe", {}).get("ingredients", [])
                break

    if not ingredients:
        return jsonify({"error": "No ingredients found to import"}), 400

    import time
    data = load_grocery_list()
    if mode == "replace":
        data["items"] = []

    added = []
    base_time = int(time.time() * 1000)
    for idx, ing in enumerate(ingredients):
        if isinstance(ing, str):
            name = ing.strip()
            qty = ""
            note = ""
        elif isinstance(ing, dict):
            name = (ing.get("name") or "").strip()
            qty = (ing.get("quantity") or "").strip()
            note = (ing.get("note") or "").strip()
        else:
            continue

        if not name:
            continue

        item = {
            "id": f"g_{base_time}_{idx}_{os.urandom(2).hex()}",
            "name": name,
            "quantity": qty,
            "note": note,
            "checked": False,
            "recipe_id": recipe_id,
            "recipe_title": recipe_title or "Imported Recipe",
            "created_at": datetime.now().isoformat()
        }
        data["items"].append(item)
        added.append(item)

    save_grocery_list(data)
    return jsonify({"success": True, "imported_count": len(added), "items": data["items"]})


@app.route("/api/grocery/clear", methods=["POST", "DELETE"])
def clear_grocery_list():
    """Clear whole checklist or just completed items."""
    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "all")  # "all" or "completed"
    data = load_grocery_list()
    if mode == "completed":
        data["items"] = [i for i in data.get("items", []) if not i.get("checked")]
    else:
        data["items"] = []
    save_grocery_list(data)
    return jsonify({"success": True, "items": data["items"]})


@app.route("/api/grocery/sync", methods=["POST", "PUT"])
def sync_full_grocery_list():
    """Bulk replace or sync full grocery list state."""
    payload = request.get_json() or {}
    items = payload.get("items", [])
    if not isinstance(items, list):
        return jsonify({"error": "Invalid items format"}), 400

    data = {"items": items, "updated_at": datetime.now().isoformat()}
    save_grocery_list(data)
    return jsonify({"success": True, "items": data["items"]})


@app.route("/api/extract", methods=["POST"])
def extract():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    notes = data.get("notes", "").strip()

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
            video_info = fetch_video_info(url, tmpdir, custom_notes=notes)

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
