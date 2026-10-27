# Project Context: Recipe Helper Agent

## 1. Executive Summary
Recipe Helper Agent is a full-stack, AI-powered culinary companion and digital cookbook that extracts structured, visual recipes from **YouTube Shorts** and **Instagram Reels**. It processes videos locally to extract ingredients, equipment, timing, cooking instructions, and high-resolution keyframe snapshots (via OpenCV), then auto-compiles a standalone static cookbook hosted for **100% free on GitHub Pages**.

---

## 2. Core Architecture & Hybrid Model

```
                    LOCAL MACHINE (Private & Heavy Work)
┌────────────────────────────────────────────────────────────────────────┐
│  • Flask Web Server (http://localhost:8080 & http://<LAN_IP>:8080)     │
│  • 3-Tab Web App (Extract Recipe, Saved Recipes, Grocery / To-Do)      │
│  • Persistent Grocery Engine (data/grocery.json & /api/grocery REST)   │
│  • yt-dlp Video & Subtitle Extractor (Direct signed URL parsing)       │
│  • OpenCV Keyframe Extraction (Laplacian variance sharpness filtering) │
│  • Google Gemini AI Client (Private API key, multimodal video fallback)│
│  • Local Video Player & MP4 Storage (static/videos/<id>.mp4)          │
│  • Local Database (data/recipes.json)                                  │
│  • Batch Agent (batch_agent.py) for bulk URL/CSV extractions           │
│  • Desktop Controller (manage_server.sh & start_server.desktop)        │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ Auto-syncs on save/edit/delete/milestones
                                   ▼
                    GITHUB PAGES (Public Static Hosting)
┌────────────────────────────────────────────────────────────────────────┐
│  • Free forever global CDN (https://imrugesh9.github.io/recipe-helper/)│
│  • Standalone Static Site in docs/ (docs/index.html & docs/recipes.json)│
│  • Category Quick-Filter Bar (Main Course, High Protein, Snack, etc.)  │
│  • Multi-parameter Filtering (category, difficulty, cook/prep time)    │
│  • Fully Mobile-Responsive (touch checklist, full-screen mobile modal) │
│  • Full-text Search & Sorting                                          │
│  • Visual step images & prep gallery (embedded base64, zero external CDN)│
│  • Interactive ingredient checklist & lightbox zoom                    │
│  • Deep-linking support via URL hash (#rec_id)                         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Key Files & Structure

```
personal-ai/
├── server.py              # Flask backend, extraction engine, auto-sync worker, LAN IP detection, REST API
├── export_static.py       # Compiles data/recipes.json into responsive docs/ static site & auto-pushes
├── batch_agent.py         # Batch extraction CLI for CSV/text lists of Instagram & YouTube URLs
├── recipe_agent.py        # Standalone CLI interface for single URL extraction
├── manage_server.sh       # Service controller (start, stop, restart, status) with desktop alerts
├── start_server.desktop   # Linux desktop launcher for 1-click local server control
├── requirements.txt       # Python dependencies (flask, yt-dlp, google-genai, opencv-python-headless, etc.)
├── .env                   # Secret credentials (GEMINI_API_KEY) — NEVER COMMITTED
├── .env.example           # Template for environment variables
├── .gitignore             # Configured to protect secrets and ignore .venv, *.bundle, *.mp4
├── context.md             # Living architecture & technical context documentation
├── handoff.md             # Migration & setup guide across environments
├── data/
│   ├── recipes.json       # Canonical database of 73 extracted culinary recipes with visual snapshots
│   └── grocery.json       # Persistent grocery checklist with item states, quantities, recipe origins, and timestamps
├── docs/                  # GitHub Pages root folder (branch: main, path: /docs)
│   ├── index.html         # Standalone, interactive, mobile-responsive public cookbook (73 recipes)
│   └── recipes.json       # Raw static JSON feed
├── static/
│   ├── index.html         # Local web app interface (Extract, Saved tab, Category Pills, Card Editor)
│   └── videos/            # Downloaded local MP4 video streams for local player
└── template/
    └── recipe.html.jinja  # Jinja2 template for single static exports
