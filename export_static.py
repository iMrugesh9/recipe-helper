#!/usr/bin/env python3
"""
Static Cookbook Generator & GitHub Auto-Sync
============================================
Compiles saved recipes from data/recipes.json into a standalone static site
in the docs/ folder for 100% free hosting on GitHub Pages.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).parent
DATA_FILE = ROOT_DIR / "data" / "recipes.json"
DOCS_DIR = ROOT_DIR / "docs"


def load_recipes() -> list:
    if not DATA_FILE.exists():
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[export] Error loading recipes: {e}")
        return []


def generate_static_site() -> Path:
    """Generate docs/index.html and docs/recipes.json for GitHub Pages."""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    recipes = load_recipes()

    # 1. Save docs/recipes.json
    recipes_json_path = DOCS_DIR / "recipes.json"
    with open(recipes_json_path, "w", encoding="utf-8") as f:
        json.dump(recipes, f, ensure_ascii=False, indent=2)

    # 2. Build standalone docs/index.html
    # We embed the recipes JSON directly so it works anywhere without CORS issues or server dependencies.
    recipes_json_str = json.dumps(recipes, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0" />
  <meta name="theme-color" content="#080b12" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
  <title>Chef AI Cookbook — Extracted Recipes</title>
  <meta name="description" content="Personal AI-extracted recipe cookbook with visual steps, ingredient checklists, and smart filters." />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800;900&family=Playfair+Display:ital,wght@0,700;1,500&display=swap" rel="stylesheet" />
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    img {{ max-width: 100%; height: auto; }}
    :root {{
      --bg:         #080b12;
      --surface:    #0f1420;
      --surface2:   #161c2e;
      --surface3:   #1c2440;
      --border:     rgba(255,255,255,0.07);
      --border2:    rgba(255,255,255,0.12);
      --accent:     #ff6b35;
      --accent2:    #ff9a6c;
      --accent-dim: rgba(255,107,53,0.15);
      --accent-glow:rgba(255,107,53,0.3);
      --green:      #4ade80;
      --blue:       #60a5fa;
      --purple:     #a78bfa;
      --yellow:     #fbbf24;
      --text:       #e2e8f8;
      --text-muted: #6b7a9e;
      --text-dim:   #3a445e;
      --radius:     12px;
      --radius-lg:  20px;
      --radius-xl:  28px;
    }}
    html {{ scroll-behavior: smooth; }}
    body {{
      font-family: 'Outfit', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      -webkit-font-smoothing: antialiased;
      overflow-x: hidden;
    }}
    ::-webkit-scrollbar {{ width: 5px; }}
    ::-webkit-scrollbar-track {{ background: var(--bg); }}
    ::-webkit-scrollbar-thumb {{ background: var(--accent); border-radius: 99px; }}

    .bg-orbs {{ position: fixed; inset: 0; pointer-events: none; z-index: 0; overflow: hidden; }}
    .orb {{ position: absolute; border-radius: 50%; filter: blur(80px); opacity: 0.16; animation: floatOrb 12s ease-in-out infinite alternate; }}
    .orb-1 {{ width: 500px; height: 500px; background: #ff6b35; top: -150px; left: -150px; }}
    .orb-2 {{ width: 400px; height: 400px; background: #a78bfa; top: 40%; right: -120px; animation-delay: -4s; }}
    .orb-3 {{ width: 300px; height: 300px; background: #e1306c; bottom: -80px; left: 30%; animation-delay: -8s; }}
    @keyframes floatOrb {{ from {{ transform: translate(0, 0) scale(1); }} to {{ transform: translate(30px, 20px) scale(1.05); }} }}

    .page {{ position: relative; z-index: 1; max-width: 1200px; margin: 0 auto; padding: 48px 24px 80px; }}

    header {{ text-align: center; margin-bottom: 40px; }}
    .logo-badge {{
      display: inline-flex; align-items: center; gap: 8px;
      background: var(--accent-dim); border: 1px solid rgba(255,107,53,0.25);
      color: var(--accent2); font-size: 12px; font-weight: 700;
      letter-spacing: 0.12em; text-transform: uppercase;
      padding: 6px 16px; border-radius: 99px; margin-bottom: 18px;
    }}
    header h1 {{
      font-family: 'Playfair Display', Georgia, serif;
      font-size: clamp(2.4rem, 5vw, 3.8rem);
      font-weight: 700; line-height: 1.1; margin-bottom: 14px;
      background: linear-gradient(135deg, #ffffff 0%, #ff9a6c 60%, #ff6b35 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    header p {{ font-size: 1.1rem; color: var(--text-muted); font-weight: 300; max-width: 560px; margin: 0 auto 20px; line-height: 1.6; }}

    .stats-bar {{
      display: flex; align-items: center; justify-content: center; gap: 20px; flex-wrap: wrap; margin-bottom: 36px;
    }}
    .stat-pill {{
      display: inline-flex; align-items: center; gap: 8px;
      background: var(--surface2); border: 1px solid var(--border);
      padding: 6px 16px; border-radius: 99px; font-size: 13px; font-weight: 600; color: var(--text);
    }}

    /* Filter Panel */
    .filter-panel {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius-lg); padding: 22px 24px; margin-bottom: 32px;
      box-shadow: 0 12px 40px rgba(0,0,0,0.3);
    }}
    .filter-search-wrap {{ position: relative; margin-bottom: 18px; }}
    .filter-search-input {{
      width: 100%; background: var(--surface2); border: 1px solid var(--border2);
      border-radius: var(--radius); padding: 13px 18px 13px 44px;
      font-family: 'Outfit', sans-serif; font-size: 15px; color: var(--text); outline: none;
      transition: all 0.2s ease;
    }}
    .filter-search-input:focus {{ border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-dim); }}
    .filter-search-icon {{ position: absolute; left: 16px; top: 50%; transform: translateY(-50%); opacity: 0.5; font-size: 16px; }}

    /* Category Quick Filter Pills */
    .type-pill-bar {{
      display: flex; gap: 8px; overflow-x: auto; padding: 2px 2px 14px;
      scrollbar-width: none; -ms-overflow-style: none; margin-bottom: 14px;
    }}
    .type-pill-bar::-webkit-scrollbar {{ display: none; }}
    .type-pill {{
      display: inline-flex; align-items: center; gap: 6px; white-space: nowrap;
      background: var(--surface2); border: 1px solid var(--border); color: var(--text-muted);
      padding: 8px 15px; border-radius: 99px; font-size: 12.5px; font-weight: 600;
      cursor: pointer; transition: all 0.2s ease;
    }}
    .type-pill:hover {{ color: var(--text); border-color: var(--accent); background: var(--surface3); }}
    .type-pill.active {{ background: var(--accent); color: #fff; border-color: var(--accent); box-shadow: 0 4px 14px var(--accent-glow); }}
    .type-overlay-badge {{
      background: rgba(8,11,18,0.75); border: 1px solid rgba(255,255,255,0.18);
      font-size: 11px; padding: 3px 9px; border-radius: 99px; color: var(--accent2); font-weight: 600;
      backdrop-filter: blur(8px);
    }}
    .type-chip {{
      background: var(--accent-dim) !important; color: var(--accent2) !important;
      border-color: rgba(255,107,53,0.3) !important; font-weight: 600 !important;
    }}

    .filter-grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px;
    }}
    .filter-group {{ display: flex; flex-direction: column; gap: 6px; }}
    .filter-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); font-weight: 700; }}
    .filter-select {{
      background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius);
      padding: 10px 14px; font-family: 'Outfit', sans-serif; font-size: 13px; font-weight: 600;
      color: var(--text); outline: none; cursor: pointer; transition: border-color 0.2s;
    }}
    .filter-select:focus {{ border-color: var(--accent); }}
    .btn-reset-filters {{
      align-self: flex-end; padding: 10px 16px; border-radius: var(--radius);
      background: var(--surface3); border: 1px solid var(--border2); color: var(--text-muted);
      font-size: 13px; font-weight: 600; cursor: pointer; transition: all 0.2s;
    }}
    .btn-reset-filters:hover {{ background: var(--accent-dim); color: var(--accent2); border-color: var(--accent); }}

    /* Cards Grid */
    .recipes-grid {{
      display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr)); gap: 24px;
    }}
    .recipe-card {{
      background: var(--surface); border: 1px solid var(--border);
      border-radius: var(--radius-lg); overflow: hidden; display: flex; flex-direction: column;
      transition: transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease;
    }}
    .recipe-card:hover {{
      transform: translateY(-4px); box-shadow: 0 16px 40px rgba(0,0,0,0.5);
      border-color: rgba(255,107,53,0.35);
    }}
    .card-thumb-wrap {{
      position: relative; width: 100%; aspect-ratio: 16/9; background: #111827; overflow: hidden;
    }}
    .card-thumb {{ width: 100%; height: 100%; object-fit: cover; transition: transform 0.4s ease; }}
    .recipe-card:hover .card-thumb {{ transform: scale(1.04); }}
    .card-overlay {{
      position: absolute; inset: 0; padding: 12px;
      display: flex; align-items: flex-start; justify-content: space-between;
      background: linear-gradient(180deg, rgba(0,0,0,0.65) 0%, transparent 40%, rgba(0,0,0,0.7) 100%);
    }}
    .diff-badge {{
      font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em;
      padding: 4px 10px; border-radius: 99px; backdrop-filter: blur(8px);
    }}
    .diff-easy   {{ background: rgba(74,222,128,0.25); border: 1px solid rgba(74,222,128,0.45); color: #86efac; }}
    .diff-medium {{ background: rgba(251,191,36,0.25); border: 1px solid rgba(251,191,36,0.45); color: #fde68a; }}
    .diff-hard   {{ background: rgba(255,107,53,0.25); border: 1px solid rgba(255,107,53,0.45); color: #fdba74; }}
    .source-badge {{
      background: rgba(8,11,18,0.75); border: 1px solid rgba(255,255,255,0.18);
      font-size: 11px; padding: 3px 9px; border-radius: 99px; color: white; font-weight: 600;
    }}

    .card-body {{ padding: 18px 20px; display: flex; flex-direction: column; flex: 1; }}
    .card-title {{
      font-family: 'Playfair Display', Georgia, serif; font-size: 1.25rem; font-weight: 700;
      color: var(--text); line-height: 1.3; margin-bottom: 10px;
    }}
    .card-chips {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }}
    .card-chip {{
      font-size: 11px; background: var(--surface2); border: 1px solid var(--border);
      padding: 3px 8px; border-radius: 6px; color: var(--text-muted); font-weight: 500;
    }}
    .card-desc {{
      font-size: 13px; color: var(--text-muted); line-height: 1.5; margin-bottom: 16px;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
    }}
    .card-stats {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 12px;
      color: var(--text-muted); background: var(--surface2); padding: 10px 12px;
      border-radius: var(--radius); margin-bottom: 16px;
    }}
    .card-stats b {{ color: var(--text); font-weight: 600; }}
    .card-footer {{ margin-top: auto; display: flex; align-items: center; gap: 8px; }}
    .btn-view {{
      flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 8px;
      padding: 10px 16px; border-radius: var(--radius); background: var(--accent);
      color: #fff; font-size: 13px; font-weight: 700; border: none; cursor: pointer;
      text-decoration: none; transition: all 0.2s;
    }}
    .btn-view:hover {{ background: #ff5722; transform: translateY(-1px); }}
    .btn-orig {{
      padding: 10px 14px; border-radius: var(--radius); background: var(--surface2);
      border: 1px solid var(--border); color: var(--text-muted); font-size: 13px;
      text-decoration: none; display: inline-flex; align-items: center; transition: all 0.2s;
    }}
    .btn-orig:hover {{ color: var(--text); background: var(--surface3); }}

    /* Detailed View Modal / Overlay */
    .detail-overlay {{
      display: none; position: fixed; inset: 0; background: rgba(4,6,10,0.88);
      backdrop-filter: blur(16px); z-index: 1000; overflow-y: auto; padding: 40px 20px 80px;
    }}
    .detail-overlay.active {{ display: block; }}
    .detail-container {{
      max-width: 900px; margin: 0 auto; background: var(--surface); border: 1px solid var(--border2);
      border-radius: var(--radius-xl); overflow: hidden; box-shadow: 0 24px 80px rgba(0,0,0,0.7);
    }}
    .detail-hero {{
      position: relative; width: 100%; min-height: 280px; background-size: cover;
      background-position: center; display: flex; align-items: flex-end; padding: 32px 36px;
    }}
    .detail-hero-overlay {{
      position: absolute; inset: 0;
      background: linear-gradient(180deg, rgba(8,11,18,0.2) 0%, rgba(15,20,32,0.95) 100%);
    }}
    .detail-hero-content {{ position: relative; z-index: 1; }}
    .detail-title {{
      font-family: 'Playfair Display', Georgia, serif; font-size: clamp(1.8rem, 4vw, 2.8rem);
      font-weight: 700; line-height: 1.15; margin-bottom: 12px; color: #fff;
    }}
    .detail-desc {{ font-size: 1rem; color: var(--text-muted); line-height: 1.6; max-width: 680px; margin-bottom: 18px; }}
    .detail-chips {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .meta-chip {{
      display: inline-flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.08);
      border: 1px solid rgba(255,255,255,0.12); padding: 5px 12px; border-radius: 99px;
      font-size: 12px; font-weight: 600;
    }}
    .btn-close-detail {{
      position: sticky; top: 18px; float: right; margin-right: 18px; z-index: 10;
      background: var(--surface2); border: 1px solid var(--border2); color: var(--text);
      padding: 8px 16px; border-radius: 99px; font-size: 13px; font-weight: 600;
      cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.4);
    }}
    .btn-close-detail:hover {{ background: var(--accent); color: #fff; }}

    .detail-body {{ padding: 36px; }}
    .section-title {{
      font-family: 'Playfair Display', Georgia, serif; font-size: 1.4rem; font-weight: 700;
      color: var(--text); margin-bottom: 16px; display: flex; align-items: center; gap: 10px;
    }}
    .section-box {{
      background: var(--surface2); border: 1px solid var(--border);
      border-radius: var(--radius); padding: 20px; margin-bottom: 28px;
    }}

    /* Ingredients checklist */
    .ing-list {{ list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; }}
    .ing-item {{
      display: flex; align-items: center; gap: 10px; padding: 10px 14px;
      background: var(--surface3); border: 1px solid var(--border); border-radius: var(--radius);
      cursor: pointer; user-select: none; transition: all 0.15s ease;
    }}
    .ing-item.checked {{ opacity: 0.5; text-decoration: line-through; }}
    .ing-check {{
      width: 18px; height: 18px; border-radius: 4px; border: 1px solid var(--border2);
      display: flex; align-items: center; justify-content: center; font-size: 12px; color: var(--green);
    }}
    .ing-item.checked .ing-check {{ background: rgba(74,222,128,0.2); border-color: var(--green); }}
    .ing-thumb {{ width: 34px; height: 34px; border-radius: 6px; object-fit: cover; }}
    .ing-name {{ font-size: 14px; font-weight: 600; color: var(--text); }}
    .ing-qty {{ font-size: 12px; color: var(--accent2); font-weight: 500; }}

    /* Prep Gallery */
    .prep-gallery {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin-top: 14px; }}
    .prep-card {{
      position: relative; border-radius: var(--radius); overflow: hidden; cursor: pointer; aspect-ratio: 4/3;
      border: 1px solid var(--border2);
    }}
    .prep-card img {{ width: 100%; height: 100%; object-fit: cover; transition: transform 0.3s; }}
    .prep-card:hover img {{ transform: scale(1.06); }}
    .prep-card-label {{
      position: absolute; bottom: 0; inset-inline: 0; padding: 6px 10px;
      background: linear-gradient(180deg, transparent, rgba(0,0,0,0.85)); font-size: 11px; font-weight: 600;
    }}

    /* Steps */
    .steps-list {{ list-style: none; display: flex; flex-direction: column; gap: 20px; }}
    .step-item {{ display: flex; gap: 18px; }}
    .step-num {{
      width: 32px; height: 32px; border-radius: 50%; background: var(--accent); color: #fff;
      display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 14px; flex-shrink: 0;
    }}
    .step-content {{ flex: 1; }}
    .step-title {{ font-size: 16px; font-weight: 700; color: var(--text); margin-bottom: 6px; }}
    .step-instruction {{ font-size: 14px; color: var(--text-muted); line-height: 1.6; margin-bottom: 12px; }}
    .step-img-wrap {{
      max-width: 440px; border-radius: var(--radius); overflow: hidden; border: 1px solid var(--border2); cursor: pointer;
    }}
    .step-img-wrap img {{ width: 100%; display: block; }}

    /* Lightbox */
    .lightbox-modal {{
      display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.92);
      z-index: 2000; align-items: center; justify-content: center; flex-direction: column; padding: 24px;
    }}
    .lightbox-modal.active {{ display: flex; }}
    .lightbox-img {{ max-width: 90vw; max-height: 80vh; border-radius: var(--radius); object-fit: contain; }}
    .lightbox-caption {{ margin-top: 14px; font-size: 14px; color: var(--text); font-weight: 600; }}

    /* Empty state */
    .empty-state {{ text-align: center; padding: 60px 20px; color: var(--text-muted); }}
    .empty-icon {{ font-size: 48px; margin-bottom: 14px; }}

    /* ── Mobile & Responsive Breakpoints ────────────────────────── */
    @media (max-width: 900px) {{
      .page {{ padding: 32px 18px 70px; }}
      .detail-body {{ padding: 26px 20px; }}
    }}

    @media (max-width: 680px) {{
      .page {{ padding: 20px 14px 60px; }}
      header {{ margin-bottom: 22px; }}
      .logo-badge {{ font-size: 11px; padding: 5px 12px; margin-bottom: 12px; }}
      header h1 {{ font-size: 2.1rem; margin-bottom: 10px; }}
      header p {{ font-size: 0.95rem; line-height: 1.5; margin-bottom: 16px; }}
      .stats-bar {{ gap: 8px; margin-bottom: 20px; }}
      .stat-pill {{ font-size: 11px; padding: 5px 12px; }}

      /* Filter Panel Mobile */
      .filter-panel {{ padding: 16px 14px; margin-bottom: 20px; border-radius: var(--radius); }}
      .filter-search-input {{ font-size: 14px; padding: 11px 14px 11px 38px; }}
      .filter-search-icon {{ left: 12px; font-size: 14px; }}
      .filter-grid {{ grid-template-columns: 1fr 1fr; gap: 8px; }}
      .filter-select {{ font-size: 12px; padding: 8px 10px; }}
      .btn-reset-filters {{ grid-column: 1 / -1; width: 100%; text-align: center; padding: 10px; font-size: 12px; }}

      /* Recipes Grid Mobile */
      .recipes-grid {{ grid-template-columns: 1fr; gap: 16px; }}
      .recipe-card {{ border-radius: var(--radius); }}
      .card-body {{ padding: 14px 14px; }}
      .card-title {{ font-size: 1.2rem; }}
      .card-stats {{ font-size: 11.5px; padding: 8px 10px; }}
      .btn-view {{ min-height: 44px; font-size: 13.5px; }}
      .btn-orig {{ min-height: 44px; padding: 10px 16px; font-size: 14px; }}

      /* Detail Modal Mobile: Full Screen */
      .detail-overlay {{
        padding: 0;
        background: var(--bg);
      }}
      .detail-container {{
        border-radius: 0;
        border: none;
        min-height: 100vh;
        box-shadow: none;
      }}
      .btn-close-detail {{
        position: fixed;
        top: 12px;
        right: 12px;
        margin: 0;
        z-index: 1200;
        padding: 8px 14px;
        font-size: 12px;
        background: rgba(15,20,32,0.92);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,0.2);
        box-shadow: 0 4px 16px rgba(0,0,0,0.6);
      }}
      .detail-hero {{ min-height: 200px; padding: 24px 16px; }}
      .detail-title {{ font-size: 1.65rem; }}
      .detail-desc {{ font-size: 0.92rem; line-height: 1.5; }}
      .detail-chips {{ gap: 6px; }}
      .meta-chip {{ font-size: 11px; padding: 4px 10px; }}
      .detail-body {{ padding: 18px 14px 60px; }}
      .section-box {{ padding: 14px 12px; border-radius: var(--radius); margin-bottom: 18px; }}
      .section-title {{ font-size: 1.15rem; }}

      /* Single column ingredients for easy checklist tapping */
      .ing-list {{ grid-template-columns: 1fr; gap: 8px; }}
      .ing-item {{ padding: 10px 12px; min-height: 44px; }}
      .ing-name {{ font-size: 13.5px; }}

      /* Prep gallery: 2 columns on mobile */
      .prep-gallery {{ grid-template-columns: repeat(2, 1fr); gap: 8px; }}
      .prep-card-label {{ font-size: 10px; padding: 4px 6px; }}

      /* Steps mobile */
      .steps-list {{ gap: 16px; }}
      .step-item {{ gap: 10px; }}
      .step-num {{ width: 26px; height: 26px; font-size: 12px; }}
      .step-title {{ font-size: 14.5px; }}
      .step-instruction {{ font-size: 13px; line-height: 1.5; }}
      .step-img-wrap {{ width: 100%; max-width: 100%; }}

      /* Lightbox mobile */
      .lightbox-modal {{ padding: 10px; }}
      .lightbox-img {{ max-width: 95vw; max-height: 75vh; }}
    }}

    @media (max-width: 380px) {{
      .filter-grid {{ grid-template-columns: 1fr; }}
      .detail-title {{ font-size: 1.4rem; }}
      .card-stats {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="bg-orbs">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="orb orb-3"></div>
  </div>

  <div class="page">
    <header>
      <div class="logo-badge">🍽️ Chef AI Public Cookbook</div>
      <h1>Curated Recipe Collection</h1>
      <p>Hand-crafted and AI-extracted recipes from Instagram Reels and YouTube Shorts with visual steps, prep milestones, and precision ingredient lists.</p>

      <div class="stats-bar">
        <div class="stat-pill">📖 <span id="statCount">0</span> Recipes</div>
        <div class="stat-pill">⚡ Auto-Synced from Local AI</div>
        <div class="stat-pill">📱 Mobile & Offline Friendly</div>
      </div>
    </header>

    <!-- Filters -->
    <div class="filter-panel">
      <!-- Quick Category Pills -->
      <div class="type-pill-bar" id="typePillBar">
        <button class="type-pill active" onclick="setTypeFilter('all', this)">✨ All (<span id="typeCountAll">0</span>)</button>
        <button class="type-pill" onclick="setTypeFilter('Main Course', this)">🍲 Main Course (<span id="typeCountMain">0</span>)</button>
        <button class="type-pill" onclick="setTypeFilter('High Protein', this)">💪 High Protein (<span id="typeCountProtein">0</span>)</button>
        <button class="type-pill" onclick="setTypeFilter('Snack', this)">🥪 Snacks (<span id="typeCountSnack">0</span>)</button>
        <button class="type-pill" onclick="setTypeFilter('Breakfast', this)">🌅 Breakfast (<span id="typeCountBreakfast">0</span>)</button>
        <button class="type-pill" onclick="setTypeFilter('Dessert', this)">🍰 Desserts (<span id="typeCountDessert">0</span>)</button>
        <button class="type-pill" onclick="setTypeFilter('Salad', this)">🥗 Salads (<span id="typeCountSalad">0</span>)</button>
        <button class="type-pill" onclick="setTypeFilter('Drink', this)">🥤 Drinks (<span id="typeCountDrink">0</span>)</button>
      </div>

      <div class="filter-search-wrap">
        <span class="filter-search-icon">🔍</span>
        <input type="text" id="searchInput" class="filter-search-input" placeholder="Search by recipe name, ingredient, tool, cuisine, or category..." />
      </div>

      <div class="filter-grid">
        <div class="filter-group">
          <label class="filter-label">Type of Recipe</label>
          <select id="filterRecipeType" class="filter-select" onchange="onTypeSelectChange(this.value)">
            <option value="all">All Recipe Types</option>
            <option value="Main Course">🍲 Main Course</option>
            <option value="High Protein">💪 High Protein</option>
            <option value="Snack">🥪 Snack & Appetizer</option>
            <option value="Breakfast">🌅 Breakfast</option>
            <option value="Dessert">🍰 Dessert & Sweets</option>
            <option value="Salad">🥗 Salad & Bowls</option>
            <option value="Drink">🥤 Drink & Beverage</option>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">Difficulty</label>
          <select id="filterDifficulty" class="filter-select">
            <option value="all">All Difficulties</option>
            <option value="Easy">⭐ Easy</option>
            <option value="Medium">⭐⭐ Medium</option>
            <option value="Hard">⭐⭐⭐ Hard</option>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">Max Cook Time</label>
          <select id="filterCookTime" class="filter-select">
            <option value="all">Any Cook Time</option>
            <option value="15">≤ 15 mins</option>
            <option value="30">≤ 30 mins</option>
            <option value="45">≤ 45 mins</option>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">Max Prep Time</label>
          <select id="filterPrepTime" class="filter-select">
            <option value="all">Any Prep Time</option>
            <option value="10">≤ 10 mins</option>
            <option value="20">≤ 20 mins</option>
            <option value="30">≤ 30 mins</option>
          </select>
        </div>

        <div class="filter-group">
          <label class="filter-label">Sort By</label>
          <select id="filterSort" class="filter-select">
            <option value="newest">✨ Newest First</option>
            <option value="fastest">⚡ Fastest Total Time</option>
            <option value="fewest">🥕 Fewest Ingredients</option>
            <option value="name">🔤 Recipe Name</option>
          </select>
        </div>

        <button class="btn-reset-filters" onclick="resetFilters()">✕ Reset</button>
      </div>
    </div>

    <!-- Grid -->
    <div class="recipes-grid" id="recipesGrid"></div>
  </div>

  <!-- Detailed Modal -->
  <div class="detail-overlay" id="detailOverlay" onclick="if(event.target===this) closeDetail()">
    <button class="btn-close-detail" onclick="closeDetail()">✕ Back to Recipes</button>
    <div class="detail-container" id="detailContainer"></div>
  </div>

  <!-- Lightbox -->
  <div class="lightbox-modal" id="lightboxModal" onclick="closeLightbox()">
    <img class="lightbox-img" id="lightboxImg" alt="Enlarged" onclick="event.stopPropagation()" />
    <div class="lightbox-caption" id="lightboxCaption"></div>
  </div>

  <!-- Embedded Data -->
  <script id="recipesData" type="application/json">
{recipes_json_str}
  </script>

  <script>
    let allRecipes = [];
    let currentTypeFilter = 'all';

    function getTypeEmoji(t) {{
      const s = (t || '').toLowerCase();
      if (s.includes('protein')) return '💪';
      if (s.includes('snack')) return '🥪';
      if (s.includes('breakfast')) return '🌅';
      if (s.includes('dessert') || s.includes('sweet')) return '🍰';
      if (s.includes('salad')) return '🥗';
      if (s.includes('drink') || s.includes('smoothie')) return '🥤';
      if (s.includes('quick')) return '⚡';
      return '🍲';
    }}

    function setTypeFilter(type, btn) {{
      currentTypeFilter = type;
      const select = document.getElementById('filterRecipeType');
      if (select) select.value = type;
      document.querySelectorAll('.type-pill').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      applyFilters();
    }}

    function onTypeSelectChange(val) {{
      currentTypeFilter = val;
      document.querySelectorAll('.type-pill').forEach(b => {{
        const txt = b.getAttribute('onclick') || '';
        if (txt.includes(`'${{val}}'`) || (val === 'all' && txt.includes("'all'"))) {{
          b.classList.add('active');
        }} else {{
          b.classList.remove('active');
        }}
      }});
      applyFilters();
    }}

    // Load recipes: first from embedded script, fallback to fetch
    function initData() {{
      try {{
        const el = document.getElementById('recipesData');
        if (el && el.textContent.trim()) {{
          allRecipes = JSON.parse(el.textContent.trim());
        }}
      }} catch (e) {{
        console.warn('Embedded data parse error, trying fetch:', e);
      }}

      if (!allRecipes || allRecipes.length === 0) {{
        fetch('./recipes.json')
          .then(res => res.json())
          .then(data => {{
            allRecipes = data || [];
            updateStats();
            applyFilters();
            checkHashRoute();
          }})
          .catch(err => {{
            console.error('Failed to fetch recipes.json:', err);
            renderGrid([]);
          }});
      }} else {{
        updateStats();
        applyFilters();
        checkHashRoute();
      }}
    }}

    function updateStats() {{
      const countEl = document.getElementById('statCount');
      if (countEl) countEl.textContent = allRecipes.length;

      const counts = {{
        all: allRecipes.length,
        'Main Course': 0,
        'High Protein': 0,
        'Snack': 0,
        'Breakfast': 0,
        'Dessert': 0,
        'Salad': 0,
        'Drink': 0
      }};

      allRecipes.forEach(item => {{
        const t = item.recipe?.recipe_type || 'Main Course';
        if (counts[t] !== undefined) counts[t]++;
      }});

      if (document.getElementById('typeCountAll')) document.getElementById('typeCountAll').textContent = counts.all;
      if (document.getElementById('typeCountMain')) document.getElementById('typeCountMain').textContent = counts['Main Course'];
      if (document.getElementById('typeCountProtein')) document.getElementById('typeCountProtein').textContent = counts['High Protein'];
      if (document.getElementById('typeCountSnack')) document.getElementById('typeCountSnack').textContent = counts['Snack'];
      if (document.getElementById('typeCountBreakfast')) document.getElementById('typeCountBreakfast').textContent = counts['Breakfast'];
      if (document.getElementById('typeCountDessert')) document.getElementById('typeCountDessert').textContent = counts['Dessert'];
      if (document.getElementById('typeCountSalad')) document.getElementById('typeCountSalad').textContent = counts['Salad'];
      if (document.getElementById('typeCountDrink')) document.getElementById('typeCountDrink').textContent = counts['Drink'];
    }}

    function parseMinutes(str) {{
      if (!str || typeof str !== 'string') return 0;
      const m = str.match(/(\\d+)/);
      return m ? parseInt(m[1], 10) : 0;
    }}

    function escHtml(str) {{
      const d = document.createElement('div');
      d.appendChild(document.createTextNode(str || ''));
      return d.innerHTML;
    }}

    function applyFilters() {{
      const search = (document.getElementById('searchInput').value || '').toLowerCase().trim();
      const diff = document.getElementById('filterDifficulty').value;
      const recipeType = (document.getElementById('filterRecipeType')?.value || currentTypeFilter || 'all').toLowerCase();
      const maxCook = document.getElementById('filterCookTime').value;
      const maxPrep = document.getElementById('filterPrepTime').value;
      const sort = document.getElementById('filterSort').value;

      let filtered = allRecipes.filter(item => {{
        const r = item.recipe || {{}};
        if (search) {{
          const haystack = [
            r.recipe_name, r.description, r.cuisine_type, r.recipe_type,
            ...(r.ingredients || []).map(i => i.name),
            ...(r.tools || []).map(t => t.name)
          ].join(' ').toLowerCase();
          if (!haystack.includes(search)) return false;
        }}

        if (recipeType !== 'all') {{
          const rType = (r.recipe_type || 'Main Course').toLowerCase();
          if (rType !== recipeType) return false;
        }}

        if (diff !== 'all' && (r.difficulty || '').toLowerCase() !== diff.toLowerCase()) {{
          return false;
        }}

        if (maxCook !== 'all') {{
          const cookM = parseMinutes(r.cook_time);
          if (cookM > parseInt(maxCook, 10)) return false;
        }}

        if (maxPrep !== 'all') {{
          const prepM = parseMinutes(r.prep_time);
          if (prepM > parseInt(maxPrep, 10)) return false;
        }}

        return true;
      }});

      // Sort
      if (sort === 'fastest') {{
        filtered.sort((a, b) => {{
          const tA = parseMinutes(a.recipe?.prep_time) + parseMinutes(a.recipe?.cook_time);
          const tB = parseMinutes(b.recipe?.prep_time) + parseMinutes(b.recipe?.cook_time);
          return (tA || 999) - (tB || 999);
        }});
      }} else if (sort === 'fewest') {{
        filtered.sort((a, b) => (a.recipe?.ingredients?.length || 0) - (b.recipe?.ingredients?.length || 0));
      }} else if (sort === 'name') {{
        filtered.sort((a, b) => (a.recipe?.recipe_name || '').localeCompare(b.recipe?.recipe_name || ''));
      }}

      renderGrid(filtered);
    }}

    function renderGrid(recipes) {{
      const grid = document.getElementById('recipesGrid');
      if (!grid) return;
      grid.innerHTML = '';

      if (recipes.length === 0) {{
        grid.innerHTML = `
          <div class="empty-state" style="grid-column: 1 / -1;">
            <div class="empty-icon">🔍</div>
            <h3>No recipes match your criteria</h3>
            <p>Try clearing your search or resetting filters.</p>
          </div>
        `;
        return;
      }}

      recipes.forEach(item => {{
        const r = item.recipe || {{}};
        const diff = (r.difficulty || 'Easy').toLowerCase();
        const diffClass = 'diff-' + (diff === 'medium' ? 'medium' : diff === 'hard' ? 'hard' : 'easy');
        const isIg = (item.source_url || '').includes('instagram.com');

        let thumb = item.thumbnail_url || '';
        if (!thumb && r.steps && r.steps[0]?.image) thumb = r.steps[0].image;

        const card = document.createElement('div');
        card.className = 'recipe-card';
        card.innerHTML = `
          <div class="card-thumb-wrap">
            ${{thumb ? `<img src="${{thumb}}" alt="${{escHtml(r.recipe_name)}}" class="card-thumb" loading="lazy" />` : ''}}
            <div class="card-overlay">
              <span class="diff-badge ${{diffClass}}">⭐ ${{escHtml(r.difficulty || 'Easy')}}</span>
              <div style="display:flex; align-items:center; gap:6px;">
                ${{r.recipe_type ? `<span class="type-overlay-badge">${{getTypeEmoji(r.recipe_type)}} ${{escHtml(r.recipe_type)}}</span>` : ''}}
                <span class="source-badge">${{isIg ? '📸 Reel' : '▶️ Short'}}</span>
              </div>
            </div>
          </div>
          <div class="card-body">
            <h3 class="card-title">${{escHtml(r.recipe_name || 'Untitled Recipe')}}</h3>
            <div class="card-chips">
              ${{r.recipe_type ? `<span class="card-chip type-chip">${{getTypeEmoji(r.recipe_type)}} ${{escHtml(r.recipe_type)}}</span>` : ''}}
              ${{r.cuisine_type ? `<span class="card-chip">🌍 ${{escHtml(r.cuisine_type)}}</span>` : ''}}
              ${{r.servings ? `<span class="card-chip">👥 ${{escHtml(r.servings)}}</span>` : ''}}
              ${{r.cook_time ? `<span class="card-chip">🔥 ${{escHtml(r.cook_time)}}</span>` : ''}}
            </div>
            <p class="card-desc">${{escHtml(r.description || '')}}</p>
            <div class="card-stats">
              <div>⏱️ Prep: <b>${{escHtml(r.prep_time || '—')}}</b></div>
              <div>🔥 Cook: <b>${{escHtml(r.cook_time || '—')}}</b></div>
              <div>🥕 <b>${{(r.ingredients || []).length}} ingredients</b></div>
              <div>📋 <b>${{(r.steps || []).length}} steps</b></div>
            </div>
            <div class="card-footer">
              <button class="btn-view" onclick="openDetail('${{item.id}}')">View Recipe ➔</button>
              ${{item.source_url ? `<a href="${{item.source_url}}" target="_blank" rel="noopener" class="btn-orig" title="Watch Original Video">▶</a>` : ''}}
            </div>
          </div>
        `;
        grid.appendChild(card);
      }});
    }}

    function resetFilters() {{
      document.getElementById('searchInput').value = '';
      document.getElementById('filterDifficulty').value = 'all';
      if (document.getElementById('filterRecipeType')) document.getElementById('filterRecipeType').value = 'all';
      document.getElementById('filterCookTime').value = 'all';
      document.getElementById('filterPrepTime').value = 'all';
      document.getElementById('filterSort').value = 'newest';
      currentTypeFilter = 'all';
      document.querySelectorAll('.type-pill').forEach((b, i) => {{
        if (i === 0) b.classList.add('active');
        else b.classList.remove('active');
      }});
      applyFilters();
    }}

    function openDetail(recipeId) {{
      const item = allRecipes.find(r => r.id === recipeId);
      if (!item) return;

      const r = item.recipe || {{}};
      const container = document.getElementById('detailContainer');
      const diff = (r.difficulty || 'Easy').toLowerCase();
      const diffClass = 'diff-' + (diff === 'medium' ? 'medium' : diff === 'hard' ? 'hard' : 'easy');

      window.location.hash = recipeId;

      container.innerHTML = `
        <div class="detail-hero" style="${{item.thumbnail_url ? `background-image: url('${{item.thumbnail_url}}')` : ''}}">
          <div class="detail-hero-overlay"></div>
          <div class="detail-hero-content">
            <div class="meta-chip diff-badge ${{diffClass}}" style="margin-bottom:12px;">⭐ ${{escHtml(r.difficulty || 'Easy')}}</div>
            <h2 class="detail-title">${{escHtml(r.recipe_name || 'Recipe')}}</h2>
            <p class="detail-desc">${{escHtml(r.description || '')}}</p>
            <div class="detail-chips">
              ${{r.recipe_type ? `<span class="meta-chip" style="background:var(--accent-dim); border-color:var(--accent); color:var(--accent2);">${{getTypeEmoji(r.recipe_type)}} ${{escHtml(r.recipe_type)}}</span>` : ''}}
              ${{r.cuisine_type ? `<span class="meta-chip">🌍 ${{escHtml(r.cuisine_type)}}</span>` : ''}}
              ${{r.servings ? `<span class="meta-chip">👥 ${{escHtml(r.servings)}}</span>` : ''}}
              ${{r.prep_time ? `<span class="meta-chip">⏱️ Prep: ${{escHtml(r.prep_time)}}</span>` : ''}}
              ${{r.cook_time ? `<span class="meta-chip">🔥 Cook: ${{escHtml(r.cook_time)}}</span>` : ''}}
              ${{item.source_url ? `<a href="${{item.source_url}}" target="_blank" rel="noopener" class="meta-chip" style="color:var(--accent2); text-decoration:none;">▶ Watch Original Video</a>` : ''}}
            </div>
          </div>
        </div>

        <div class="detail-body">
          <!-- Ingredients -->
          <div class="section-box">
            <h3 class="section-title">🧾 Ingredients (${{(r.ingredients || []).length}})</h3>
            <ul class="ing-list">
              ${{(r.ingredients || []).map(ing => `
                <li class="ing-item" onclick="this.classList.toggle('checked')">
                  <div class="ing-check">✓</div>
                  ${{ing.image ? `<img src="${{ing.image}}" class="ing-thumb" alt="${{escHtml(ing.name)}}" onclick="event.stopPropagation(); openLightbox('${{ing.image}}', '${{escHtml(ing.name)}}')" />` : ''}}
                  <div>
                    <div class="ing-name">${{escHtml(ing.name)}}</div>
                    ${{ing.quantity ? `<div class="ing-qty">${{escHtml(ing.quantity)}}</div>` : ''}}
                  </div>
                </li>
              `).join('')}}
            </ul>

            ${{(r.ingredient_snapshots || []).length > 0 ? `
              <div style="margin-top:20px;">
                <h4 style="font-size:13px; color:var(--text-muted); text-transform:uppercase; margin-bottom:10px;">📸 Preparation Gallery</h4>
                <div class="prep-gallery">
                  ${{(r.ingredient_snapshots || []).map(s => `
                    <div class="prep-card" onclick="openLightbox('${{s.image}}', '${{escHtml(s.label)}}')">
                      <img src="${{s.image}}" alt="${{escHtml(s.label)}}" loading="lazy" />
                      <div class="prep-card-label">${{escHtml(s.label)}} (${{escHtml(s.time)}})</div>
                    </div>
                  `).join('')}}
                </div>
              </div>
            ` : ''}}
          </div>

          <!-- Tools -->
          ${{(r.tools || []).length > 0 ? `
            <div class="section-box">
              <h3 class="section-title">🛠️ Tools & Equipment</h3>
              <div style="display:flex; flex-wrap:wrap; gap:8px;">
                ${{(r.tools || []).map(t => `
                  <span class="meta-chip">🔧 ${{escHtml(t.name)}}${{t.purpose ? ` (${{escHtml(t.purpose)}})` : ''}}</span>
                `).join('')}}
              </div>
            </div>
          ` : ''}}

          <!-- Steps -->
          <div class="section-box">
            <h3 class="section-title">👨‍🍳 Step-by-Step Instructions</h3>
            <ul class="steps-list">
              ${{(r.steps || []).map(s => `
                <li class="step-item">
                  <div class="step-num">${{s.step_number}}</div>
                  <div class="step-content">
                    <div class="step-title">${{escHtml(s.title || `Step ${{s.step_number}}`)}}</div>
                    <div class="step-instruction">${{escHtml(s.instruction)}}</div>
                    ${{s.image ? `
                      <div class="step-img-wrap" onclick="openLightbox('${{s.image}}', 'Step ${{s.step_number}}: ${{escHtml(s.title || '')}}')">
                        <img src="${{s.image}}" alt="Step ${{s.step_number}}" loading="lazy" />
                      </div>
                    ` : ''}}
                  </div>
                </li>
              `).join('')}}
            </ul>
          </div>

          <!-- Tips -->
          ${{(r.tips || []).length > 0 ? `
            <div class="section-box">
              <h3 class="section-title">💡 Chef's Tips</h3>
              <ul style="padding-left:20px; line-height:1.7; color:var(--text-muted);">
                ${{(r.tips || []).map(tip => `<li>${{escHtml(tip)}}</li>`).join('')}}
              </ul>
            </div>
          ` : ''}}
        </div>
      `;

      document.getElementById('detailOverlay').classList.add('active');
      document.body.style.overflow = 'hidden';
    }}

    function closeDetail() {{
      document.getElementById('detailOverlay').classList.remove('active');
      document.body.style.overflow = '';
      history.replaceState(null, null, ' ');
    }}

    function checkHashRoute() {{
      const hash = window.location.hash.replace('#', '');
      if (hash) {{
        openDetail(hash);
      }}
    }}

    function openLightbox(src, caption) {{
      const modal = document.getElementById('lightboxModal');
      document.getElementById('lightboxImg').src = src;
      document.getElementById('lightboxCaption').textContent = caption || '';
      modal.classList.add('active');
    }}

    function closeLightbox() {{
      document.getElementById('lightboxModal').classList.remove('active');
    }}

    // Event listeners
    document.getElementById('searchInput').addEventListener('input', applyFilters);
    document.getElementById('filterDifficulty').addEventListener('change', applyFilters);
    document.getElementById('filterCookTime').addEventListener('change', applyFilters);
    document.getElementById('filterPrepTime').addEventListener('change', applyFilters);
    document.getElementById('filterSort').addEventListener('change', applyFilters);
    window.addEventListener('hashchange', checkHashRoute);

    document.addEventListener('keydown', e => {{
      if (e.key === 'Escape') {{
        closeLightbox();
        closeDetail();
      }}
    }});

    window.addEventListener('DOMContentLoaded', initData);
  </script>
</body>
</html>
"""

    index_html_path = DOCS_DIR / "index.html"
    with open(index_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[export] Generated static site at: {index_html_path} ({len(recipes)} recipes)")
    return index_html_path


def auto_sync_github() -> dict:
    """Export static site, git commit, and git push docs/ to GitHub."""
    out_path = generate_static_site()

    # Check if git is initialized
    is_git = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], capture_output=True, text=True)
    if is_git.returncode != 0:
        return {
            "exported": True,
            "git_synced": False,
            "message": "Static site generated in docs/. Initialize git and set remote origin to enable auto-push."
        }

    try:
        # Stage docs/ and canonical data
        subprocess.run(["git", "add", "docs/", "data/recipes.json"], check=True)

        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain", "docs/", "data/recipes.json"], capture_output=True, text=True)
        if not status.stdout.strip():
            return {
                "exported": True,
                "git_synced": True,
                "message": "Docs are already up to date with GitHub."
            }

        # Commit
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subprocess.run(["git", "commit", "-m", f"Auto-update recipe cookbook [{now_str}]"], check=True)

        # Check for remote origin
        remotes = subprocess.run(["git", "remote"], capture_output=True, text=True)
        if "origin" in remotes.stdout:
            push_res = subprocess.run(["git", "push"], capture_output=True, text=True, timeout=25)
            if push_res.returncode == 0:
                print("[github] Successfully pushed updated docs/ to GitHub!")
                return {
                    "exported": True,
                    "git_synced": True,
                    "message": "Successfully published latest recipes to GitHub Pages!"
                }
            else:
                print(f"[github push warning]: {push_res.stderr}")
                return {
                    "exported": True,
                    "git_synced": False,
                    "message": f"Git commit created. Push failed: {push_res.stderr[:80]}"
                }
        else:
            return {
                "exported": True,
                "git_synced": False,
                "message": "Git commit created. Add remote origin to push automatically."
            }

    except Exception as e:
        print(f"[github sync error]: {e}")
        return {"exported": True, "git_synced": False, "error": str(e)}


if __name__ == "__main__":
    generate_static_site()
    res = auto_sync_github()
    print("Result:", res)
