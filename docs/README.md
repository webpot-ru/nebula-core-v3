# 🚀 nebula-core-v3 — Project Documentation

**Internal project name**: `nebula-core-v3`  
**GitHub**: [github.com/lalishka/nebula-core-v3](https://github.com/lalishka/nebula-core-v3) *(private)*  
**Brand**: ChonkerTalks  
**Purpose**: Automated multilingual YouTube story-entertainment publishing pipeline
**Last updated**: 2026-06-29

**Current state for new chats**: read [`PROJECT_STATE.md`](PROJECT_STATE.md) first.

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

**nebula-core-v3** is an automated content production system for regional YouTube story-entertainment channels.

1. Tests short-form hooks across region-specific entertainment topics
2. Expands the winning topics into long-form videos for the same channel audience
3. Uses Reddit stories as one possible source, not as the whole content strategy
4. Generates neural voice narration via **AI33 TTS v3** (prefixed voice ids for ElevenLabs, MiniMax, Edge, Kokoro, or clones)
5. Publishes videos automatically to multilingual YouTube channel networks
6. Uses a custom-built Reddit UI simulator for visual video recording when the format needs it

The system is modeled after the successful **LUNA 2** architecture — orchestration runs locally via GitHub CLI, heavy processing (rendering, uploading) runs in GitHub Actions cloud runners at zero local CPU cost.

---

## 2. Channel Network Strategy

Status: **supersedes the older "one language = one Reddit niche" plan.**

`channels.json` is still the current execution config for scripts, voices, and scraper inputs. It is **not** the final content strategy. Before production publishing, update it to match the audience-first strategy below.

### Strategy Rule

One channel should be defined by **language + viewer promise + tone**, not by a single subreddit or a single narrow topic. Shorts and long-form videos can cover different topics inside one channel if they satisfy the same viewer promise.

Operational split:
- **Shorts**: fast hook testing, trend response, punchy facts, mini-dramas, mysteries, quizzes.
- **Long-form**: expand proven Shorts topics into 8-18 minute explainers, story documentaries, moral-drama breakdowns, mystery timelines, or compilation-style episodes.
- **Reddit**: one source of story material, especially for human drama and scary stories. It should not be treated as the whole channel concept.

### Recommended Channel Concepts

| Market / Language | Primary Channel Promise | Shorts Mix | Long-form Mix | Priority |
|---|---|---|---|---|
| LATAM Spanish | Emotional story entertainment: drama, internet lore, challenges, scary hooks | family scandals, AITA-style choices, creator/internet drama, quick mysteries | mini-telenovela-style story breakdowns, internet lore, challenge/adventure explainers | Highest |
| Brazil Portuguese | Curiosities, football culture, emotional human stories | strange facts, football stories, moral drama hooks, pop-culture moments | football documentaries without match footage, curiosity explainers, strong personal stories | Highest |
| French | Mystery, true stories, pop culture, gaming/creator lore | creepy facts, case hooks, creator drama, gaming lore | mystery timelines, true-story explainers, pop-culture dossiers | High |
| German | Science/curiosity, experiments, strange facts, tech/internet explainers | "what happens if...", visual facts, tech hooks, strange discoveries | quality explainers, experiment recaps, internet/science documentaries | High |
| Italian | Visual social comedy, football/food identity, relationship drama | visual sketches, relationship mini-scenes, football moments, food/culture hooks | social-experiment episodes, football/food culture stories, drama compilations | Medium-high |
| English | Spectacle curiosity, internet lore, story hooks | experiments, gadgets, internet drama, "what happened next" hooks | high-production explainers, creator/internet lore, mystery or science stories | High upside / high competition |
| Russian-speaking / CIS diaspora | Tech/gaming/facts plus dark stories, with platform-risk awareness | gaming facts, tech hooks, strange stories | tech/gaming explainers, dark-story compilations | Opportunistic |

### Topic Families to Test

1. **Dark Curiosity / Strange Stories** — disappearances, creepy internet lore, unresolved mysteries, unusual real events.
2. **Human Drama / AITA Court** — relationship conflict, family scandals, workplace drama, "who is right?" formats.
3. **Curiosity / Experiments / Facts** — visual explainers, surprising science, everyday experiments, "did you know?" formats.
4. **Football Culture** — player arcs, club lore, transfer drama, fan culture, rights-safe documentaries and quizzes.
5. **Pop Culture / Internet Lore** — meme histories, creator drama, fandom moments, gaming and series timelines.
6. **Visual Social Comedy** — language-light Shorts, relationship sketches, expectation-vs-reality, street-style prompts.

### Evidence Basis

- Top-channel patterns reviewed through SocialBlade country lists for [Brazil](https://socialblade.com/youtube/top/country/br/mostsubscribed), [Mexico](https://socialblade.com/youtube/top/country/mx/mostsubscribed), [Germany](https://socialblade.com/youtube/top/country/de/mostsubscribed), [France](https://socialblade.com/youtube/lists/top/50/subscribers/all/FR), [Italy](https://socialblade.com/youtube/lists/top/50/subscribers/all/IT), [UK](https://socialblade.com/youtube/lists/top/50/subscribers/all/GB), [US](https://socialblade.com/youtube/lists/top/50/subscribers/all/US), and [Russia](https://socialblade.com/youtube/lists/top/50/subscribers/all/RU).
- YouTube Shorts research indicates Shorts over-index toward entertainment, while regular long-form supports a wider range of topics: [arXiv:2403.00454](https://arxiv.org/abs/2403.00454).
- Russia/CIS YouTube strategy carries extra platform-access risk, so treat it as opportunistic rather than the first launch market.

### Scraper / Source Filtering Rules

For Reddit-derived stories only:
- **Upvotes**: minimum 1,000 unless a market-specific experiment says otherwise.
- **Comments ratio**: high comment/upvote ratio indicates controversy and discussion potential.
- **Time window**: `top/week` for validated viral content rather than temporary spikes.
- **Body length**: minimum 300 characters for narration depth.

---

## 3. Tech Stack

| Component | Technology |
|---|---|
| Reddit scraping | PRAW (Python Reddit API Wrapper) + OAuth2 |
| AI Translation | Prompt-engineered per-language translation (culturally adapted) |
| Voice synthesis | **AI33 TTS v3** via multipart FormData (`xi-api-key`) |
| Metadata / SEO | **VectorEngine Gemini** (`gemini-3.5-flash`) |
| Thumbnail image generation | **VectorEngine image** (`gpt-image-2`) via explicit `--confirm-spend` |
| Dry-run video rendering | Deterministic `storyboard_generator.py` + RedditSim headless Chrome/Chromium capture + FFmpeg |
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
├── scraper.py                     ← Reddit story fetcher (PRAW OAuth2 + virality scoring)
├── metadata_generator.py          ← VectorEngine Gemini YouTube metadata + SEO
├── thumbnail_generator.py         ← VectorEngine image thumbnail generator
├── vectorengine_client.py         ← Shared VectorEngine text/image client
├── translator_tts.py              ← AI33 TTS v3 narration generator
├── storyboard_generator.py        ← Deterministic story_data.json → storyboard.json
├── render.py                      ← RedditSim dry-run renderer: storyboard.json → final_output.mp4
├── uploader.py                    ← YouTube Data API v3 auto-publisher
│
├── channels.json                  ← Current execution config; content strategy above supersedes old niche plan
├── sample_story_data.json         ← Safe fixture for local/GitHub dry-run rendering
├── requirements.txt               ← Python dependencies
│
├── scrapers/                      ← Reference scrapers (study only)
│   ├── ScrapiReddit/              ← Zero-auth (broken, Reddit blocked May 2026)
│   └── URS/                       ← PRAW-based reference implementation
│
└── .github/
    └── workflows/
        ├── auto_publish.yml       ← Production sketch; not end-to-end verified
        └── video_dry_run.yml      ← Manual dry-run MP4 render artifact workflow
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

### Dry-Run Storyboard / Renderer

The minimal no-spend video path is now:

```text
sample_story_data.json or story_data.json
  -> storyboard_generator.py
  -> storyboard.json
  -> render.py
  -> final_output.mp4
```

This path does **not** call Reddit, AI33, VectorEngine, or YouTube. It is only a proof that the project can create a 9:16 MP4 artifact locally and in GitHub Actions.

```bash
python3 storyboard_generator.py --input sample_story_data.json --output storyboard.json
python3 render.py --storyboard storyboard.json --output final_output.mp4
test -s final_output.mp4
ffprobe final_output.mp4
```

`render.py` opens the existing RedditSim UI (`index.html` + `app.js`) in headless Chrome/Chromium, loads `render_story` from `storyboard.json`, samples deterministic typing progress screenshots, and uses FFmpeg to encode them into `final_output.mp4`. It is intentionally minimal: no voiceover, no subtitles, no external API calls, no upload.

The GitHub dry-run workflow is `.github/workflows/video_dry_run.yml`. It can be run manually and also runs on pushes that touch the renderer/simulator/sample files. It installs FFmpeg, uses the runner browser, builds `storyboard.json`, renders `final_output.mp4`, verifies the file with `ffprobe`, creates preview PNGs, and uploads all outputs as the `chonkertalks-dry-run-video` artifact.

---

## 6. Scraper — Architecture & Plan

### Current Status

> [!NOTE]
> ✅ **PRAW OAuth2 integration complete.** `scraper.py` fully rewritten and pushed to GitHub.
> Reddit App: **red 2025** | Account: `Complex_Lack4476`
> GitHub Secrets set: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`
> ⏳ Only missing: `REDDIT_PASSWORD` — add with: `gh secret set REDDIT_PASSWORD --body "your_password"`

### Root Cause: Why All Third-Party Scrapers Also Fail in 2026

| Scraper | Status | Reason |
|---|---|---|
| ScrapiReddit (zero-auth) | ❌ Dead | Reddit blocked unauthenticated endpoints since May 2026 |
| URS | ✅ Works | Uses PRAW with approved OAuth keys |
| **Our scraper.py** | ✅ **Working** | **PRAW OAuth2 integrated, virality scoring added** |

### Reddit API Credentials

| Field | Value |
|---|---|
| App name | red 2025 |
| Type | personal use script |
| Client ID | `JYA8zMAO2b1GTIZnHoITbg` |
| Client Secret | stored in GitHub Secrets |
| Reddit Account | `Complex_Lack4476` |
| Reddit App URL | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |

#### GitHub Secrets Status
```
REDDIT_CLIENT_ID      ✅ Set
REDDIT_CLIENT_SECRET  ✅ Set
REDDIT_USERNAME       ✅ Set (Complex_Lack4476)
REDDIT_PASSWORD       ⏳ Needed → gh secret set REDDIT_PASSWORD --body "..."
```

### scraper.py — CLI Usage

```bash
# Scan subreddits from channels.json (channel #1 by default)
python3 scraper.py

# Scan a specific subreddit
python3 scraper.py nosleep

# Use a specific channel's subreddit strategy
python3 scraper.py --channel acc4

# Custom time filter
python3 scraper.py --channel acc1 --time month

# Custom output file
python3 scraper.py --channel acc3 --output story_ru.json
```

### scraper.py — Key Functions

| Function | Purpose |
|---|---|
| `get_reddit()` | Authenticates with Reddit via PRAW OAuth2 |
| `virality_score(post)` | Scores post virality 0–100 based on 5 signals |
| `fetch_best_story(subreddits)` | Scans all subreddits, picks highest-scoring post |
| `fetch_top_comments(reddit, post_id)` | Fetches top 3 comments (excludes AutoModerator) |
| `load_channel_config(channel_id)` | Reads subreddit list from channels.json |

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

### Current: AI33 TTS v3

`translator_tts.py` now submits narration text to AI33's unified v3 endpoint:

```bash
python3 translator_tts.py es --output narration_es.mp3
python3 translator_tts.py --channel acc4 --output narration_es.mp3
python3 translator_tts.py ru --voice-id edge_ru-RU-DmitryNeural
```

The script sends multipart FormData to:

```text
POST https://api.ai33.pro/v3/text-to-speech
Header: xi-api-key: $AI33_API_KEY
Fields: text, voice_id, model_id, speed, with_transcript, context_chaining, file_name
```

`voice_id` must already include an AI33 provider prefix:

```text
elevenlabs_...
minimax_...
clone_...
edge_...
kokoro_...
```

`channels.json` is the current source of truth for per-channel TTS voice ids. The current defaults use Edge-backed voices routed through AI33 for a low-risk baseline:

| Channel | AI33 voice_id |
|---|---|
| 🇷🇺 Russia | `edge_ru-RU-DmitryNeural` |
| 🇬🇧 English | `edge_en-US-ChristopherNeural` |
| 🇩🇪 Germany | `edge_de-DE-ConradNeural` |
| 🌎 LATAM | `edge_es-MX-JorgeNeural` |
| 🇧🇷 Brazil | `edge_pt-BR-AntonioNeural` |
| 🇫🇷 France | `edge_fr-FR-HenriNeural` |
| 🇮🇹 Italy | `edge_it-IT-DiegoNeural` |

To upgrade a channel to ElevenLabs v3 or MiniMax, first read AI33 Voice Library and paste the returned prefixed `voice_id` into `channels.json` or pass it with `--voice-id`.

For ElevenLabs-backed voices, `translator_tts.py` sends `model_id=eleven_v3` by default. Override only intentionally:

```bash
python3 translator_tts.py en --voice-id elevenlabs_... --model-id eleven_v3
AI33_TTS_MODEL_ID=eleven_v3 python3 translator_tts.py en --voice-id elevenlabs_...
```

### AI33 Task Handling

The v3 create call returns a `task_id`. `translator_tts.py` polls the AI33 Common Task endpoint using:

```text
AI33_TASK_URL_TEMPLATE=https://api.ai33.pro/v3/task/{task_id}
```

The v3 task endpoint uses `Authorization: $AI33_API_KEY` by default. If AI33's live docs or account-specific routing use a different task URL or header, set `AI33_TASK_URL_TEMPLATE` or `AI33_TASK_AUTH_HEADER` in the environment. Use `--no-poll` when using a webhook-only `receive_url`; the script will save `*.ai33-task.json` metadata instead of waiting for an audio file.

### Required Secret

Use `AI33_API_KEY` in local shell and GitHub Secrets. `A133_API_KEY` is accepted only as a compatibility fallback because older LUNA2 notes mention that typo. Do not copy or print the key in chat or docs.

```bash
export AI33_API_KEY="..."
python3 translator_tts.py es --dry-run
python3 translator_tts.py es --output narration_es.mp3
```

Live audio generation spends AI33 credits, so run it intentionally.

### Live Smoke Result

On 2026-06-29, user-approved local smokes used the gitignored LUNA2 AI33 key without printing or copying it into this repo. The first test submitted an ElevenLabs-prefixed voice id with `[sighs]`, `[laughs]`, and `[whispers]` tags. A second test explicitly sent `model_id=eleven_v3` with `[laughs]` and `[sighs]`; AI33 returned `task_id=08c146ad-82a0-4efb-a4e2-f8ec65254852`, `/v3/task/{task_id}` polling returned `status=done`, and the output file was a valid 5.64s MP3 at `/tmp/reddit_ai33_eleven_v3_laugh.mp3`.

Important distinction: the smoke used an `elevenlabs_...` voice. The current `channels.json` defaults are `edge_...` voices routed through AI33 as a low-risk baseline; if emotional sound tags like laughter should be default behavior, choose final `elevenlabs_...` or `minimax_...` voices from AI33 Voice Library and update `channels.json`.

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

### VectorEngine Metadata / SEO

`metadata_generator.py` builds YouTube packaging from `story_data.json` and `channels.json`:

```bash
# No API spend
python3 metadata_generator.py --story story_data.json --channel acc4 --dry-run

# Live VectorEngine Gemini call
python3 metadata_generator.py --story story_data.json --channel acc4 --confirm-spend --output youtube_metadata.json
```

Output shape:

```json
{
  "youtube_title": "...",
  "youtube_description": "...",
  "tags": ["..."],
  "hashtags": ["#..."],
  "thumbnail_text": "...",
  "thumbnail_prompt": "...",
  "seo_keywords": ["..."],
  "risk_flags": ["..."]
}
```

`uploader.py` prefers `youtube_metadata.json` when present, then falls back to `story_data.json`.

### VectorEngine Thumbnail Images

`thumbnail_generator.py` uses `youtube_metadata.json.thumbnail_prompt` and VectorEngine image generation:

```bash
# No image spend
python3 thumbnail_generator.py --metadata youtube_metadata.json --dry-run

# Paid image generation
python3 thumbnail_generator.py --metadata youtube_metadata.json --confirm-spend --output youtube_thumbnail.png
```

The default image model is `gpt-image-2`, default size `1536x864`. Actual image generation is intentionally not run automatically in the current workflow.

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

### Dry-Run Render Workflow

`video_dry_run.yml` is the safe workflow to run first. It can be triggered manually or by pushes touching the dry-run renderer/simulator/sample files, and it does not use secrets:

```text
sample_story_data.json
  -> storyboard_generator.py
  -> render.py
  -> final_output.mp4
  -> artifact upload
```

It installs FFmpeg explicitly, verifies `final_output.mp4` with `test -s` and `ffprobe`, then uploads the MP4 and storyboard as a GitHub Actions artifact.

### Production Publish Workflow

`auto_publish.yml` is still a production sketch and is **not** end-to-end verified. It is scheduled daily at 18:00 UTC and can be manually triggered, but it still needs the production render/localization path before safe upload.

Planned production flow:
```
scraper.py → story_data.json
    ↓
localize_story.py → story_localized_<lang>.json
    ↓
metadata_generator.py → youtube_metadata.json via VectorEngine
    ↓
translator_tts.py → narration_<lang>.mp3 via AI33
    ↓
storyboard_generator.py → storyboard.json
    ↓
render.py → final_output.mp4
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
| `YOUTUBE_CLIENT_ID` | ✅ Documented set | Google OAuth App |
| `YOUTUBE_CLIENT_SECRET` | ✅ Documented set | Google OAuth App |
| `YOUTUBE_REFRESH_TOKEN_ACC1–7` | ✅ Documented set | Per-account YouTube tokens |
| `REDDIT_CLIENT_ID` | ✅ Documented set | Reddit PRAW OAuth |
| `REDDIT_CLIENT_SECRET` | ✅ Documented set | Reddit PRAW OAuth |
| `REDDIT_USERNAME` | ✅ Documented set | Reddit account |
| `REDDIT_PASSWORD` | ⏳ Needed | Reddit account |
| `AI33_API_KEY` | ⏳ Needed / not re-read | AI33 TTS v3 |
| `VECTORENGINE_API_KEY` | ⏳ Needed / local smoke passed with LUNA2 env | VectorEngine metadata and thumbnail generation |

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

# Trigger no-spend dry-run render manually
gh workflow run video_dry_run.yml --ref main

# Check secrets
gh secret list

# Generate narration through AI33 without spending credits
python3 translator_tts.py es --dry-run

# Generate narration through AI33 (spends AI33 credits)
AI33_API_KEY=... python3 translator_tts.py es --output narration_es.mp3

# Generate YouTube SEO metadata through VectorEngine without spending credits
python3 metadata_generator.py --story story_data.json --channel acc4 --dry-run

# Generate YouTube SEO metadata through VectorEngine (spends VectorEngine credits)
VECTORENGINE_API_KEY=... python3 metadata_generator.py --story story_data.json --channel acc4 --confirm-spend

# Generate thumbnail image through VectorEngine without spending credits
python3 thumbnail_generator.py --metadata youtube_metadata.json --dry-run

# Generate a local no-spend MP4 dry-run
python3 storyboard_generator.py --input sample_story_data.json --output storyboard.json
python3 render.py --storyboard storyboard.json --output final_output.mp4
test -s final_output.mp4
ffprobe final_output.mp4
```

---

## 12. Roadmap

### ✅ Completed
- [x] Reddit Simulator (typewriter, 3 themes, safe zones, keyboard sounds)
- [x] Desktop + Mobile dual layout
- [x] GitHub private repo `nebula-core-v3`
- [x] YouTube OAuth for all 7 accounts
- [x] GitHub Secrets baseline documented; live readback still required before production runs
- [x] `channels.json` — initial execution config; content strategy now supersedes the old niche plan
- [x] `scraper.py` — **fully rewritten with PRAW OAuth2 + virality scoring**
- [x] `translator_tts.py` switched to AI33 TTS v3, `uploader.py` base script
- [x] `metadata_generator.py` connected to VectorEngine Gemini for SEO metadata
- [x] `thumbnail_generator.py` connected to VectorEngine image generation behind explicit spend confirmation
- [x] `storyboard_generator.py` and `render.py` create a no-spend dry-run `final_output.mp4`
- [x] GitHub Actions workflow `video_dry_run.yml` renders and uploads a dry-run MP4 artifact
- [x] GitHub Actions workflow `auto_publish.yml`
- [x] Scrapers research & comparison documentation
- [x] Reddit App registered: **red 2025** (Complex_Lack4476)

### 🔄 Next Steps (Priority Order)
- [ ] **1. Add REDDIT_PASSWORD secret** → `gh secret set REDDIT_PASSWORD --body "..."`  — then scraper is 100% live
- [ ] **2. Add/verify AI33_API_KEY secret** for this GitHub repo; local one-off smoke passed with the LUNA2 key
- [ ] **3. Update `channels.json` to match the new audience-first strategy** before production publishing
- [ ] **4. Select final ElevenLabs/MiniMax voices** from AI33 Voice Library for each channel if emotion tags should be default
- [ ] **5. Channel art** — Generate banners/avatars using Imagen 2 from LUNA 2
- [ ] **6. Add/verify VECTORENGINE_API_KEY** in GitHub Secrets before relying on workflow metadata generation
- [ ] **7. Add production localization + audio-aware render path** before enabling YouTube upload

### 🔮 Future
- [ ] Browser-captured scene templates, animated captions, and audio-aware timing
- [ ] Custom Chonker cat avatars per language
- [ ] Analytics readback — track best performing content per language
- [ ] Auto A/B test thumbnails
