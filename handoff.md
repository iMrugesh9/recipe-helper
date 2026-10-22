# Session Handoff & Continuity Guide

## 1. Current State
- **Codebase**: Fully functional and verified.
- **Git State**: Local repository initialized on branch `main`. All code and data committed.
- **Bundle**: `personal-ai.bundle` (4.5 MB) created in workspace root containing full repository history.
- **Secrets**: `.env` is properly git-ignored and contains active `GEMINI_API_KEY`.
- **Target Remote**: Personal GitHub repository (to be linked on new machine via SSH).

---

## 2. Setting Up on the New Machine (Linux)

### Step 2.1: Transfer & Unpack
1. Move `personal-ai.bundle` from this machine to your Linux machine (via USB, AirDrop/LocalShare, or Drive).
2. Unpack into your workspace directory:
   ```bash
   git clone /path/to/personal-ai.bundle Personal-Ai
   cd Personal-Ai
   ```

### Step 2.2: Environment Setup
1. Create the `.env` file with your Gemini API key:
   ```bash
   echo "GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>" > .env
   ```
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

### Step 2.3: Link Personal GitHub via SSH (No Password Prompts)
1. Generate an SSH key on Linux (press Enter 3 times for defaults):
   ```bash
   ssh-keygen -t ed25519 -C "personal-recipe-app"
   ```
2. Copy the public key output:
   ```bash
   cat ~/.ssh/id_ed25519.pub
   ```
3. Add it to your personal GitHub account at [github.com/settings/ssh/new](https://github.com/settings/ssh/new).
4. Update the Git remote to use SSH (starts with `git@github.com:`, **not** `https://`):
   ```bash
   git remote set-url origin git@github.com:<YOUR-USERNAME>/<YOUR-REPO-NAME>.git
   ```
5. Push to GitHub:
   ```bash
   git push -u origin main
   ```

### Step 2.4: Enable GitHub Pages
1. Go to your repository on GitHub.com → **Settings** → **Pages**.
2. Under **Build and deployment**:
   - Source: `Deploy from a branch`
   - Branch: `main`
   - Folder: `/docs`
3. Click **Save**.
4. Public site will be live at `https://<YOUR-USERNAME>.github.io/<YOUR-REPO-NAME>/`.

---

## 3. How to Resume the Antigravity Session on the New Machine

### If using Antigravity CLI (`agy`):
1. On your Linux machine, install and authenticate `agy` CLI:
   ```bash
   agy
   ```
2. Start or open the workspace:
   ```bash
   cd Personal-Ai
   agy
   ```
3. In your first prompt to the agent, say:
   > "I am continuing work on the Recipe Helper Agent project. Please read `context.md` and `handoff.md` to get up to speed on the architecture, current state, and next tasks."

### If using Antigravity IDE / Desktop App:
1. Open the cloned `Personal-Ai` directory in Antigravity.
2. In the AI chat pane, send:
   > "Please review `context.md` and `handoff.md` to resume our Recipe Helper Agent development."

---

## 4. How to Run the Local Server
```bash
source .venv/bin/activate
python server.py
```
- Open `http://localhost:8080`.
- Every time you analyze a video or change difficulty, the server automatically updates `docs/` and pushes to GitHub Pages in the background.

---

## 5. Next Feature Roadmap (Ideas for Future Turns)
- [ ] **Shopping List Export**: Check off ingredients and export as a WhatsApp/SMS shareable text or PDF checklist.
- [ ] **Nutrition / Calorie Estimator**: Use Gemini to estimate macros (Protein, Carbs, Fats, Calories per serving).
- [ ] **Instagram Private Reels Support**: Add option to use browser session cookies for private accounts.
- [ ] **Custom Domain**: Point a custom domain to your GitHub Pages site.