```

---

## 4. Key Engineering Discoveries & Solutions

1. **YouTube 429 Rate-Limiting on Subtitles**:
   - Calling `yt-dlp --write-auto-subs --sub-langs en.*` causes YouTube's timedtext service to return `HTTP 429: Too Many Requests` when auto-translating.
   - **Solution (`extract_captions_from_info`)**: Extracted direct signed URLs from `info['automatic_captions']` and `info['subtitles']`, prioritizing original language tracks (`hi-orig`, `en-orig`, `hi`, `en`), fetching clean VTT text with standard HTTP requests without triggering rate limits.

2. **Multimodal Gemini Fallback for Videos with No Captions/Description**:
   - Videos like `https://www.youtube.com/shorts/Lnr4OeAOgcU` have empty descriptions and no text.
   - **Solution**: The backend automatically uploads the downloaded video to Gemini via `client.files.upload()`. Gemini watches and listens to the video directly, extracting ingredients, measurements, and steps. File reference is deleted immediately after generation.

3. **Portrait / Shorts Video Format Selection**:
   - Vertical videos (9:16) often have split DASH streams without pre-muxed audio/video.
   - **Solution**: Format selector `best[ext=mp4]/bestvideo[height<=1280][ext=mp4]/bestvideo[width<=1280][ext=mp4]/best` downloads the best MP4 stream without requiring `ffmpeg` for local playback and frame extraction.

4. **OpenCV Motion-Blur Filtering**:
   - Extracts sharpest keyframes using Laplacian variance scoring over a 5-frame sample window around target timestamps.
   - Produces step snapshots, ingredient thumbnails, and a 4-milestone preparation gallery.

5. **Recipe Type Cataloging & Quick Filters**:
   - Categorizes recipes into 7 core types: `Main Course`, `High Protein`, `Snack`, `Breakfast`, `Dessert`, `Salad`, and `Drink`.
   - Built a horizontal category quick-filter pill bar with dynamic counts at the top of both the local server (`static/index.html`) and public static site (`docs/index.html`).
   - Integrated full category filtering into full-text search, filter panel selects, and card badges.
   - Enabled 1-click on-card re-cataloging via interactive badge dropdowns that trigger `PATCH /api/recipes/<id>` and persist to `data/recipes.json`.

6. **Recipe Removal & Video Deletion**:
   - Implemented `DELETE /api/recipes/<id>` in `server.py`.
   - Deletes entry from `data/recipes.json`, removes local video files (`static/videos/<id>.mp4`), and triggers automated Git push to GitHub Pages.
   - Added `🗑️ Remove` buttons on recipe cards and in the recipe detail header.

7. **Instagram Saved Posts Scraper via GraphQL Hooking**:
   - Standard DOM scrolling on Instagram terminates prematurely because Instagram unmounts off-screen elements and throttles pagination.
   - **Solution**: Injected a custom browser script into the user's logged-in Firefox session hooking `window.fetch` to intercept internal Instagram GraphQL paginated responses (`/api/v1/feed/saved/posts/`), retrieving all 291 saved reel URLs directly into a CSV export.

8. **Strict Culinary Validation & Non-Recipe Rejection**:
   - When batch-analyzing social feeds that contain mixed content (workouts, unboxings, memes, gaming clips), Gemini initially attempted to generate placeholder recipes.
   - **Solution**: Hardened validation in `batch_agent.py` and `server.py` to strictly reject items without valid `recipe_name`, items with empty ingredient lists, and items explicitly described as non-recipes. Successfully filtered out 171 non-culinary reels during bulk processing.

9. **Batch Processing with Sync Throttling (`batch_agent.py`)**:
   - Processing hundreds of URLs with per-recipe Git syncs would breach GitHub Pages deployment limits (10 builds/hour).
   - **Solution**: Local updates are saved per recipe to `data/recipes.json` immediately, while Git commits and pushes are throttled to milestone batches of 20 and upon final completion.

10. **Desktop Service Controller (`manage_server.sh` & `start_server.desktop`)**:
    - Built a robust toggle script to start, stop, restart, and inspect the Flask server.
    - Resolves active LAN IP, displays system tray notifications (`notify-send`), updates `server.pid`, and opens `http://localhost:8080` in the default browser.
    - Installed a `start_server.desktop` desktop shortcut for 1-click launching.

