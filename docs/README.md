# 🚀 nebula-core-v3 — Project Documentation

**Internal project name**: `nebula-core-v3`  
**GitHub**: [github.com/lalishka/nebula-core-v3](https://github.com/lalishka/nebula-core-v3) *(private)*  
**Brand**: ChonkerTalks  
**Purpose**: Automated multilingual YouTube story-entertainment publishing pipeline
**Last updated**: 2026-06-30

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

`channels.json` is still the current execution config for scripts, voices, scraper inputs, and initial topic weights. Its `topic_mix` entries now follow the audience-first strategy below, but the weights are hypotheses until live artifacts and retention/readback prove them.

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
- **Time window**: `auto` uses topic-family windows such as `day + week` for fresh drama and `week + month` for mystery/lore; manual `day|week|month|year` is still available for experiments.
- **Body length**: minimum 300 characters for narration depth.
- **Topic families**: channels now use weighted `topic_mix` values instead of one flat subreddit list. The scraper has rules for `human_drama`, `dark_curiosity`, `curiosity_facts`, `football_culture`, `internet_lore`, and `visual_comedy`.
- **AI budget**: Gemini quality checks are bounded by `MAX_AI_CANDIDATES` / `--max-ai-candidates`; local Reddit metrics and duplicate guards run before any AI call.
- **Duplicate guard**: exact Reddit post ids, normalized story signatures, and similar keyword signatures are skipped per channel.
- **Velocity scoring**: fresh `day/week` candidates get a small bonus for upvotes/hour and comments/hour, so rising stories can beat older high-total posts.
- **Topic fatigue**: recently repeated topic families receive a penalty so one channel does not publish the same kind of story too many times in a row.

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

This path does **not** call Reddit, AI33, VectorEngine, or YouTube. It is only a proof that the project can create an MP4 artifact locally and in GitHub Actions.

Generated previews and scratch files must not be deleted directly. Move them into project Trash with:

```bash
bash scripts/move-to-trash.sh build/render/example_preview.png
find build/render -type f -name '*.png' -print0 | bash scripts/move-to-trash.sh --stdin0
```

The helper preserves project-relative paths under `Trash/<timestamp>/...`; only the user should permanently empty Trash.

```bash
python3 storyboard_generator.py --input sample_story_data.json --output storyboard.json
python3 render.py --storyboard storyboard.json --output final_output.mp4
test -s final_output.mp4
ffprobe final_output.mp4
```

`storyboard_generator.py` now emits `render_slides` for the simulator. The first story screen contains the title/body only, comment screens contain only comments that fit, and long story text advances as new centered card screens rather than a scrolling page. The slide text limits are intentionally conservative because render-mode fonts are sized for mobile Shorts and 16:9 readability.

`render.py` opens the existing RedditSim UI (`index.html` + `app.js`) in headless Chrome/Chromium, loads `render_story` from `storyboard.json`, samples deterministic slide-progress/karaoke screenshots, and uses FFmpeg to encode them into `final_output.mp4`. If `narration.mp3` exists, it is merged into the MP4 as an AAC audio track. If `narration.json` exists and contains usable word timings, the renderer passes it into RedditSim so the current word is highlighted directly inside the currently visible Reddit card text. If AI33 returns missing or partial timings, the renderer disables karaoke and falls back to clean slide-progress frames while still merging the voiceover audio. Karaoke mode does not add extra caption words, lower subtitle strips, or overlay text.

Render orientation is duration-aware. In default `--orientation auto` mode, videos up to 180 seconds render as vertical Shorts (`1080x1920`, mobile layout), while videos longer than 180 seconds render as horizontal long-form video (`1920x1080`, desktop layout). Both modes use the same in-text karaoke highlight; horizontal render fills the 16:9 viewport with a clean centered Reddit card and hides editor/sidebar widgets. Override only intentionally with `--orientation vertical` or `--orientation horizontal`.

The GitHub dry-run workflow is `.github/workflows/video_dry_run.yml`. The current workflow fetches a live Reddit story and calls AI33 for narration/transcript, so it uses configured secrets and can spend provider credits. It installs FFmpeg, uses the runner browser, builds `storyboard.json`, renders `final_output.mp4`, verifies the file with `ffprobe`, creates preview PNGs, and uploads video, story, storyboard, narration, transcript, and previews as an artifact.

Current GitHub verification status: previously recovered after the `startup_failure` ownership/billing issue; see `docs/PROJECT_STATE.md` for the latest verified run and artifact notes.

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

# Topic-family auto mode: searches weighted topic families and their time windows
python3 scraper.py --channel acc4 --time auto

# Force one topic family for experiments
python3 scraper.py --channel acc4 --topic-family human_drama

# Custom time filter and hard Gemini budget
python3 scraper.py --channel acc1 --time month --max-ai-candidates 8 --similarity-threshold 0.72

# Custom output file
python3 scraper.py --channel acc3 --output story_ru.json
```

### scraper.py — Key Functions

| Function | Purpose |
|---|---|
| `get_reddit()` | Authenticates with Reddit via PRAW OAuth2 |
| `virality_score(post)` | Scores post virality 0–100 based on 5 signals |
| `build_topic_sources(...)` | Builds topic-family + time-window source plans from `channels.json` |
| `fetch_best_story(subreddits)` | Scans topic sources, dedupes, ranks, and AI-checks a bounded candidate pool |
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

The final candidate score also includes a small topic-weight boost, time-window freshness adjustment, velocity bonus, and topic-fatigue penalty. Gemini then receives Reddit metrics, velocity, topic-family rules, story signature, and duplicate context. It must return `viral_potential`, `novelty`, `duplicate_risk`, `legal_risk`, and a `PUBLISH | REWRITE | SKIP` verdict.

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
  "velocity_bonus": 5,
  "fatigue_penalty": 0,
  "topic_family": "human_drama",
  "time_window": "week",
  "story_signature": "ab12cd34ef56ab78",
  "keyword_signature": "attend family refusing sister wedding",
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
python3 translator_tts.py ru --voice-id elevenlabs_rQOBu7YxCDxGiFdTm28w
python3 translator_tts.py --channel acc3 --comment-voice-id elevenlabs_LB5G0Z4EP98YaEgL654m --output narration.mp3
```

Before TTS, the script now localizes `story_data.json` for non-English target channels through VectorEngine Gemini using the channel's `translate_prompt`. It translates the story `title`, story `body`, and each comment `body`, preserves usernames/metadata, writes localization metadata into the story JSON, and by default overwrites `--story` so `storyboard_generator.py` and `render.py` consume the translated text. Use `--translated-story-output story_localized_<lang>.json` to keep the original file untouched, `--skip-translation` for an explicit no-localization run, or `--force-translation` to refresh existing localized text.

For karaoke sync, the default narration text mirrors visible card text: title, body, then comment bodies. If `channels.json` defines `comment_tts_voice`, `translator_tts.py` automatically splits narration into role segments: title/body use `tts_voice`, comments use `comment_tts_voice`, then FFmpeg concatenates the segments into one `narration.mp3` and writes a combined `narration.json` with shifted word timings when AI33 returns them. Missing or partial AI33 word timings no longer fail the TTS step; the transcript metadata is saved with `timing_status` and `render.py` falls back to clean slide-progress frames with audio. If a voiceover should explicitly say localized "Comment by user" labels, pass `--include-comment-labels`; that can reduce word-level visual alignment unless the rendered DOM also includes those labels.

Use `--single-voice` to force one voice for the full narration. Use `--comment-voice-id` for a one-off override without editing `channels.json`.

The script sends multipart FormData to:

```text
POST https://api.ai33.pro/v3/text-to-speech
Header: xi-api-key: $AI33_API_KEY
Fields: text, voice_id, model_id, speed, with_transcript, context_chaining, file_name
```

Production channel `voice_id` values must use the ElevenLabs AI33 provider prefix:

```text
elevenlabs_...
```

`channels.json` is the current source of truth for per-channel TTS voice ids. All configured channels now use ElevenLabs-prefixed AI33 voice ids; Edge values should be treated only as historical placeholders. `auto_publish.yml` runs this early preflight before Reddit/Gemini/AI33 spend:

```bash
python3 translator_tts.py --channel acc4 --check-voice-config --require-voice-prefix elevenlabs_
```

The publish workflow remains fail-closed: if either `tts_voice` or `comment_tts_voice` stops using an `elevenlabs_` prefix, it fails early for that channel. Current configured values are:

| Channel | Narrator `tts_voice` | Comment `comment_tts_voice` |
|---|---|---|
| Russia | `elevenlabs_rQOBu7YxCDxGiFdTm28w` | `elevenlabs_ymDCYd8puC7gYjxIamPt` |
| English | `elevenlabs_sB7vwSCyX0tQmU24cW2C` | `elevenlabs_DODLEQrClDo8wCz460ld` |
| Germany | `elevenlabs_aTTiK3YzK3dXETpuDE2h` | `elevenlabs_LB5G0Z4EP98YaEgL654m` |
| LATAM | `elevenlabs_22VndfJPBU7AZORAZZTT` | `elevenlabs_8mBRP99B2Ng2QwsJMFQl` |
| Brazil | `elevenlabs_dX7gRq1dIvLTgUaWpEFn` | `elevenlabs_4r3G9XKliGgVZLKMgjik` |
| France | `elevenlabs_wufFsVwuYBePWKO6dMMN` | `elevenlabs_i6ke7jvmGEVUyV4zjSaT` |
| Italy | `elevenlabs_ImsA1Fn5TNc843fFdz99` | `elevenlabs_RXoaSpLaWTEckJgPUBG3` |

Before public publishing, run short user-approved AI33 sound tests for each active narrator/comment pair. For one-off experiments, pass `--voice-id` / `--comment-voice-id` without editing `channels.json`.

Voice selection is per channel and per narration role. There is no requirement to find one universal voice for all languages; each channel can use its own narrator/comment pair as long as both configured IDs match the target language and start with `elevenlabs_`.

Current ElevenLabs candidates collected from AI33 Voice Library screenshots and metadata readback:

| Raw ElevenLabs ID | AI33 `voice_id` | Verified catalog metadata | Safe channel fit | Do not use for |
|---|---|---|---|---|
| `cCYjmrGZaI86GUJ7F2Nn` | `elevenlabs_cCYjmrGZaI86GUJ7F2Nn` | AI33 readback verified: English `en-US` / `american`, male, middle-aged; also supports Russian `ru-RU` / `ru-standard`, French `fr-FR` / `fr-quebec`, Portuguese `pt-BR` / `pt-brazilian` | Strong candidate for English and Russian; secondary candidate for French/Portuguese if accent is acceptable | LATAM Spanish, German, Italian |
| `sB7vwSCyX0tQmU24cW2C` | `elevenlabs_sB7vwSCyX0tQmU24cW2C` | AI33 readback verified: English `en-US` / `american`, male, middle-aged; name `Jon - Natural Authority` | Active `acc2` English narrator | Pending sound test |
| `nzFihrBIvB34imQBuxub` | `elevenlabs_nzFihrBIvB34imQBuxub` | AI33 readback verified: English `en-US` / `american`, male, young; also supports Russian `ru-RU` / `ru-standard`, French `fr-FR` / `fr-quebec` | English spare/young alternate; possible Russian spare | LATAM Spanish, Brazil Portuguese, German, Italian |
| `DODLEQrClDo8wCz460ld` | `elevenlabs_DODLEQrClDo8wCz460ld` | AI33 readback verified: English `en-US` / `american`, female, middle-aged; name `Lauren - Friendly, Comforting and Soft` | Active `acc2` English comments | Pending sound test |
| `BIvP0GN1cAtSRTxNHnWS` | `elevenlabs_BIvP0GN1cAtSRTxNHnWS` | AI33 readback verified: English `en-GB` / `german`, female, young; also supports Russian `ru-RU` / `standard`, Italian `it-IT` / `standard`; Spanish is `es-ES` / `peninsular` | Candidate for Italian and Russian; possible English character/comment voice only after sound test | LATAM Spanish, Brazil Portuguese, French, German |
| `93nuHbke4dTER9x2pDwE` | `elevenlabs_93nuHbke4dTER9x2pDwE` | AI33 readback verified: French `fr-CA` / `quebec`, male, middle-aged; also supports Portuguese `pt-BR` / `brazilian`, Russian `ru-RU` / `standard`, English `en-US` / `southern`; Spanish is `es-ES` / `peninsular` | French Canada/Québec spare; not main France-standard narrator | LATAM Spanish, German, Italian |
| `wufFsVwuYBePWKO6dMMN` | `elevenlabs_wufFsVwuYBePWKO6dMMN` | AI33 readback verified: French `fr-FR` / `standard`, male, middle-aged; name `Rudy - Narrator` | Active `acc6` France-standard French narrator | Pending sound test |
| `i6ke7jvmGEVUyV4zjSaT` | `elevenlabs_i6ke7jvmGEVUyV4zjSaT` | AI33 readback verified: French `fr-FR` / `parisian`, female, young; name `Emilie - Pro` | Active `acc6` French comments | Pending sound test |
| `ymDCYd8puC7gYjxIamPt` | `elevenlabs_ymDCYd8puC7gYjxIamPt` | AI33 readback verified: Russian `ru-RU` / `standard`, female, middle-aged | Active `acc1` Russian comments | Pending sound test |
| `rQOBu7YxCDxGiFdTm28w` | `elevenlabs_rQOBu7YxCDxGiFdTm28w` | AI33 readback verified: Russian `ru-RU` / `standard`, male, middle-aged | Active `acc1` Russian narrator | Pending sound test |
| `LB5G0Z4EP98YaEgL654m` | `elevenlabs_LB5G0Z4EP98YaEgL654m` | AI33 readback verified: German `de-DE` / `standard`, female, young | Active `acc3` German comments | Pending sound test |
| `aTTiK3YzK3dXETpuDE2h` | `elevenlabs_aTTiK3YzK3dXETpuDE2h` | AI33 readback verified: German `de-DE` / `standard`, male, young | Active `acc3` German narrator | Pending sound test |
| `5KvpaGteYkNayiswuX2h` | `elevenlabs_5KvpaGteYkNayiswuX2h` | AI33 readback verified: German `de-DE` / `standard`, male, old | German spare narrator/character voice; possible authoritative explainer tone | Pending sound test |
| `ImsA1Fn5TNc843fFdz99` | `elevenlabs_ImsA1Fn5TNc843fFdz99` | AI33 readback verified: Italian `it-IT` / `standard`, male, young; name `Davide - Sports Commentator` | Active `acc7` Italian narrator | Pending sound test |
| `RXoaSpLaWTEckJgPUBG3` | `elevenlabs_RXoaSpLaWTEckJgPUBG3` | AI33 readback verified: Italian `it-IT` / `standard`, female, middle-aged; name `Tiziana - Smart, Balanced and Credible` | Active `acc7` Italian comments | Pending sound test |
| `22VndfJPBU7AZORAZZTT` | `elevenlabs_22VndfJPBU7AZORAZZTT` | AI33 readback verified: Spanish, `es-AR`, `latin american`, female, young | Active `acc4` LATAM Spanish narrator | Pending sound test |
| `8mBRP99B2Ng2QwsJMFQl` | `elevenlabs_8mBRP99B2Ng2QwsJMFQl` | AI33 readback verified: Spanish, `es-AR`, `latin american`, male, old | Active `acc4` LATAM Spanish comments | Pending sound test |
| `dX7gRq1dIvLTgUaWpEFn` | `elevenlabs_dX7gRq1dIvLTgUaWpEFn` | AI33 readback verified: Portuguese, `pt-BR`, `brazilian`, male, middle-aged | Active `acc5` Brazil Portuguese narrator | Pending sound test |
| `4r3G9XKliGgVZLKMgjik` | `elevenlabs_4r3G9XKliGgVZLKMgjik` | AI33 readback verified: Portuguese, `pt-BR`, `brazilian`, male, middle-aged | Active `acc5` Brazil Portuguese comments | Pending sound test |

All seven channels now have active ElevenLabs-prefixed narrator/comment pairs in `channels.json`. A single voice ID is only one role; each channel should keep separate narrator and comment voices before production publishing. Do not configure a voice on a channel whose target language is missing from the AI33/ElevenLabs language list.

Verification note: the AI33 metadata endpoint is `GET /v3/voices?provider=elevenlabs&search=<voice_id>`. This confirms catalog labels such as language, locale, accent, gender, and age; it does not synthesize audio, so a short AI33 sound test is still required before public production use.

For no-audio metadata readback through the repository secret, use the manual workflow `.github/workflows/voice_metadata_check.yml`. It calls AI33 voice metadata endpoints with `AI33_API_KEY`, prints only sanitized metadata for requested voice IDs, and does not call `/v3/text-to-speech`.

For audible review, use the manual workflow `.github/workflows/audit_voice_youtube.yml` with `generate_voice_samples=true`. It generates short AI33 samples for the configured narrator/comment voices and uploads them as the `ai33-voice-samples` artifact. This spends AI33 TTS credits but does not call Reddit, VectorEngine, render, or YouTube upload.

Latest sample artifact: run `28457170166` generated all 14 configured narrator/comment samples on 2026-06-30. The downloaded local review page is `build/audit/run_28457170166/ai33-voice-samples/20260630T154616Z/voice_samples_review.html`.

Current candidate coverage:

| Channel | Candidate status |
|---|---|
| `acc1` Russian | Standard Russian narrator/comment pair configured in `channels.json`, pending sound test |
| `acc2` English | US English narrator/comment pair configured in `channels.json`, with one young male spare, pending sound test |
| `acc3` German | Standard German narrator/comment pair configured in `channels.json`, with one spare German male voice, pending sound test |
| `acc4` LATAM Spanish | Spanish Latin-accent narrator/comment pair configured in `channels.json` from user-provided AI33 UI readback, pending sound test |
| `acc5` Brazil Portuguese | Brazilian-accent narrator/comment pair configured in `channels.json` from user-provided AI33 UI readback, pending sound test |
| `acc6` French | France-standard / Parisian narrator/comment pair configured in `channels.json`, with one Québec male spare, pending sound test |
| `acc7` Italian | Standard Italian narrator/comment pair configured in `channels.json`, pending sound test |

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

Live translation and audio generation can spend VectorEngine and AI33 credits, so run them intentionally.

### Live Smoke Result

On 2026-06-29, user-approved local smokes used the gitignored LUNA2 AI33 key without printing or copying it into this repo. The first test submitted an ElevenLabs-prefixed voice id with `[sighs]`, `[laughs]`, and `[whispers]` tags. A second test explicitly sent `model_id=eleven_v3` with `[laughs]` and `[sighs]`; AI33 returned `task_id=08c146ad-82a0-4efb-a4e2-f8ec65254852`, `/v3/task/{task_id}` polling returned `status=done`, and the output file was a valid 5.64s MP3 at `/tmp/reddit_ai33_eleven_v3_laugh.mp3`.

Important distinction: the smoke used an `elevenlabs_...` voice, and current `channels.json` production channel voices are also `elevenlabs_...`. Older Edge placeholders are historical only and should not be reintroduced unless the project explicitly changes provider strategy.

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

SEO/upload handling:
- `youtube_title` is trimmed to YouTube's 100-character limit.
- `youtube_description` is trimmed to 5,000 characters and must include the original Reddit URL.
- `hashtags` are appended to the upload description if Gemini returned them separately.
- `tags` and `seo_keywords` are merged into YouTube tags with duplicate removal and a 25-tag cap.
- `language` is passed to YouTube as `defaultLanguage` and `defaultAudioLanguage` when present.
- Manual `auto_publish.yml` runs default to `privacy_status=unlisted`; scheduled runs should stay `unlisted` until one post-fix live artifact is reviewed end to end.
- `uploader.py --check-channel-only --account-index N` calls `channels.list(mine=true)` and verifies the authenticated channel against `channels.json`; `auto_publish.yml` runs this as an early preflight before Reddit/Gemini/AI33/render spend.
- For a mapping-only audit across all accounts, use `.github/workflows/audit_voice_youtube.yml` with `check_youtube_mapping=true`. It runs `uploader.py --check-channel-only` for `acc1` through `acc7`, uploads per-account logs, and does not continue into Reddit/Gemini/AI33/render/upload.
- Historical blocker: scope-aware audit run `28459324708` proved the then-current `YOUTUBE_REFRESH_TOKEN_ACC1-7` values had only `https://www.googleapis.com/auth/youtube.upload`, so `channels.list(mine=true)` returned `403 insufficient authentication scopes`. Per current user-provided state on 2026-07-02, all seven OAuth credentials/scopes were reissued and verified after that audit. Keep the channel preflight enabled before any spend/upload.
- Before upload, `uploader.py` repeats the same channel check; a mismatch blocks `videos.insert`.
- After upload, `uploader.py` calls `videos.list(part=snippet,status)` to read back channel id, privacy, and language.
- Public oEmbed readback can confirm the uploaded title and channel handle for unlisted videos, but authenticated YouTube Data API readback is still needed for description, tags, language, and final status.

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
- `youtube.readonly` — Read authenticated channel/video metadata for token mapping and post-upload readback
- `youtube.force-ssl` — Manage metadata/thumbnails when that path is enabled
- `yt-analytics.readonly` — Optional future performance stats; not required for the current upload/channel mapping gate

### Reissuing YouTube Refresh Tokens

The existing GitHub Secrets cannot be expanded in place. If an old refresh token
was issued only with `youtube.upload`, adding scopes in Google Cloud does not
change that token. Reissue each account token with consent and replace the
matching GitHub Secret.

Use the helper below from a local shell where `gh` is authenticated to the
`webpot-ru/nebula-core-v3` repository. It does not print the refresh token.

```bash
export YOUTUBE_CLIENT_ID="..."
export YOUTUBE_CLIENT_SECRET="..."

python3 scripts/issue_youtube_refresh_token.py \
  --account-index 1 \
  --update-github-secret
```

Repeat for `--account-index 1` through `7`, choosing the Google account that
owns the exact expected channel shown by the script. The helper requests
`youtube.upload`, `youtube.readonly`, and `youtube.force-ssl` by default. Add
`--include-analytics` only if the analytics-read scope is intentionally needed.

If the secrets are ever replaced again, rerun `.github/workflows/audit_voice_youtube.yml`
with `check_youtube_mapping=true` and `generate_voice_samples=false`. The audit
must show the new scopes and then match every authenticated channel against
`channels.json` before trusting the new token set for public/scheduled publishing.

---

## 9. GitHub Actions Automation

### Dry-Run Render Workflow

`video_dry_run.yml` is the workflow to run before production upload. It can be triggered manually. The current version uses live Reddit and AI33 secrets, so it is not a no-spend fixture-only workflow:

```text
scraper.py
  -> story_data.json
  -> translator_tts.py
  -> narration.mp3 + narration.json
  -> storyboard_generator.py
  -> render.py
  -> final_output.mp4
  -> artifact upload
```

It installs FFmpeg explicitly, verifies `final_output.mp4` with `test -s` and `ffprobe`, then uploads the MP4, story, storyboard, narration, transcript, render story, and preview PNGs as a GitHub Actions artifact.

### Production Publish Workflow

`auto_publish.yml` has passed one end-to-end unlisted live smoke, but public scheduled publishing should still wait for one post-fix unlisted review. The 2026-06-30 smoke verified localization, AI33 narration, audio-aware render, YouTube upload, and history commit, but readback/user review showed videos landing on the wrong channel for the requested account. Per current user-provided state on 2026-07-02, the OAuth/channel mapping issue has been resolved; the next gate is artifact quality review after the render/TTS fixes.

YouTube refresh tokens are no longer the active blocker; the early token preflight still blocks mismatched accounts. After the 2026-07-02 render/TTS fallback fixes, keep the next run `unlisted` until one live artifact is inspected for translated text, voiceover audio, clean UI, and karaoke highlight when AI33 word timings are present.

Planned production flow:
```
scraper.py → story_data.json
    ↓
metadata_generator.py → youtube_metadata.json via VectorEngine
    ↓
translator_tts.py → localized story_data.json + narration.mp3 + narration.json via VectorEngine + AI33
    ↓
translator_tts.py → narration-safe card text; raw URLs become localized "link on screen" phrases
    ↓
storyboard_generator.py → storyboard.json with centered render_slides
    ↓
render.py → final_output.mp4 with audio track + karaoke highlight when usable transcript word timings exist, otherwise clean slide-progress frames with audio
    ↓
uploader.py → channel preflight, YouTube upload, metadata readback
```

`render.py` uses `--orientation auto` by default: narration/storyboard duration up to 180 seconds stays vertical 9:16 for Shorts, and anything longer than 180 seconds becomes horizontal 16:9 for long-form YouTube. The horizontal path keeps the same word-level karaoke treatment on the Reddit card text and does not add side panels or extra captions. Both orientations use larger render-mode text and slide chunking so the card stays readable instead of squeezing a long post onto one screen.

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
| `YOUTUBE_REFRESH_TOKEN_ACC1–7` | ✅ Verified | Per-account YouTube tokens; all 7 channels verified against `channels.json` mappings, including analytics scopes |

| `REDDIT_CLIENT_ID` | ✅ Set | Reddit PRAW OAuth |
| `REDDIT_CLIENT_SECRET` | ✅ Set | Reddit PRAW OAuth |
| `REDDIT_USERNAME` | ✅ Set | Reddit account |
| `REDDIT_PASSWORD` | 🚫 Not needed | Reddit PRAW read-only mode is active |
| `AI33_API_KEY` | ✅ Set | AI33 TTS v3 |
| `VECTORENGINE_API_KEY` | ✅ Set | VectorEngine Gemini and image generation |

Useful scraper budget env vars:
- `MAX_AI_CANDIDATES` — hard cap on Gemini quality checks per scrape; default `12`, dry-run workflow uses `8`.
- `CANDIDATE_LIMIT_PER_SOURCE` — Reddit posts fetched per subreddit/window source; default `25`.
- `MAX_SUBREDDITS_PER_TOPIC` — subreddits scanned per topic family; default `4`.
- `MAX_TIME_WINDOWS_PER_TOPIC` — time windows scanned per topic family in `auto` mode; default `2`.
- `AI_QUALITY_FAIL_OPEN` — default `0`; if VectorEngine fails, candidates are skipped instead of silently publishing.
- `STORY_SIMILARITY_THRESHOLD` — keyword-overlap duplicate threshold; default `0.72`.
- `TOPIC_FATIGUE_LOOKBACK` — recent channel history entries considered for topic fatigue; default `10`.

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

# Trigger one manual publish run as unlisted first, scoped to one topic family
gh workflow run auto_publish.yml --ref main -f channel=acc4 -f time_filter=auto -f topic_family=human_drama -f video_slot=1 -f privacy_status=unlisted

# Do not use privacy_status=public until token-to-channel preflight/readback matches channels.json

# Trigger live GitHub render dry-run manually; this can spend Reddit/Gemini/AI33 provider usage
gh workflow run video_dry_run.yml --ref main

# Check secrets
gh secret list

# Verify a YouTube token maps to the expected channels.json account without uploading
python3 uploader.py --check-channel-only --account-index 4

# Generate narration through AI33 without spending credits
python3 translator_tts.py es --dry-run

# Test topic-family source planning without Gemini spend
AI_QUALITY_CHECK=0 python3 scraper.py --channel acc4 --time auto --max-ai-candidates 0 --output /tmp/story_data_check.json

# Run bounded Gemini quality checks for topic discovery (spends VectorEngine credits)
VECTORENGINE_API_KEY=... python3 scraper.py --channel acc4 --time auto --max-ai-candidates 8

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
- [x] YouTube OAuth secrets exist for all 7 accounts
- [x] YouTube refresh-token mapping reported verified against expected channel handles after the 2026-06-30 scope reissue
- [x] `channels.json` — execution config now includes weighted `topic_mix` per channel
- [x] `scraper.py` — **PRAW OAuth2 + virality scoring + topic-family search + bounded Gemini quality gate**
- [x] `translator_tts.py` switched to AI33 TTS v3, `uploader.py` base script
- [x] `metadata_generator.py` connected to VectorEngine Gemini for SEO metadata
- [x] `thumbnail_generator.py` connected to VectorEngine image generation behind explicit spend confirmation
- [x] `storyboard_generator.py` and `render.py` create a no-spend dry-run `final_output.mp4`
- [x] Slide-based RedditSim rendering: first story screen without comments, comment-only screens, long story chunking, in-text karaoke highlight, and larger render-mode fonts
- [x] GitHub Actions workflow `video_dry_run.yml` renders and uploads a live dry-run MP4 artifact
- [x] GitHub Actions workflow `auto_publish.yml`
- [x] Scrapers research & comparison documentation
- [x] Reddit App registered: **red 2025** (Complex_Lack4476)
- [x] Verified GitHub dry-run rendering (`chonkertalks-dry-run-video` artifact generated)

### 🔄 Next Steps (Priority Order)
- [ ] **1. Run one post-fix unlisted live smoke** and inspect channel, language, translated card text, voiceover audio, clean slide render, karaoke timing, SEO metadata, and uploaded metadata readback before public scheduled publishing.
- [ ] **2. Select final ElevenLabs/MiniMax voices** from AI33 Voice Library for each channel if emotion tags should be default.
- [ ] **3. Channel art** — Generate banners/avatars using Imagen 2 from LUNA 2.
- [ ] **4. Add authenticated uploader readback** for title, description, tags, language, privacy, and channel id after upload.

### 🔮 Future
- [ ] Broader source discovery beyond Reddit: YouTube comments, Google Trends, TikTok/Shorts trend scouts, and RSS/news sources behind explicit spend/API boundaries
- [ ] Custom Chonker cat avatars per language
- [ ] Analytics readback — track best performing content per language
- [ ] Auto A/B test thumbnails
