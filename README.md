# 🍽️ Recipe Helper Agent & Kitchen Assistant

A full-stack, AI-powered culinary companion and digital cookbook. Paste any **YouTube Shorts** or **Instagram Reel** link to automatically extract structured, visual recipe cards — with ingredients, tools, steps, and tips — powered by Google Gemini AI.

Includes a **3-Tab Web Dashboard** (`http://localhost:8080`), an offline MP4 video player, and a **Persistent Grocery & To-Do Checklist with Memory** that remembers every checked item even across server restarts and machine reboots.

---

## ✨ Key Features

### 🛒 1. Persistent Grocery & To-Do Checklist (with Memory)
* **Server-Persistent State**: Backed by atomic disk storage in `data/grocery.json`. Every time an ingredient is checked or unchecked, the exact state is preserved on disk immediately — even if the server stops, restarts, or crashes.
* **1-Click Recipe Export**:
  * In the detailed recipe viewer: Click **"🛒 Export to Grocery List"** (in header or ingredients card) to export all recipe ingredients directly into your shopping checklist.
  * In the saved recipes collection: Tap the **"🛒"** button on any recipe card to export instantly.
* **Import from Recipe Modal**:
  * Tap **"📥 Import from Recipe"** to open a real-time searchable recipe picker.
  * Choose **"＋ Add"** (appends ingredients to your active list) or **"🔄 Replace"** (clears and loads only this recipe's items).
* **Manual Item Entry**:
  * Dedicated input bar for custom household items (e.g. *Milk*, *2 Avocados*, *Olive Oil*) with optional quantities and notes.
* **Interactive Checklist & Tools**:
  * Real-time completion progress bar (e.g., `50% completed`).
  * Filter pills: **All**, **🛒 To Buy (Unchecked)**, and **✅ Checked**.
  * **"📋 Copy List"**: Copies a clean, formatted shopping checklist directly to your clipboard for WhatsApp, SMS, or Notes.
  * **"🧹 Clear Checked"**: Removes purchased/completed items while keeping remaining items to buy.
  * **"🗑️ Clear Whole List"**: Empties the checklist after confirmation.
  * **"✕" Individual Delete**: Remove any single item from the list.

---

### 📚 2. Recipe Collection & Smart Catalog
* **7 Quick-Filter Categories**: Filter instantly by `Main Course`, `High Protein`, `Snack`, `Breakfast`, `Dessert`, `Salad`, or `Drink`.
* **Full-Text Search & Multi-Filters**: Search across recipe names, ingredients, cuisines, difficulty levels, cook times, and required kitchen tools (e.g., Air Fryer, Pan, Oven).
* **Editable Recipe Parameters**: Change difficulty or recatalog recipe types with 1 click directly from the UI cards.
* **Offline Video Player**: Watch downloaded MP4 recipe videos locally without ads or leaving the page.
* **Prep Snapshots & Visual Steps**: Automatic keyframe extraction (via OpenCV) displays high-resolution thumbnails for ingredients and each cooking milestone.

---

### 🤖 3. Multimodal Extraction Engine
* Works with **YouTube Shorts** and **Instagram Reels**.
* Extracts information from **video streams, audio transcripts, post captions, and creator pinned comments**.
* Multimodal fallback handles videos without speech or captions by sending video frames directly to Gemini AI.

---

### ☁️ 4. GitHub Pages Static Sync
* Automatically compiles a standalone static site in `docs/` (`docs/index.html` and `docs/recipes.json`).
* Hosted for **100% free on GitHub Pages** with responsive mobile layout and offline friendliness.

---

## 🚀 Quick Start

### 1. Requirements & Setup
```bash
# Clone and enter directory
cd personal-ai

# Activate virtual environment
source .venv/bin/activate

# Configure your Gemini API Key in .env
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=AIzaSy...
```

### 2. Start the Local Server
```bash
# Using the desktop service controller:
./manage_server.sh start

# Or directly with python:
python server.py
```
Open **`http://localhost:8080`** in your browser.

To access the shopping list on your phone while walking through the grocery store, simply open:
**`http://<YOUR_LAN_IP>:8080`** (displayed when the server starts).

### 3. Server Controller Commands
```bash
./manage_server.sh start     # Starts background server & opens browser
./manage_server.sh stop      # Stops server cleanly
./manage_server.sh restart   # Restarts server and reloads configuration
./manage_server.sh status    # Displays active PID and port status
```

---

## 📡 REST API Reference

The Flask backend exposes clean REST endpoints for automation, mobile clients, and integrations:

### Grocery & Checklist API
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/grocery` | Returns the active checklist from `data/grocery.json` |
| `POST` | `/api/grocery/item` | Adds a manual item (`{"name": "...", "quantity": "..."}`) |
| `PATCH`| `/api/grocery/item/<id>` | Toggles `checked` state or updates item text |
| `DELETE`| `/api/grocery/item/<id>` | Removes an individual grocery item |
| `POST` | `/api/grocery/import` | Imports ingredients from a recipe (`mode: "append"` or `"replace"`) |
| `POST` | `/api/grocery/clear` | Clears all items (`mode: "all"`) or completed (`mode: "completed"`) |
| `POST` | `/api/grocery/sync` | Bulk syncs or updates the entire grocery list |

### Recipe Catalog & Extraction API
| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/recipes` | Retrieves all saved recipes from `data/recipes.json` |
| `PATCH`| `/api/recipes/<id>` | Updates recipe fields (difficulty, category, cuisine) |
| `DELETE`| `/api/recipes/<id>` | Deletes recipe and associated video files |
| `POST` | `/api/extract` | Triggers AI extraction from a video URL (`{"url": "...", "notes": "..."}`) |
| `POST` | `/api/sync` | Manually triggers static site regeneration and GitHub Pages push |

---

## 📁 Project Structure

```text
personal-ai/
├── server.py              # Flask backend, extraction engine, auto-sync worker, REST API
├── export_static.py       # Compiles data/recipes.json into docs/ static site & auto-pushes
├── batch_agent.py         # Batch extraction CLI for CSV/text lists of URLs
├── recipe_agent.py        # Standalone CLI interface for single URL extraction
├── manage_server.sh       # Service controller (start, stop, restart, status)
├── start_server.desktop   # Linux desktop launcher for 1-click server start
├── requirements.txt       # Python dependencies (flask, yt-dlp, google-genai, opencv, etc.)
├── .env                   # Secret credentials (GEMINI_API_KEY) — NEVER COMMITTED
├── context.md             # Living architecture & engineering context documentation
├── data/
│   ├── recipes.json       # Canonical database of extracted recipes
│   └── grocery.json       # Persistent grocery checklist state with memory across restarts
├── docs/                  # GitHub Pages root folder (branch: main, path: /docs)
│   ├── index.html         # Standalone public static cookbook
│   └── recipes.json       # Public static JSON recipe feed
├── static/
│   ├── index.html         # Local 3-tab web dashboard (Extract, Saved, Grocery/To-Do)
│   └── videos/            # Downloaded local MP4 video streams
└── template/
    └── recipe.html.jinja  # Jinja2 template for single static exports
```

---

## 💡 Tips & Mobile Usage
* **Mobile Grocery Shopping**: Open `http://<LAN_IP>:8080` on your mobile phone on home Wi-Fi before heading to the store. Items stay checked in real-time.
* **WhatsApp Sharing**: Use the **"📋 Copy List"** button in the Grocery tab to send a formatted checklist to family members with one tap.
* **Air Fryer & Smart Pot Synergy**: Check the companion repository in `projects/food` for tailored cooking runbooks for the **Faber 6L Air Fryer** and **Nutricook Smart Pot 2**.
