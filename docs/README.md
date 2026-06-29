# 🚀 nebula-core-v3 — Project Documentation

**Internal project name**: `nebula-core-v3`  
**GitHub**: [github.com/lalishka/nebula-core-v3](https://github.com/lalishka/nebula-core-v3) *(private)*  
**Brand**: ChonkerTalks  
**Purpose**: Fully automated Reddit story → multilingual YouTube video publishing pipeline

---

## 📋 Table of Contents

1. [Project Overview](#1-project-overview)
2. [Channel Network Strategy](#2-channel-network-strategy)
3. [Tech Stack](#3-tech-stack)
4. [Project File Structure](#4-project-file-structure)
5. [Reddit Simulator](#5-reddit-simulator-web-tool)
6. [Scraper — Architecture & Plan](#6-scraper--architecture--plan)
7. [Translation & TTS Pipeline](#7-translation--tts-pipeline)
8. [YouTube Auto-Publisher](#8-youtube-auto-publisher)
9. [GitHub Actions Automation](#9-github-actions-automation)
10. [Security & Secrets](#10-security--secrets)
11. [Local Development](#11-local-development)
12. [Roadmap](#12-roadmap)

---

## 1. Project Overview

**nebula-core-v3** is an automated content production system that:

1. Finds viral stories from Reddit (scraped by virality score)
2. Translates them into 7 languages using AI
3. Generates high-quality neural voice narration via **ElevenLabs**
4. Publishes videos automatically to 7 YouTube channel networks
5. Uses a custom-built Reddit UI simulator for visual video recording

The system is modeled after the successful **LUNA 2** architecture — orchestration runs locally via GitHub CLI, heavy processing (rendering, uploading) runs in GitHub Actions cloud runners at zero local CPU cost.

---

## 2. Channel Network Strategy

Configuration file: `channels.json`

| Handle | Language | Region | Niche | Format | Priority |
|---|---|---|---|---|---|
| `@ChonkerTalksRussia` | 🇷🇺 Russian | RU/CIS | Horror + Drama | Long + Shorts | ⭐⭐⭐⭐ |
| `@ChonkerTalksEn` | 🇬🇧 English | US/UK/AU/CA | AITA Drama | Shorts + Long | ⭐⭐⭐ |
| `@ChonkerTalksDe` | 🇩🇪 German | DE/AT/CH | Horror (empty niche!) | Long | ⭐⭐⭐⭐⭐ |
| `@ChonkerTalksES` | 🌎 Spanish LATAM | Mexico/Argentina/Colombia+ | Family Scandals | Shorts + Long | ⭐⭐⭐⭐⭐ |
| `@CHONKERTALKSpo` | 🇧🇷 Portuguese BR | Brazil (2nd biggest YT market) | Drama + Confessions | Shorts | ⭐⭐⭐⭐⭐ |
| `@ChonkerTalksFR` | 🇫🇷 French | FR/BE/CA | Horror + Mystery | Long | ⭐⭐⭐⭐ |
| `@ChonkerTalksIT` | 🇮🇹 Italian | Italy | Relationship Drama | Shorts + Long | ⭐⭐⭐ |

### Subreddit → Channel Mapping

| Channel | Primary Subreddits |
|---|---|
| Russia 🇷🇺 | `r/nosleep`, `r/LetsNotMeet`, `r/creepyencounters`, `r/AmItheAsshole` |
| English 🇬🇧 | `r/AmItheAsshole`, `r/relationship_advice`, `r/TIFU` |
| German 🇩🇪 | `r/nosleep`, `r/LetsNotMeet`, `r/Glitch_in_the_Matrix` |
| LATAM 🌎 | `r/AmItheAsshole`, `r/entitledparents`, `r/confession` |
| Brazil 🇧🇷 | `r/confession`, `r/AmItheAsshole`, `r/offmychest` |
| French 🇫🇷 | `r/nosleep`, `r/Glitch_in_the_Matrix`, `r/UnresolvedMysteries` |
| Italian 🇮🇹 | `r/AmItheAsshole`, `r/relationship_advice`, `r/confession` |

### Virality Filtering Rules

Stories are selected based on:
- **Upvotes**: minimum 1,000 (configurable per channel)
- **Comments ratio**: high comment/upvote ratio → indicates controversy → more YouTube comments
- **Time window**: `top/week` — validated viral content, not temporary spikes
- **Body length**: minimum 300 characters (enough content for full video narration)

---

## 3. Tech Stack

| Component | Technology |
|---|---|
| Reddit scraping | PRAW (Python Reddit API Wrapper) + OAuth2 |
| AI Translation | Prompt-engineered per-language translation (culturally adapted) |
| Voice synthesis | **ElevenLabs** via REST API — full emotion support, multilingual v2 |
| YouTube publishing | YouTube Data API v3 (OAuth2 Refresh Tokens, 7 accounts) |
| CI/CD | GitHub Actions (ubuntu-latest runners) |
| Orchestration | GitHub CLI (`gh workflow run`) — **local dispatch only** |
| Secrets management | GitHub Repository Secrets |
| Visual recorder | Custom HTML/CSS/JS Reddit UI Simulator |

---

## 4. Project File Structure

```
reddit/                            ← Project root (nebula-core-v3)
│
├── index.html                     ← Reddit Simulator main page
├── style.css                      ← Simulator CSS (themes, layouts, safe zones)
├── app.js                         ← Simulator JS (typing engine, audio, state)
│
├── scraper.py                     ← Reddit story fetcher ← NEEDS PRAW OAuth fix
├── translator_tts.py              ← Translation + voice synthesis
├── uploader.py                    ← YouTube Data API v3 auto-publisher
│
├── channels.json                  ← Channel strategy config
├── requirements.txt               ← Python dependencies
│
├── scrapers/                      ← Reference scrapers (study only)
│   ├── ScrapiReddit/              ← Zero-auth (broken, Reddit blocked May 2026)
│   └── URS/                       ← PRAW-based reference implementation
│
└── .github/
    └── workflows/
        └── auto_publish.yml       ← GitHub Actions daily pipeline
```

---

## 5. Reddit Simulator (Web Tool)

Running at: [http://localhost:8080](http://localhost:8080)

A fully custom web application mimicking Reddit's interface for use as video background when recording narrated content.

### Features
- **Dual layout**: Mobile card (9:16) and Desktop page (16:9)
- **3 Themes**: Reddit Midnight (AMOLED), Reddit Dark, Reddit Light
- **Aspect ratios**: 9:16 (Shorts/Reels), 16:9 (YouTube), 1:1 (Instagram)
- **Safe zone overlays**: YouTube Shorts, Instagram Reels, TikTok UI masks
- **Typing engine**: Typewriter effect with realistic speed jitter, punctuation pauses, typos
- **Sound synthesis**: Web Audio API keyboard sounds (Mech Blue, Mech Brown, Chiclet, Typewriter)
- **Multi-comment support**: Sequential post title → body → comments typing
- **Clean recording mode**: Hides all controls for distraction-free capture

### Keyboard Shortcuts
| Key | Action |
|---|---|
| `SPACE` | Play / Pause typing |
| `R` | Reset animation |
| `ESC` | Exit recording mode |

---

## 6. Scraper — Architecture & Plan

### Current Status

> [!CAUTION]
> Reddit blocked **all unauthenticated `.json` endpoints on May 30, 2026**.
> `scraper.py` currently returns `HTTP 403`.
> **Required fix**: Add PRAW OAuth2 authentication (10 lines of code).

### Root Cause: Why All Free Scrapers Fail in 2026

| Scraper | Status | Reason |
|---|---|---|
| ScrapiReddit (zero-auth) | ❌ Dead | Reddit blocked unauthenticated endpoints |
| URS | ✅ Works | Uses PRAW with approved OAuth keys |
| Our scraper.py | ❌ Dead | No OAuth token |

### Fix Plan: PRAW OAuth Integration

#### Step 1 — Get Reddit API Credentials (5 min)
1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Click **"Create App"** → type: **script**
3. Name: `chonkertalks-bot` (any name works)
4. Redirect URI: `http://localhost:8080`
5. Click Create → copy **`client_id`** (under app name) + **`client_secret`**

#### Step 2 — Add to GitHub Secrets
```
REDDIT_CLIENT_ID
REDDIT_CLIENT_SECRET
REDDIT_USERNAME
REDDIT_PASSWORD
```

#### Step 3 — Updated scraper.py Core Logic

```python
import praw, os, json

def get_reddit():
    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent="ChonkerTalksBot/1.0"
    )

def virality_score(post):
    """Score a post's viral potential 0–100"""
    score = 0
    ratio = post.num_comments / max(post.score, 1)
    if ratio > 0.1:          score += 30  # Controversy = comments > 10% of upvotes
    if post.score > 5_000:   score += 25  # Proven popular
    if post.score > 15_000:  score += 20  # Bonus for mega-viral
    if post.num_comments > 1_000: score += 15
    if len(post.selftext) > 500:  score += 10  # Enough content for video
    return score

def fetch_best_story(channel_config):
    reddit = get_reddit()
    best, best_score = None, 0
    for sub_name in channel_config["subreddits"]:
        for post in reddit.subreddit(sub_name).top(time_filter="week", limit=25):
            if post.stickied or len(post.selftext) < 300:
                continue
            s = virality_score(post)
            if s > best_score:
                best_score, best = s, post
    return format_story(best, best_score)
```

### Virality Scoring Algorithm

| Signal | Points | Why It Matters |
|---|---|---|
| Comments/Upvotes ratio > 10% | +30 | Controversy = viewers argue in your comments → algorithm boost |
| Score > 5,000 | +25 | Proven mainstream appeal |
| Score > 15,000 | +20 | Mega-viral bonus |
| Comments > 1,000 | +15 | High engagement signal |
| Body length > 500 chars | +10 | Enough content for full 5–10 min video |

### Output Format `story_data.json`

```json
{
  "subreddit": "r/AmItheAsshole",
  "title": "AITA for refusing to attend my sister's wedding?",
  "author": "u/ThrowRA_Sister22",
  "body": "So this happened last month...",
  "upvotes": "18.4k",
  "comments_count": "2.1k",
  "virality_score": 90,
  "url": "https://reddit.com/r/AmItheAsshole/comments/...",
  "comments": [
    {
      "id": 1,
      "username": "u/JudgmentCall99",
      "time": "5h ago",
      "body": "NTA. Your sister knew what she was doing.",
      "upvotes": "4.2k"
    }
  ]
}
```

---

## 7. Translation & TTS Pipeline

### Current: Edge-TTS (Microsoft, free)
Basic, robotic voice. Sufficient for testing.

### Planned: ElevenLabs (`eleven_multilingual_v2`)

```python
def generate_voice(text, voice_id, output_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.75,
            "style": 0.5,          # Emotional expressiveness
            "use_speaker_boost": True
        }
    }
    r = requests.post(url, headers=headers, json=payload)
    open(output_path, "wb").write(r.content)
```

### Translation Prompts per Channel

Each channel's `channels.json` entry has a `translate_prompt` field:

| Channel | Translation Strategy |
|---|---|
| 🇷🇺 Russia | Разговорный стиль, молодёжная речь, эмоции оригинала |
| 🇩🇪 Germany | Natürliche Jugendsprache, kein formelles Deutsch |
| 🌎 LATAM | Español latinoamericano neutro — sin vosotros, sin regionalismos |
| 🇧🇷 Brazil | Português brasileiro coloquial, tom de amigos |
| 🇫🇷 France | Français courant, ton naturel de jeune adulte |
| 🇮🇹 Italy | Italiano colloquiale, tono informale |

---

## 8. YouTube Auto-Publisher

### Multi-Account Architecture

All 7 accounts share **one Google Cloud OAuth App** (Client ID + Secret).  
Each account has its own **refresh token** stored in GitHub Secrets.

| Secret | Channel |
|---|---|
| `YOUTUBE_REFRESH_TOKEN_ACC1` | Account 1 |
| `YOUTUBE_REFRESH_TOKEN_ACC2` | Account 2 |
| ... | ... |
| `YOUTUBE_REFRESH_TOKEN_ACC7` | Account 7 |

### API Scopes Required
- `youtube.upload` — Upload videos
- `youtube.force-ssl` — Manage thumbnails, metadata
- `yt-analytics.readonly` — Performance stats

---

## 9. GitHub Actions Automation

Schedule: **Daily at 18:00 UTC** (or manually triggered)

### Pipeline Flow
```
scraper.py → story_data.json
    ↓
translator_tts.py → translated_text + narration.mp3
    ↓
uploader.py → YouTube video published
```

### ⚠️ Orchestration Rule (CRITICAL)

> [!IMPORTANT]
> Per **LUNA 2 architecture**: Never use `GITHUB_TOKEN` inside runners for batch workflow dispatch.
> `GITHUB_TOKEN` = 1,000 req/hour. Developer OAuth token = 5,000 req/hour.
> **Always trigger from local terminal:**
> ```bash
> gh workflow run auto_publish.yml --ref main -f channel=ru -f subreddit=nosleep
> ```

---

## 10. Security & Secrets

> [!CAUTION]
> Never commit secrets to Git. All credentials live in GitHub Repository Secrets only.

| Secret | Status | Purpose |
|---|---|---|
| `YOUTUBE_CLIENT_ID` | ✅ Set | Google OAuth App |
| `YOUTUBE_CLIENT_SECRET` | ✅ Set | Google OAuth App |
| `YOUTUBE_REFRESH_TOKEN_ACC1–7` | ✅ Set (all 7) | Per-account YouTube tokens |
| `REDDIT_CLIENT_ID` | ⏳ Needed | Reddit PRAW OAuth |
| `REDDIT_CLIENT_SECRET` | ⏳ Needed | Reddit PRAW OAuth |
| `REDDIT_USERNAME` | ⏳ Needed | Reddit account |
| `REDDIT_PASSWORD` | ⏳ Needed | Reddit account |
| `ELEVENLABS_API_KEY` | ⏳ Needed | Voice synthesis |

---

## 11. Local Development

```bash
# Start Reddit Simulator
cd /Users/lali/Projects/reddit
python3 -m http.server 8080
# → http://localhost:8080

# Push changes
git add . && git commit -m "message" && git push origin main

# Trigger pipeline manually
gh workflow run auto_publish.yml --ref main

# Check secrets
gh secret list

# Install PRAW (when ready)
pip3 install praw
```

---

## 12. Roadmap

### ✅ Completed
- [x] Reddit Simulator (typewriter, 3 themes, safe zones, keyboard sounds)
- [x] Desktop + Mobile dual layout
- [x] GitHub private repo `nebula-core-v3`
- [x] YouTube OAuth for all 7 accounts
- [x] GitHub Secrets (9 secrets configured)
- [x] `channels.json` — full channel strategy config
- [x] `scraper.py`, `translator_tts.py`, `uploader.py` base scripts
- [x] GitHub Actions workflow `auto_publish.yml`
- [x] Scrapers research & comparison documentation

### 🔄 Next Steps (Priority Order)
- [ ] **1. Fix scraper.py** — Add PRAW OAuth (needs Reddit API keys from reddit.com/prefs/apps)
- [ ] **2. Upgrade TTS** — Switch Edge-TTS → ElevenLabs API
- [ ] **3. AI virality filter** — Score stories by emotional intensity + controversy
- [ ] **4. Channel art** — Generate banners/avatars using Imagen 2 from LUNA 2

### 🔮 Future
- [ ] `render.py` — FFmpeg video renderer (Simulator screenshot + audio → MP4)
- [ ] Custom Chonker cat avatars per language
- [ ] Analytics readback — track best performing content per language
- [ ] Auto A/B test thumbnails
