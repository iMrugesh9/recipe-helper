#!/usr/bin/env python3
"""
Batch Recipe Analyzer
=====================
Analyzes multiple Instagram Reels / YouTube Shorts in batch.
"""

import sys
import os
import re
import csv
import glob
import json
import time
import shutil
import tempfile
import traceback
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from server import (
    fetch_video_info,
    extract_recipe_with_gemini,
    extract_visual_snippets,
    load_recipes,
    VIDEOS_DIR,
    DATA_FILE,
)
from export_static import auto_sync_github, generate_static_site


def parse_urls_from_sources(sources: list[str]) -> list[str]:
    """Extract and deduplicate Instagram/YouTube URLs from files or wildcards."""
    raw_urls = []
    
    # Expand any glob patterns
    expanded = []
    for s in sources:
        matching = glob.glob(os.path.expanduser(s))
        if matching:
            expanded.extend(matching)
        else:
            expanded.append(s)

    for item in expanded:
        p = Path(item)
        if p.exists() and p.is_file():
            print(f"📄 Reading URLs from: {p.name}")
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                for row in reader:
                    for cell in row:
                        c = cell.strip().strip('"').strip("'")
                        if "instagram.com" in c or "youtube.com" in c or "youtu.be" in c:
                            raw_urls.append(c)
        else:
            if "instagram.com" in item or "youtube.com" in item or "youtu.be" in item:
                raw_urls.append(item.strip())

    # Clean tracking params and deduplicate
    clean_urls = []
    seen = set()
    for u in raw_urls:
        cleaned = re.sub(r"\?.*$", "", u).rstrip("/") + "/"
        if cleaned not in seen:
            seen.add(cleaned)
            clean_urls.append(cleaned)

    return clean_urls


def save_recipe_local(recipe_entry: dict):
    """Save recipe to data/recipes.json without triggering git push immediately."""
    recipes = load_recipes()
    recipes = [r for r in recipes if r.get("id") != recipe_entry.get("id")]
    recipes.insert(0, recipe_entry)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(recipes, f, ensure_ascii=False, indent=2)


def classify_recipe(r: dict) -> str:
    """Infer recipe category type based on title, description, tags, and ingredients."""
    if r.get("recipe_type"):
        return r.get("recipe_type")
    name = (r.get("recipe_name") or "").lower()
    desc = (r.get("description") or "").lower()
    tags = " ".join(r.get("tags") or []).lower()
    ings = " ".join([i.get("name", "") for i in r.get("ingredients") or []]).lower()
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


def process_single_video(url: str) -> dict | None:
    """Download video, extract via Gemini, extract OpenCV snapshots, and save locally."""
    with tempfile.TemporaryDirectory() as tmpdir:
        video_info = fetch_video_info(url, tmpdir)

        if not video_info.get("transcript") and not video_info.get("video_path"):
            raise ValueError("Could not extract video stream or transcript from URL.")

        recipe_data = extract_recipe_with_gemini(video_info)

        # Non-recipe detection
        name = recipe_data.get("recipe_name")
        ingredients = recipe_data.get("ingredients") or []
        desc = (recipe_data.get("description") or "").lower()
        if not name or len(ingredients) == 0 or "not a recipe" in desc or "not a cooking" in desc:
            print("   ℹ️ Skipped: Video does not appear to be a genuine culinary recipe.")
            return None

        recipe_data["recipe_type"] = classify_recipe(recipe_data)

        # Extract visual frames
        if video_info.get("video_path"):
            recipe_data = extract_visual_snippets(video_info["video_path"], recipe_data)

        recipe_id = f"rec_{int(datetime.now().timestamp())}"
        video_url = None

        # Copy local MP4 video
        raw_video_path = video_info.get("video_path")
        if raw_video_path and os.path.exists(raw_video_path):
            try:
                ext = Path(raw_video_path).suffix or ".mp4"
                saved_video_filename = f"{recipe_id}{ext}"
                dest_path = VIDEOS_DIR / saved_video_filename
                shutil.copy2(raw_video_path, dest_path)
                video_url = f"/static/videos/{saved_video_filename}"
            except Exception as ve:
                print(f"   ⚠️ Video copy warning: {ve}")

        recipe_entry = {
            "id": recipe_id,
            "recipe": recipe_data,
            "thumbnail_url": video_info.get("thumbnail_url", ""),
            "source_url": url,
            "video_url": video_url,
            "generated_at": datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        }

        save_recipe_local(recipe_entry)
        return recipe_entry


def run_batch(sources: list[str]):
    all_urls = parse_urls_from_sources(sources)

    if not all_urls:
        print("❌ No valid Instagram or YouTube URLs found in provided files.")
        return

    print(f"\n📊 Total unique URLs extracted: {len(all_urls)}")

    existing_recipes = load_recipes()
    existing_urls = {
        re.sub(r"\?.*$", "", r.get("source_url", "")).rstrip("/") + "/"
        for r in existing_recipes
    }

    pending_urls = [u for u in all_urls if u not in existing_urls]
    already_saved = len(all_urls) - len(pending_urls)

    if already_saved > 0:
        print(f"⏭️  Skipping {already_saved} URL(s) already in your cookbook.")

    if not pending_urls:
        print("🎉 All URLs in this list are already analyzed and in your cookbook!")
        return

    print(f"⚡ Starting batch analysis for {len(pending_urls)} new recipes...\n")

    successful = []
    skipped_non_recipe = []
    failed = []

    for idx, url in enumerate(pending_urls, start=1):
        pct = int((idx / len(pending_urls)) * 100)
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"[{idx}/{len(pending_urls)}] ({pct}%) Analyzing: {url}")
        
        try:
            entry = process_single_video(url)
            if entry:
                name = entry.get("recipe", {}).get("recipe_name", "Untitled Recipe")
                ing_count = len(entry.get("recipe", {}).get("ingredients", []))
                step_count = len(entry.get("recipe", {}).get("steps", []))
                print(f"   ✅ Saved: '{name}' ({ing_count} ingredients, {step_count} steps)")
                successful.append((name, url))
            else:
                skipped_non_recipe.append(url)
        except Exception as e:
            err_msg = str(e)
            print(f"   ❌ Error: {err_msg}")
            failed.append((url, err_msg))

        # Periodic sync to GitHub Pages every 10 successful recipes
        if len(successful) > 0 and len(successful) % 10 == 0:
            print(f"\n📦 Periodic Milestone: Syncing {len(successful)} new recipes to GitHub Pages...")
            try:
                auto_sync_github()
            except Exception as se:
                print(f"   ⚠️ Sync warning: {se}")

        # Polite 2.5s pause to prevent IP/API rate-limits
        if idx < len(pending_urls):
            time.sleep(2.5)

    print(f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"🏁 Batch Processing Complete!")
    print(f"   ✨ Successfully Added: {len(successful)} recipes")
    print(f"   ℹ️ Non-Recipe Reels Skipped: {len(skipped_non_recipe)}")
    print(f"   ⚠️ Failed/Unavailable: {len(failed)}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    # Final static build and GitHub push
    if successful:
        print("🔄 Generating final static site and pushing all recipes to GitHub Pages...")
        try:
            res = auto_sync_github()
            print(f"📄 {res.get('message')}")
        except Exception as se:
            print(f"⚠️ Push error: {se}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default to all saved CSVs in Downloads
        default_files = glob.glob(os.path.expanduser("~/Downloads/instagram_saved_posts*.csv"))
        if default_files:
            run_batch(default_files)
        else:
            print("Usage: python batch_agent.py <csv_or_url...>")
    else:
        run_batch(sys.argv[1:])