11. **Mobile-Responsive Public Cookbook (`docs/index.html`)**:
    - Grid uses `minmax(min(100%, 320px), 1fr)` with single-column cards on mobile viewports to prevent horizontal overflow.
    - Full-screen modal presentation on small screens with fixed floating `✕ Back` button.
    - Single-column touch checklist with 44px tap targets for ingredient check-offs while cooking.
    - 2-column mobile preparation milestone gallery.
    - Added `theme-color` and Apple web-app meta tags for seamless browser display.

12. **Instagram Caption & Pinned Comments Intelligence Engine**:
    - Solved recipe extraction inaccuracies where ingredient quantities and secret sauces are not spoken or displayed on-screen, but are published in the post caption or pinned in comments by the creator (e.g., `https://www.instagram.com/reels/Dd3FwFSsjff/` by `@batati.being.batati`).
    - Configured `yt-dlp` to extract metadata and comments simultaneously via `--write-comments`, with optional session cookie support (`cookies.txt`, `INSTAGRAM_COOKIES_PATH`, `INSTAGRAM_BROWSER`).
    - Implemented smart comment parsing in `server.py` and `recipe_agent.py` that prioritizes comments made by the creator (`uploader`, `channel`), pinned comments, and comments containing ingredient measurements.
    - Re-architected Gemini multimodal prompting so the model receives BOTH the full video file and the complete text payload (title, creator, caption, structured comments, and audio transcript), cross-referencing visual timestamps with written ingredients.
    - Added an optional expandable "Add Pinned Comment / Recipe Notes" input to the web interface (`static/index.html`) and `/api/extract` REST endpoint.

13. **Persistent Grocery & Shopping Checklist with Memory (`data/grocery.json`, `server.py`, `static/index.html`)**:
    - Created a 3rd main navigation tab (`🛒 Grocery / To-Do`) with dynamic unchecked item count badge, progress bar, and category/completion filters.
    - **Persistent State Across Server Restarts**: Integrated atomic disk storage in `data/grocery.json` via dedicated REST endpoints (`GET /api/grocery`, `POST /api/grocery/item`, `PATCH /api/grocery/item/<id>`, `DELETE /api/grocery/item/<id>`, `POST /api/grocery/import`, `POST /api/grocery/clear`). Checking or unchecking an item writes immediately to disk, so state survives server restarts and crashes.
    - **1-Click Recipe Export**: Added "Export to Grocery List" buttons in both the recipe detail header and ingredients card, plus a quick `🛒` button on every saved recipe card.
    - **Interactive Import Modal**: Built an in-tab recipe picker modal allowing users to search saved recipes and choose between appending ingredients or replacing the whole list.
    - **Manual Item Add**: Fast input bar for custom household items (e.g. Milk, Eggs, Olive Oil) with name, quantity/notes, and Enter key support.
    - **List Management Tools**: Quick buttons for "Clear Whole List", "Clear Checked", and "Copy List" (formatted for WhatsApp/Notes sharing).

---

## 5. Deployment & Links
* **Git Remote**: `git@github.com:iMrugesh9/recipe-helper.git` (Branch: `main`)
* **GitHub Pages Site**: [https://imrugesh9.github.io/recipe-helper/](https://imrugesh9.github.io/recipe-helper/)
* **Static Feed**: [https://imrugesh9.github.io/recipe-helper/recipes.json](https://imrugesh9.github.io/recipe-helper/recipes.json)
* **Local Web Interface**: `http://localhost:8080` (and `http://<LAN_IP>:8080`)

---

## 6. Current Recipe Database Stats (73 Recipes in `data/recipes.json`)

* **Total Active Recipes**: 73
* **Category Breakdown**:
  * 🥤 **Drink**: 20
  * 🍲 **Main Course**: 13
  * 💪 **High Protein**: 13
  * 🍰 **Dessert**: 12
  * 🥪 **Snack**: 7
  * 🌅 **Breakfast**: 5
  * 🥗 **Salad**: 3

### Batch Ingestion Metrics (from 291 Saved Reels):
* **Total Posts Extracted**: 291
* **Pre-existing in Cookbook**: 54
* **New Culinary Recipes Added**: 28
* **Non-Recipe Media Filtered Out**: 171
* **Inaccessible / Deleted Posts**: 38
