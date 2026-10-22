# Project Context: Recipe Helper Agent

## 1. Executive Summary
Recipe Helper Agent is a full-stack, AI-powered culinary tool that extracts structured, visual recipes from **YouTube Shorts** and **Instagram Reels**. It processes videos locally to extract ingredients, equipment, timing, cooking instructions, and high-resolution keyframe snapshots (via OpenCV), then auto-compiles a standalone static cookbook hosted for **100% free on GitHub Pages**.

---

## 2. Core Architecture & Hybrid Model

```
                    LOCAL MACHINE (Private & Heavy Work)
┌────────────────────────────────────────────────────────────────────────┐
│  • Flask Web Server (http://localhost:8080)                            │
│  • yt-dlp Video & Subtitle Extractor (Direct signed URL parsing)       │
│  • OpenCV Keyframe Extraction (Laplacian variance sharpness filtering) │
│  • Google Gemini AI Client (Private API key, multimodal video fallback)│
│  • Local Video Player & MP4 Storage (static/videos/<id>.mp4)          │
│  • Local Storage (data/recipes.json)                                   │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │ Auto-syncs on save/edit/delete
                                   ▼
                    GITHUB PAGES (Public Static Hosting)
┌────────────────────────────────────────────────────────────────────────┐
│  • Free forever global CDN (https://<username>.github.io/<repo>/)      │
│  • Standalone Static Site in docs/ (docs/index.html & docs/recipes.json)│
│  • Multi-parameter Filtering (difficulty, cook time, prep time, tools) │
│  • Full-text Search & Sorting                                          │
│  • Visual step images & prep gallery (embedded base64, zero external CDN│
│  • Interactive ingredient checklist & lightbox zoom                    │
│  • Deep-linking support via URL hash (#rec_id)                         │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Key Files & Structure

```
Personal-Ai/
├── server.py              # Flask backend, extraction engine, auto-sync worker
├── export_static.py       # Compiles data/recipes.json into docs/ static site
├── recipe_agent.py        # Standalone CLI interface for single URL extraction
├── requirements.txt       # Python dependencies (flask, yt-dlp, google-genai, opencv-python-headless, etc.)
├── .env                   # Secret credentials (GEMINI_API_KEY) — NEVER COMMITTED
├── .env.example           # Template for environment variables
├── .gitignore             # Configured to protect secrets and ignore .venv, *.bundle, videos
├── data/
│   └── recipes.json       # Canonical database of 6 extracted recipes with visual snapshots
├── docs/                  # GitHub Pages root folder
│   ├── index.html         # Standalone, interactive public cookbook
│   └── recipes.json       # Raw static JSON feed
├── static/
│   ├── index.html         # Local web app interface (Extract & Saved Recipes tabs)
│   └── videos/            # Downloaded local MP4 video streams
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

5. **Editable Difficulty Parameter**:
   - Recipes extract an initial difficulty (`Easy`, `Medium`, `Hard`).
   - The user can edit the difficulty rating directly from the detail view or from the collection cards.
   - Persists immediately via `PATCH /api/recipes/<recipe_id>` to `data/recipes.json` and updates `docs/`.

6. **Local Port Selection**:
   - macOS uses port 5000 for AirPlay Receiver. Port `8080` is configured as the default port.

---

## 5. Current Saved Recipes (in `data/recipes.json`)
1. **Lemon Garlic Soya**
2. **Soya Chilli** (High protein, low calories)
3. **Non-fried Manchurian**
4. **Paneer Tikka Roll**
5. **Masoor Dal & Tomato Crispy Crackers**
6. **Air Fryer Schezwan Fried Rice**
