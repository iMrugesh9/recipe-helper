# 🍽️ Recipe Helper Agent

Paste a **YouTube Shorts** or **Instagram Reel** link and get a beautiful, standalone HTML recipe card — with ingredients, tools, steps, and tips — automatically extracted by AI.

---

## ✨ Features

- 🎬 Works with **YouTube Shorts** and **public Instagram Reels**
- 🤖 Uses **Google Gemini AI** to extract structured recipe data
- ✅ **Interactive ingredient checklist** — check off items as you cook
- 🔧 **Tools & Equipment** section
- 👨‍🍳 **Step-by-step process** with timing indicators
- 💡 **Tips & Tricks** from the chef
- 🌙 **Beautiful dark-mode** design, fully standalone HTML
- 🖨️ Print-friendly output

---

## 🚀 Quick Start

### 1. Get a Gemini API Key (free)

1. Go to → **https://aistudio.google.com/app/apikey**
2. Sign in with your Google account
3. Click **"Create API key"**
4. Copy the key

### 2. Set Up Your API Key

```bash
# In the project directory:
cp .env.example .env
```

Open `.env` and paste your key:
```
GEMINI_API_KEY=AIzaSy...your_key_here...
```

### 3. Activate the Virtual Environment

```bash
source .venv/bin/activate
```

### 4. Run the Agent!

```bash
python recipe_agent.py https://www.youtube.com/shorts/YOUR_VIDEO_ID

# Or Instagram:
python recipe_agent.py https://www.instagram.com/reel/YOUR_REEL_ID/
```

The recipe HTML page will be saved to `output/` and open automatically in your browser.

---

## 📁 Project Structure

```
Personal-Ai/
├── recipe_agent.py        # Main script
├── requirements.txt       # Python dependencies
├── .env                   # Your API key (never share this!)
├── .env.example           # Key template
├── template/
│   └── recipe.html.jinja  # HTML page template
└── output/                # Generated recipe pages (auto-created)
```

---

## ⚠️ Notes

- **Instagram**: Only works with **public** accounts. Private accounts require cookie-based login.
- **Transcription fallback**: If a video has no subtitles, the agent attempts Whisper audio transcription (requires `openai-whisper` and `ffmpeg`).
- All generated HTML files are **fully standalone** — share them or save them without needing internet.

---

## 🛠️ Troubleshooting

| Problem | Solution |
|---|---|
| `No GEMINI_API_KEY` | Create `.env` file with your key |
| `yt-dlp not found` | Make sure venv is active: `source .venv/bin/activate` |
| `No transcript found` | Try a video with auto-captions enabled |
| Instagram fails | Make sure the account is public |
