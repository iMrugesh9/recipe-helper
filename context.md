# Project Context: Recipe Helper Agent

## 1. Executive Summary
Recipe Helper Agent is a full-stack, AI-powered culinary tool that extracts structured, visual recipes from **YouTube Shorts** and **Instagram Reels**. It processes videos locally to extract ingredients, equipment, timing, cooking instructions, and high-resolution keyframe snapshots (via OpenCV), then auto-compiles a standalone static cookbook hosted for **100% free on GitHub Pages**.

---

## 2. Core Architecture & Hybrid Model

```
                    LOCAL MACHINE (Private & Heavy Work)
┌────────────────────────────────────────────────────────────────────────┐
│  • Flask Web Server (http://localhost:8080 & http://<LAN_IP>:8080)     │
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
│  • Free forever global CDN (https://imrugesh9.github.io/recipe-helper/)│
│  • Standalone Static Site in docs/ (docs/index.html & docs/recipes.json)│
│  • Fully Mobile-Responsive (touch checklist, full-screen mobile modal) │
│  • Multi-parameter Filtering (difficulty, cook time, prep time, tools) │
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
├── server.py              # Flask backend, extraction engine, auto-sync worker, LAN IP detection
├── export_static.py       # Compiles data/recipes.json into responsive docs/ static site & auto-pushes
├── recipe_agent.py        # Standalone CLI interface for single URL extraction
├── requirements.txt       # Python dependencies (flask, yt-dlp, google-genai, opencv-python-headless, etc.)
├── .env                   # Secret credentials (GEMINI_API_KEY) — NEVER COMMITTED
├── .env.example           # Template for environment variables
├── .gitignore             # Configured to protect secrets and ignore .venv, *.bundle, *.mp4
├── context.md             # Living architecture & technical context documentation
├── handoff.md             # Migration & setup guide across environments
├── data/
│   └── recipes.json       # Canonical database of 7 extracted recipes with visual snapshots
├── docs/                  # GitHub Pages root folder (branch: main, path: /docs)
│   ├── index.html         # Standalone, interactive, mobile-responsive public cookbook
│   └── recipes.json       # Raw static JSON feed
├── static/
│   ├── index.html         # Local web app interface (Extract & Saved Recipes tabs)
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

5. **Editable Difficulty Parameter**:
   - Recipes extract an initial difficulty (`Easy`, `Medium`, `Hard`).
   - The user can edit the difficulty rating directly from the detail view or from the collection cards.
   - Persists immediately via `PATCH /api/recipes/<recipe_id>` to `data/recipes.json` and updates `docs/`.

6. **Local Port & LAN Mobile Access**:
   - Port `8080` is configured as the default port.
   - Server runs on `host="0.0.0.0"` with dynamic local IP discovery via `get_local_ip()`.
   - On startup, the console displays both local (`http://localhost:8080`) and mobile LAN (`http://<LAN_IP>:8080`) URLs so phones on the same Wi-Fi can trigger extractions and playback directly.

7. **Local Video Persistence vs. Static Web App Separation**:
   - `.mp4` video files are intentionally git-ignored (`*.mp4`) to avoid hitting Git / GitHub Pages 1GB storage limits.
   - The local app streams videos from `static/videos/<id>.mp4`.
   - The public GitHub Pages site embeds high-res base64 image snapshots and deep-links to the original Reel/Short (`source_url`), keeping the public static build 100% free and lightning fast on CDN edges.

8. **Automated Dual-Sync (Data + Static Site)**:
   - `auto_sync_github()` in `export_static.py` stages both `docs/` and `data/recipes.json`.
   - Commits and pushes directly via the configured SSH key (`git@github.com:iMrugesh9/recipe-helper.git`).
   - Removed `[skip ci]` directive so GitHub Pages deployment actions trigger instantaneously on push.

9. **Mobile-Responsive Public Cookbook (`docs/index.html`)**:
   - Grid uses `minmax(min(100%, 320px), 1fr)` with single-column cards on mobile viewports to prevent horizontal overflow.
   - Full-screen modal presentation on small screens with fixed floating `✕ Back` button.
   - Single-column touch checklist with 44px tap targets for ingredient check-offs while cooking.
   - 2-column mobile preparation milestone gallery.
   - Added `theme-color` and Apple web-app meta tags for seamless browser display.

---

## 5. Deployment & Links
* **Git Remote**: `git@github.com:iMrugesh9/recipe-helper.git` (Branch: `main`)
* **GitHub Pages Site**: [https://imrugesh9.github.io/recipe-helper/](https://imrugesh9.github.io/recipe-helper/)
* **Static Feed**: [https://imrugesh9.github.io/recipe-helper/recipes.json](https://imrugesh9.github.io/recipe-helper/recipes.json)

---

## 6. Current Saved Recipes (in `data/recipes.json`)
1. **Lehsuni Dhaniya Paneer** (Instagram Reel)
2. **Lemon Garlic Soya** (YouTube Short)
3. **Soya Chilli** (High protein, low calories) (YouTube Short)
4. **Non-fried Manchurian** (Instagram Reel)
5. **Paneer Tikka Roll** (YouTube Short)
6. **Masoor Dal & Tomato Crispy Crackers** (Instagram Reel)
7. **Air Fryer Schezwan Fried Rice** (Instagram Reel)
