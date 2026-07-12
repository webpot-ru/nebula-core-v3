# 🚀 nebula-core-v3 — Project Documentation

Agent entrypoint: [`../AGENTS.md`](../AGENTS.md). Read it together with [`PROJECT_STATE.md`](PROJECT_STATE.md) before non-trivial work.

**Internal project name**: `nebula-core-v3`  
**GitHub**: [github.com/lalishka/nebula-core-v3](https://github.com/lalishka/nebula-core-v3) *(private)*  
**Brand**: ChonkerTalks  
**Purpose**: Automated multilingual YouTube story-entertainment publishing pipeline
**Last updated**: 2026-07-10

**Current state for new chats**: read [`PROJECT_STATE.md`](PROJECT_STATE.md) first.

**Current topic decision**: [`topic-strategy-research-2026-07-10.md`](topic-strategy-research-2026-07-10.md) is the source of truth for channel ownership, source lanes, the 90-day plan, evidence boundaries, and validation gates.

**Russian long-form decision**: [`russian-longform-competitor-analysis-2026-07-11.md`](russian-longform-competitor-analysis-2026-07-11.md) records the competitor evidence, long-form product contract, source-duration fit, reuse-risk boundary, and six-video `acc1` pilot.

**Russian horror editorial contract**: [`russian-horror-editorial-system.md`](russian-horror-editorial-system.md) is the canonical source for `acc1` sourcing rights, story shape, editorial ownership, script artifacts, and pre-spend gates.

**Automated acc1 pilot implementation**: [`../specs/acc1-automated-reddit-pilot/README.md`](../specs/acc1-automated-reddit-pilot/README.md) defines the isolated artifact-only slice graph, fail-closed contracts, provider boundaries, and two-pilot GitHub target.

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

`channels.json` is the current execution and strategy config for scripts, voices, scraper inputs, viewer promises, owned content bets, evidence/render contracts, and cadence gates. In the local working tree, all seven channels are `automation_enabled=false`; numeric `topic_mix` arrays are marked candidate-scouting-only or superseded and are not approved publishing weights. These guards do not affect GitHub until a separately approved commit/push.

After the committed-config source review exposed cross-channel substitutions, `acc1`, `acc4`, `acc5`, and `acc7` use single-family `forced_family_validation_only` gates. Their `1.0` values mean "do not substitute another family when this source is empty," not "this topic has proven 100 percent audience performance." All channels remain automation-disabled.

### Strategy Rule

One channel should be defined by **language + viewer promise + tone**, not by a single subreddit or a single narrow topic. Shorts and long-form videos can cover different topics inside one channel if they satisfy the same viewer promise. Topic selection must start from the outside audience job ("why this viewer would click and stay"), then choose source material. Reddit posts are raw material, not the product.

Operational split:
- **Shorts**: fast hook testing, trend response, punchy facts, mini-dramas, mysteries, quizzes.
- **Long-form**: expand proven Shorts topics into 8-18 minute explainers, story documentaries, moral-drama breakdowns, mystery timelines, or compilation-style episodes.
- **Reddit**: one source of story material, especially for human drama and scary stories. It should not be treated as the whole channel concept.

### Channel Ownership

| Channel | Owned viewer promise | Production lane | Status |
|---|---|---|---|
| `acc1` Russian | long themed Reddit horror listening session | 3-6 source-preserving stories in a 45-60 minute compilation | compilation lane in progress |
| `acc2` English | high-concept internet case file: what happened, why people cared, what changed | evidence dossier | evidence lane required |
| `acc3` German | precise explanation of digital systems, scams, privacy, and tech consequences | evidence dossier | evidence lane required |
| `acc4` LATAM Spanish | intimate moral conflict with two sides and a verdict-changing turn | Reddit story card | Reddit pilot candidate |
| `acc5` Brazil Portuguese | human football story about identity, loyalty, pressure, injustice, or comeback | rights-safe evidence dossier | evidence lane required |
| `acc6` French | skeptical web-mystery dossier separating facts, theories, and unknowns | evidence dossier | evidence lane required |
| `acc7` Italian | concrete everyday social absurdity with escalation and a comic reversal | Reddit story card | Reddit pilot candidate |

The detailed owned bets, forbidden bets, cadence gates, and 90-day rollout are in [`topic-strategy-research-2026-07-10.md`](topic-strategy-research-2026-07-10.md).

### Production Lanes

1. **`reddit_horror_compilation`** - required for `acc1`: 3-6 complete Reddit stories, source-preserving Russian editing, per-story disclosure and review, segmented Eleven v3 narration, and a 45-60 minute 16:9 compilation. `r/nosleep` and `r/LetsNotMeet` remain separate series.
2. **`reddit_story_card`** - only complete first-person moral conflict or complete social absurdity for the channels that own those treatments. The current renderer supports this lane.
3. **`evidence_dossier`** - required for facts, science/tech, scams, real mysteries, public-person allegations, internet timelines, and football. It needs independent evidence, an original script, and timeline/evidence visuals; one Reddit card is not sufficient.

### Evidence Basis

- Official YouTube reviews support creator-driven franchises and audience participation in [Hispanic America](https://blog.youtube/intl/es-419/culture-and-trends/listas-eoy/), scripted-reality/family and football demand in [Brazil](https://blog.youtube/intl/pt-br/culture-and-trends/listas-fim-de-ano-2025/), and strong edutainment/explainer demand in [Germany](https://blog.youtube/intl/de-de/creator-and-artist-stories/die-erfolgreichsten-videos-creatorinnen-und-trends-des-jahres-2025/).
- YouTube's next-generation research describes fast, layered audiovisual complexity and participatory narrative culture; the static card is a pilot surface, not a universal format: [YouTube Creative Maximalism](https://blog.youtube/culture-and-trends/next-gen-creativity/).
- YouTube's channel-level inauthentic-content policy makes materially original editorial treatment and substance variation mandatory: [YouTube channel monetization policies](https://support.google.com/youtube/answer/1311392?hl=en).

### Scraper / Source Filtering Rules

For Reddit-derived stories only:
- **Upvotes**: minimum 1,000 unless a market-specific experiment says otherwise.
- **Comments ratio**: high comment/upvote ratio indicates controversy and discussion potential.
- **Time window**: `auto` uses topic-family windows such as `day + week` for fresh drama and `week + month` for mystery/lore; manual `day|week|month|year` is still available for experiments.
- **Body length**: minimum 300 characters for narration depth. Format-specific generation must choose the right source length before adaptation: `shorts` uses complete short source stories, while `long` requires a substantial long source. Production workflows must not cut a selected story body just to fit a runtime.
- **Russian Reddit compilation first**: `acc1` targets 45-60 minutes from 3-6 complete stories. Events/order/endings remain source-preserving; literary Russian cleanup is allowed, artificial plot expansion is not. Shorts are trailer-only after the compilation exists.
- **Topic families**: channels now use weighted `topic_mix` values instead of one flat subreddit list. The scraper has rules for `human_drama`, `dark_curiosity`, `curiosity_facts`, `football_culture`, `internet_lore`, and `visual_comedy`.
- **AI budget**: Gemini quality checks are bounded by `MAX_AI_CANDIDATES` / `--max-ai-candidates`; local Reddit metrics and duplicate guards run before any AI call.
- **Producer gate**: Gemini must reject topics that are merely high-metric Reddit filler. The prompt now scores first-screen hook, discussion potential, Shorts/long-form fit, novelty, character-voice fit, AI-slop risk, source/link dependency, duplicate risk, and legal risk. For `shorts`, it receives the complete short-source body up to the Shorts source-length limit, not the old 800-character preview.
- **No-spend topic review**: `scripts/review_reddit_topics.py` converts a bounded full-body queue into explicit theme clusters and a diverse three-item rights-review shortlist. It is deterministic and advisory: `SHORTLIST_FOR_RIGHTS_REVIEW` is not publication, rights, or quality approval.
- **Outside-in brief**: before scoring the Reddit post, Gemini receives a market/channel producer brief and a `content_bet` brief for the topic family. It must decide whether the idea would be worth pitching even without Reddit metrics, then return packaging fields such as `content_bet`, `audience_job_fit`, `first_screen_promise`, `first_screen_text`, `packaging_thesis`, `why_now`, `shorts_cut`, and `longform_angle`.
- **Evidence-backed hooks**: Gemini must return `hook_evidence` with an exact title/body quote supporting the hook. The scraper writes `producer_queue.json`, ranks all approved candidates by producer score, and only then picks the slot winner.
- **No-invent adaptation**: `story_adapter.py` runs after selection and before metadata/translation. It may tighten, clean, and move a source-backed hook into the opening, but it must preserve facts, point of view, URLs, and timeline. In `--strict-evidence` mode it fails if no hook quote is found in the source text.
- **Network ownership guard**: exact Reddit post ids, normalized story signatures, and similar keyword signatures are blocked across the whole channel network by default. `--allow-cross-channel-reuse` is an explicit escape hatch for a separately approved campaign.
- **Strategy preflight**: `automation_enabled=false` channels fail before Reddit access. `--allow-disabled-channel` is reserved for an approved review and is used by the isolated source-smoke workflow.
- **Velocity scoring**: fresh `day/week` candidates get a small bonus for upvotes/hour and comments/hour, so rising stories can beat older high-total posts.
- **Topic fatigue**: recently repeated topic families receive a penalty so one channel does not publish the same kind of story too many times in a row.
- **Channel exclusions**: channels can define `topic_exclusions` in `channels.json`. `acc1` uses this to block Minecraft/gaming-server topics before Gemini quality checks, because the Russian channel default promise is dark curiosity / human drama / strange facts rather than gaming.

---

## 3. Tech Stack

| Component | Technology |
|---|---|
| Reddit scraping | PRAW (Python Reddit API Wrapper) + OAuth2 |
| AI Translation | Prompt-engineered per-language translation (culturally adapted) |
| Voice synthesis | **AI33 TTS v3** via multipart FormData (`xi-api-key`) |
| AI text routing | Direct **Google Gemini API** (`gemini-3.5-flash` / `gemini-3.1-flash-lite`) via `GOOGLE_GEMINI_API_KEY`, with VectorEngine Gemini fallback |
| Metadata / SEO | Gemini text provider via `vectorengine_client.py` |
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
├── scraper.py                     ← Reddit story fetcher (PRAW OAuth2 + virality + producer queue)
├── story_adapter.py               ← Source-backed no-invent story cleanup / hook adapter
├── metadata_generator.py          ← Gemini YouTube packaging + SEO metadata
├── thumbnail_generator.py         ← VectorEngine image thumbnail generator
├── vectorengine_client.py         ← Shared Gemini text router + VectorEngine image client
├── translator_tts.py              ← AI33 TTS v3 narration generator
├── compilation_translation.py      ← full-story translation + exact local review patches + atomic resume
├── compilation_tts_runner.py       ← chunked Eleven v3 state/resume for long compilations
├── compilation_images.py           ← guarded GPT Image 2 visual per accepted story
├── compilation_storyboard.py       ← local-only 16:9 compilation storyboard
├── compilation_renderer.py         ← deterministic H.264/AAC compilation renderer
├── compilation_metadata.py         ← three-angle packaging for a compilation
├── compilation_qa.py               ← fail-closed compilation artifact gate
├── storyboard_generator.py        ← Deterministic story_data.json → storyboard.json
├── render.py                      ← RedditSim dry-run renderer: storyboard.json → final_output.mp4
├── pre_publish_qa.py              ← Fail-closed audio/evidence/render QA gate
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

This path does **not** call Reddit, AI33, Gemini/VectorEngine, or YouTube. It is only a proof that the project can create an MP4 artifact locally and in GitHub Actions.

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

`storyboard_generator.py` now emits `render_slides` for the simulator. Story/comment text advances as clean centered card screens rather than a scrolling page. For multi-screen posts, the first screen shows the post header/title and hides the footer, middle screens show continuation text only, and only the final story screen shows upvotes/comments/share. In the current production mode, karaoke highlighting is disabled: each slide shows its text cleanly while the narration audio plays. Comment continuations follow the same rule: only the first comment chunk shows the comment header, and only the final chunk shows comment actions. Slide limits are tuned to use the available 9:16 and 16:9 card space, with an anti-orphan merge so a tiny final sentence is not split onto its own mostly empty screen.

`render.py` opens the existing RedditSim UI (`index.html` + `app.js`) in headless Chrome/Chromium, loads `render_story` from `storyboard.json`, samples deterministic slide screenshots, and uses FFmpeg to encode them into `final_output.mp4`. If `narration.mp3` exists, it is merged into the MP4 as an AAC audio track. Current workflows pass `--no-karaoke`, so no yellow karaoke highlight is shown, but they still request `narration.json`; when usable word timings exist, `render.py` uses slide `word_start` boundaries to switch clean static screens in sync with the narration. If timing data is missing, the renderer falls back to word-weighted slide boundaries instead of equal-progress timing. Use `--report render_report.json` so downstream QA can verify render format, frame schedule, duration, transcript use, and audio merge.

`pre_publish_qa.py` is the fail-closed local/upload gate. It reads `story_data.json`, `storyboard.json`, `youtube_metadata.json`, `narration.mp3`, `render_report.json`, and `final_output.mp4`; checks that the MP4 has video/audio streams, audio/video durations match, raw URLs are not spoken in narration fields, source-backed hook evidence exists, story adaptation ran, and metadata language/title length are valid. `auto_publish.yml` and live `video_dry_run.yml` run this before upload/artifact handoff. Karaoke checks run only when `--require-karaoke` is explicitly passed.

Narration text may intentionally differ from display text only for service-safe substitutions. Raw links stay visible on the card while TTS reads a localized "link on screen" phrase. For Russian narration, standalone numeric tokens are expanded only inside `narration_title`, `narration_body`, and `comments[].narration_body`; for example visible `6500+` can be voiced as `более чем шесть тысяч пятьсот`.

The acc1 compilation lane applies a stricter rule. Source URLs live in manifests/descriptions and are not narrated. Inline links become `ссылка на экране`; Markdown labels such as `фото` may become `фото (ссылка на экране)`. Static native Reddit images from `i.redd.it` or `preview.redd.it` are recorded as metadata in `source_media`; arbitrary outbound images, animation and video are rejected. Rendering an image still requires a later bounded downloader plus MIME/size/dimension/checksum validation and a local-only storyboard asset, so capture metadata does not yet mean the image is rendered.

`compilation_narration.py` is the no-spend narration preflight. It builds ordered `intro`, `story_*`, `transition_*`, and `outro` segments, forces `eleven_v3`, removes raw spoken URLs, and reuses the existing Russian integer/percent/plus normalization. Valid 24-hour `HH:MM` tokens are deterministically expanded for Russian narration (`3:15` -> `три часа пятнадцать минут`; whole hours use `ровно`). Invalid times, contextual years, dates, decimals, and currencies still fail closed until the script provides an explicit natural spoken form; they are not sent to AI33 as ambiguous digits.

Render orientation is duration-aware. In default `--orientation auto` mode, videos up to 180 seconds render as vertical Shorts (`1080x1920`, mobile layout), while videos longer than 180 seconds render as horizontal long-form video (`1920x1080`, desktop layout). Horizontal render fills the 16:9 viewport with a clean centered Reddit card and hides editor/sidebar widgets. Override only intentionally with `--orientation vertical` or `--orientation horizontal`.

The GitHub dry-run workflow is `.github/workflows/video_dry_run.yml`. The current workflow fetches a live Reddit story and calls AI33 for narration, so it uses configured secrets and can spend provider credits. It installs FFmpeg, uses the runner browser, builds `storyboard.json`, renders `final_output.mp4`, verifies the file with `ffprobe`, creates preview PNGs, and uploads video, story, storyboard, narration, render report, QA report, and previews as an artifact.

Implementation note: the render card body keeps the typed text span on the same HTML line as its `<p>` container. This is intentional because the body uses `white-space: pre-wrap`; indentation whitespace inside the HTML source would otherwise appear as a visible first-line offset in captured videos.

Current GitHub verification status: previously recovered after the `startup_failure` ownership/billing issue; see `docs/PROJECT_STATE.md` for the latest verified run and artifact notes.

---

## 6. Scraper — Architecture & Plan

### Current Status

> PRAW OAuth2 credentials are supplied only through explicit environment variables. GitHub Actions injects repository secrets into its runner; a local terminal does not inherit them automatically.

### Root Cause: Why All Third-Party Scrapers Also Fail in 2026

| Scraper | Status | Reason |
|---|---|---|
| ScrapiReddit (zero-auth) | ❌ Dead | Reddit blocked unauthenticated endpoints since May 2026 |
| URS | ✅ Works | Uses PRAW with approved OAuth keys |
| **Our scraper.py** | ✅ GitHub source access verified | PRAW OAuth2 succeeded in source-only run `29069048314`; local terminals still require explicit environment credentials. |

### Reddit API Credentials

| Field | Value |
|---|---|
| Client ID | `REDDIT_CLIENT_ID` environment variable / GitHub Secret |
| Client Secret | `REDDIT_CLIENT_SECRET` environment variable / GitHub Secret |
| Script credentials | Optional paired `REDDIT_USERNAME` + `REDDIT_PASSWORD` environment variables / GitHub Secrets |
| Reddit App URL | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) |

#### Required names
```text
REDDIT_CLIENT_ID
REDDIT_CLIENT_SECRET
REDDIT_USERNAME       # optional, but only with REDDIT_PASSWORD
REDDIT_PASSWORD       # optional, but only with REDDIT_USERNAME
```

Never put credential values in `scraper.py`, documentation, chat, or a tracked local env file. For a no-network configuration check, run `python3 scraper.py --check-reddit-config`; it reports only the chosen OAuth mode or missing variable names.

### scraper.py — CLI Usage

```bash
# Production-style channel scans fail closed while automation_enabled=false
python3 scraper.py

# Scan a specific subreddit
python3 scraper.py nosleep

# Validate local credential wiring without calling Reddit
python3 scraper.py --check-reddit-config

# Explicit approved review: bypass the channel hold but do not change history
python3 scraper.py --allow-disabled-channel --no-save-history --channel acc5 --time auto --max-ai-candidates 0 --output /tmp/reddit-story.json

# Run the isolated GitHub source smoke with repository Secrets; no Gemini, AI33, render, YouTube, or git write
gh workflow run reddit_source_smoke.yml --ref main \
  -f channel=acc4 -f video_slot=1 -f topic_family=human_drama \
  -f time_filter=auto -f candidate_limit=10 \
  -f max_subreddits_per_topic=2 -f max_time_windows_per_topic=1 \
  -f review_label=snapshot-a

# Use a specific channel after its automation gate is enabled in channels.json
python3 scraper.py --channel acc4

# Topic-family auto mode: searches weighted topic families and their time windows
python3 scraper.py --channel acc4 --time auto

# Force one topic family for an approved held-channel review
python3 scraper.py --allow-disabled-channel --no-save-history --channel acc4 --topic-family human_drama

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
| `load_channel_config(channel_id)` | Reads the full channel strategy from channels.json |
| `ensure_channel_automation_enabled(...)` | Fails held channels before Reddit access unless an explicit review override is present |

### Virality Scoring Algorithm

| Signal | Points | Why It Matters |
|---|---|---|
| Comments/Upvotes ratio > 10% | +30 | Controversy = viewers argue in your comments → algorithm boost |
| Score > 5,000 | +25 | Proven mainstream appeal |
| Score > 15,000 | +20 | Mega-viral bonus |
| Comments > 1,000 | +15 | High engagement signal |
| Body length > 500 chars | +10 | Enough content for full 5–10 min video |

The final candidate score also includes a small topic-weight boost, time-window freshness adjustment, velocity bonus, and topic-fatigue penalty. Gemini then receives Reddit metrics, velocity, topic-family rules, channel exclusions, format intent, story signature, duplicate context, an outside-in channel brief, and a topic `content_bet` brief. It must return the backward-compatible core fields (`viral_potential`, `novelty`, `duplicate_risk`, `legal_risk`, and `PUBLISH | REWRITE | SKIP`) plus producer fields such as `discussion_potential`, `format_fit`, `character_voice_fit`, `slop_risk`, `source_dependency_risk`, `format_recommendation`, `content_bet`, `audience_job_fit`, `first_screen_promise`, `packaging_thesis`, `why_now`, `shorts_cut`, `longform_angle`, and `producer_angle`.

The quality prompt is intentionally strict. Upvotes are treated as evidence, not permission to publish. Before scoring a Reddit post, the model must ask: "Would this be a worthwhile YouTube idea for this audience if we found it anywhere else?" A candidate should be skipped if it is link/screenshot dependent, only interesting inside a narrow subreddit, too generic for a Reddit-card video, too thin for the requested format, or likely to feel like mass-produced AI content. `REWRITE` is only for candidates with real topic strength but a fixable opening hook.

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

Full-story Gemini translation allows 16,384 output tokens by default instead of 4,096. Override it with `--translation-max-output-tokens` or `GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS` when the selected provider/model supports a different response limit.

`translator_tts.py` now submits narration text to AI33's unified v3 endpoint:

```bash
python3 translator_tts.py es --output narration_es.mp3
python3 translator_tts.py --channel acc4 --output narration_es.mp3
python3 translator_tts.py ru --voice-id elevenlabs_rQOBu7YxCDxGiFdTm28w
python3 translator_tts.py --channel acc3 --comment-voice-id elevenlabs_LB5G0Z4EP98YaEgL654m --output narration.mp3
```

Before TTS, the script now localizes `story_data.json` for non-English target channels through the shared Gemini text provider using the channel's `translate_prompt`. By default `vectorengine_client.py` uses direct Google Gemini when `GOOGLE_GEMINI_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_API_KEY` is present, and falls back to VectorEngine Gemini only when no Google Gemini key is configured. The translation step translates the story `title`, story `body`, and each comment `body`, preserves usernames/metadata, writes localization metadata into the story JSON, and by default overwrites `--story` so `storyboard_generator.py` and `render.py` consume the translated display text. Raw URLs stay visible in the display fields; the script adds narration-only fields such as `narration_body` / `comments[].narration_body` when TTS should say the localized "link on screen" phrase instead of reading the URL aloud. For Russian narration, visible numeric tokens stay unchanged in display fields while narration-only fields spell the number for TTS, for example `6500+` -> `более чем шесть тысяч пятьсот` and `100%` -> `сто процентов`. Use `--translated-story-output story_localized_<lang>.json` to keep the original file untouched, `--skip-translation` for an explicit no-localization run, or `--force-translation` to refresh existing localized text.

The default narration order mirrors visible card text: title, body, then comment bodies. If narration-only fields exist, TTS uses them and the card keeps the display fields, so a voice line like "link on screen" corresponds to an actual visible URL on the card, and Russian numeric display tokens can still be voiced naturally. If `channels.json` defines `comment_tts_voice`, `translator_tts.py` automatically splits narration into role segments: title/body use `tts_voice`, comments use `comment_tts_voice`, then FFmpeg concatenates the segments into one `narration.mp3`. Current workflows request `--with-transcript` for slide timing, but render with `--no-karaoke`, so no yellow word highlights or visible subtitles are shown. `translator_tts.py` accepts AI33/ElevenLabs word timings, character alignment, phrase-level timed text, and inline or linked SRT/VTT subtitle payloads; it converts all usable timing sources into `narration.json` words for `render.py`. Retryable AI33 task errors during multi-voice segment generation are retried with `--tts-retries` and `--tts-retry-delay`. If a voiceover should explicitly say localized "Comment by user" labels, pass `--include-comment-labels`.

Use `--single-voice` to force one voice for the full narration. Use `--comment-voice-id` for a one-off override without editing `channels.json`. Optional provider voice settings can be passed with `--voice-settings-json '{"stability":0.45}'` or `AI33_VOICE_SETTINGS_JSON`, but they should be sound-tested before production because more expressive settings or audio tags can affect pacing and clarity.

For less monotone ElevenLabs/AI33 delivery, the current test recommendation is:

- Keep `model_id=eleven_v3` for multilingual channels.
- Pick native/accent-correct voices first; settings cannot fully fix a weak voice-language match.
- Test `stability=0.35`, `similarity_boost=0.75`, `style=0` for a more expressive read.
- If that is too unstable, move to `stability=0.50`, `similarity_boost=0.75`, `style=0`.
- Avoid making `context_chaining` the default; AI33 documents it as a higher-credit path in this project workflow.
- Do not raise `style` by default. ElevenLabs documents style exaggeration as more resource-heavy and less stable, and recommends keeping it at `0` for most cases.
- For voice samples only, sparse Eleven v3 audio tags such as `[curious]`, `[sighs]`, and `[whispers]` are useful for checking whether a voice can perform. Add them to production narration only after a listening test confirms the voice does not speak the tags aloud.

Manual `video_dry_run.yml` and `auto_publish.yml` runs expose `voice_settings_profile`. Leave it as `default` for unchanged provider behavior, or set it to `creative` for the first emotional test. Scheduled runs still use `default` unless the workflow is changed intentionally.

The script sends multipart FormData to:

```text
POST https://api.ai33.pro/v3/text-to-speech
Header: xi-api-key: $AI33_API_KEY
Fields: text, voice_id, model_id, voice_settings, speed, with_transcript, context_chaining, file_name
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

For audible review, use the manual workflow `.github/workflows/audit_voice_youtube.yml` with `generate_voice_samples=true`. It generates short AI33 samples for the configured narrator/comment voices and uploads them as the `ai33-voice-samples` artifact. This spends AI33 TTS credits but does not call Reddit, Gemini/VectorEngine, render, or YouTube upload. The workflow now exposes `text_style` and `voice_settings_profile`; start with `text_style=emotional` and `voice_settings_profile=creative`, then compare against `natural` if the voice becomes too theatrical or unstable.

Verified `acc1` Eleven v3 comparison: GitHub run `29153420437` used emotional text with the `default` settings profile; run `29153423227` used the same text/voices and `creative` settings. Both manifests recorded `model_id=eleven_v3` and `required_model_id=eleven_v3`, both voice-sample jobs succeeded, and both YouTube mapping jobs were skipped. Use these artifacts for listening comparison; duration/codec validity alone does not determine which performance sounds better.

Local no-spend dry-run:

```bash
python3 scripts/generate_ai33_voice_samples.py --channels acc1 --text-style emotional --voice-settings-profile creative --dry-run
python3 scripts/generate_ai33_voice_samples.py --channels all --text-style emotional --voice-settings-profile natural --dry-run
```

Local audible sample run after explicit approval to spend AI33 credits:

```bash
python3 scripts/generate_ai33_voice_samples.py --channels acc1 --text-style emotional --voice-settings-profile creative --output-dir build/voice_samples
```

Available voice-settings profiles:

| Profile | Sent `voice_settings` | Use |
|---|---|---|
| `creative` | `{"stability":0.35,"similarity_boost":0.75,"style":0}` | First emotional sample pass; more range, more variability |
| `natural` | `{"stability":0.5,"similarity_boost":0.75,"style":0}` | Safer default if creative is too unstable |
| `robust` | `{"stability":0.7,"similarity_boost":0.75,"style":0}` | Consistency check; can sound flatter |
| `default` | omitted | AI33/ElevenLabs provider default |

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

Production and dry-run workflows pass both `--model-id eleven_v3` and `--require-model-id eleven_v3`. The second flag is a pre-spend guard: a v2 override fails before the AI33 request. Successful requests write `tts_request_metadata.json` with the requested model, voice ids, whether voice settings were supplied, and any model id explicitly reported by the provider. `provider_not_reported` means the client request is proven but AI33 did not echo the resolved model; it must not be described as provider-confirmed. `pre_publish_qa.py --require-tts-model eleven_v3` fails when the audit artifact is missing, requests another model, or records a provider mismatch.

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

Live translation and audio generation can spend Gemini quota and AI33 credits, so run them intentionally.

`vectorengine_client.py` is now the shared Gemini text router. For text tasks it prefers direct Google Gemini when `GOOGLE_GEMINI_API_KEY`, `GEMINI_API_KEY`, or `GOOGLE_API_KEY` is present, using `x-goog-api-key` against `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`. If no Google Gemini key is configured, it falls back to `VECTORENGINE_API_KEY` / `VECTOR_ENGINE_API_KEY`. Set `GEMINI_PROVIDER=google` or `GEMINI_PROVIDER=vectorengine` only when you want to force one provider. `GEMINI_RETRIES` controls retry count; `VECTORENGINE_GEMINI_RETRIES` remains accepted for backward compatibility.

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

### Gemini Metadata / SEO

`metadata_generator.py` builds YouTube packaging from `story_data.json`, `producer_queue.json` fields, `editorial_adaptation`, and `channels.json`. It asks Gemini for three honest title/thumbnail/first-screen packaging options, stores them in `packaging_options`, and writes the selected option into the backward-compatible `youtube_title` and `thumbnail_text` fields. For render dry-runs only, `--fallback-on-error` can write conservative marked fallback metadata if Gemini blocks the packaging prompt; do not use that flag for production upload unless fallback SEO is an intentional operator decision.

```bash
# No API spend
python3 metadata_generator.py --story story_data.json --channel acc4 --dry-run

# Live Gemini call
GOOGLE_GEMINI_API_KEY=... python3 metadata_generator.py --story story_data.json --channel acc4 --confirm-spend --output youtube_metadata.json
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

`video_dry_run.yml` is the workflow to run before production upload. It can be triggered manually. The current version uses live Reddit, Gemini, and AI33 secrets, so it is not a no-spend fixture-only workflow. For a vertical Shorts artifact that exercises live topic search/filtering without uploading to YouTube, run it with `content_format=shorts`; this selects only complete short source stories and forces a vertical render. The live dry-run caps the producer quality gate at 12 Gemini candidates so the strict quality gate can skip generic Reddit filler and still reach better candidates; for Shorts, the quality gate sees the full short source body before deciding whether the story is complete. If Gemini blocks the metadata packaging prompt, the dry-run metadata step writes marked fallback metadata and continues so MP4/audio QA can still be inspected. The shared Gemini client immediately falls back to VectorEngine on Google HTTP 429 only when `GEMINI_PROVIDER` is left in auto mode.

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

Manual `auto_publish.yml` runs support `content_format=auto|shorts|long`; the workflow default is `shorts`, and scheduled runs also resolve to `shorts` unless a matrix entry explicitly sets another format. `shorts` now filters candidates before selection: the source body must already be a complete short story, currently up to about 2,400 characters, and comments are not fetched for that run. `long` requires a substantial source body, currently at least about 2,800 characters, keeps the full story, and relies on render auto-orientation to switch videos over 180 seconds to 16:9. Production paths must not use post-selection body trimming; scraper/adapter `--max-body-chars` remains only a deprecated manual safety valve behind `--allow-body-trim`.

YouTube refresh tokens are no longer the active blocker; the early token preflight still blocks mismatched accounts. Keep the next run `unlisted` until one live artifact is inspected for translated text, voiceover audio, clean no-karaoke UI, and uploaded metadata readback.

Planned production flow:
```
scraper.py → story_data.json + producer_queue.json
    ↓
story_adapter.py → source-backed no-invent adapted story_data.json
    ↓
metadata_generator.py → youtube_metadata.json via Gemini text provider
    ↓
translator_tts.py → localized story_data.json + narration-only link placeholders + narration.mp3 via Gemini text provider + AI33
    ↓
storyboard display text keeps visible URLs; TTS says localized "link on screen" phrases
    ↓
storyboard_generator.py → storyboard.json with centered render_slides
    ↓
render.py → final_output.mp4 + render_report.json with audio track and clean static timed-slide visuals
    ↓
pre_publish_qa.py → pre_publish_qa.json fail-closed gate
    ↓
uploader.py → channel preflight, YouTube upload, metadata readback
```

`render.py` uses `--orientation auto` by default: narration/storyboard duration up to 180 seconds stays vertical 9:16 for Shorts, and anything longer than 180 seconds becomes horizontal 16:9 for long-form YouTube. Both orientations use larger render-mode text and slide chunking so the card stays readable instead of squeezing a long post onto one screen. Current workflows pass `--no-karaoke` to disable visual highlights, while still using `narration.json` timing for slide boundaries when available; upload is blocked on audio/adaptation/evidence/metadata/render QA, not on karaoke.

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
| `GOOGLE_GEMINI_API_KEY` / `GEMINI_API_KEY` | Preferred | Direct Google Gemini text calls for topic QA, adaptation, metadata, and translation |
| `VECTORENGINE_API_KEY` | Fallback / image | VectorEngine fallback for Gemini text calls and active provider for thumbnail image generation |

Gemini keys must never be committed or pasted into source files. If a key was shared in chat or logs, rotate it in Google AI Studio and update GitHub Secrets with the new value before production runs.

Useful scraper budget env vars:
- `MAX_AI_CANDIDATES` — hard cap on Gemini quality checks per scrape; default `12`, dry-run workflow uses `12`.
- `CANDIDATE_LIMIT_PER_SOURCE` — Reddit posts fetched per subreddit/window source; default `25`.
- `MAX_SUBREDDITS_PER_TOPIC` — subreddits scanned per topic family; default `4`.
- `MAX_TIME_WINDOWS_PER_TOPIC` — time windows scanned per topic family in `auto` mode; default `2`.
- `AI_QUALITY_FAIL_OPEN` — default `0`; if Gemini fails, candidates are skipped instead of silently publishing.
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
gh workflow run auto_publish.yml --ref main -f channel=acc1 -f time_filter=auto -f topic_family=channel_mix -f video_slot=1 -f privacy_status=unlisted
gh workflow run auto_publish.yml --ref main -f channel=acc1 -f time_filter=auto -f topic_family=channel_mix -f video_slot=1 -f privacy_status=unlisted -f content_format=shorts -f voice_settings_profile=creative

# Do not use privacy_status=public until token-to-channel preflight/readback matches channels.json

# Trigger live GitHub render dry-run manually; this can spend Reddit/Gemini/AI33 provider usage
gh workflow run video_dry_run.yml --ref main
gh workflow run video_dry_run.yml --ref main -f channel=acc1 -f time_filter=auto -f topic_family=channel_mix -f video_slot=1 -f content_format=shorts
gh workflow run video_dry_run.yml --ref main -f channel=acc1 -f time_filter=auto -f topic_family=channel_mix -f video_slot=1 -f content_format=shorts -f voice_settings_profile=creative

# Check secrets
gh secret list

# Verify a YouTube token maps to the expected channels.json account without uploading
python3 uploader.py --check-channel-only --account-index 4

# Generate narration through AI33 without spending credits
python3 translator_tts.py es --dry-run

# Preview emotional AI33 voice sample payloads without spending credits
python3 scripts/generate_ai33_voice_samples.py --channels acc1 --text-style emotional --voice-settings-profile creative --dry-run

# Test topic-family source planning without Gemini spend
AI_QUALITY_CHECK=0 python3 scraper.py --channel acc4 --time auto --max-ai-candidates 0 --output /tmp/story_data_check.json

# Run bounded Gemini quality checks for topic discovery (spends Gemini quota)
GOOGLE_GEMINI_API_KEY=... python3 scraper.py --channel acc4 --time auto --max-ai-candidates 8

# Generate narration through AI33 (spends AI33 credits)
AI33_API_KEY=... python3 translator_tts.py es --output narration_es.mp3

# Generate short emotional voice samples through AI33 (spends AI33 credits)
AI33_API_KEY=... python3 scripts/generate_ai33_voice_samples.py --channels acc1 --text-style emotional --voice-settings-profile creative --output-dir build/voice_samples

# Generate YouTube SEO metadata through Gemini without spending quota
python3 metadata_generator.py --story story_data.json --channel acc4 --dry-run

# Generate YouTube SEO metadata through Gemini (spends Gemini quota)
GOOGLE_GEMINI_API_KEY=... python3 metadata_generator.py --story story_data.json --channel acc4 --confirm-spend

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
- [x] `channels.json` - seven unique viewer promises, owned content bets, evidence/render contracts, cadence gates, and fail-closed strategy status; numeric mixes remain unvalidated/superseded
- [x] `scraper.py` - **PRAW OAuth2 + virality scoring + topic-family search + bounded Gemini producer queue + network-wide dedupe + held-channel preflight**
- [x] `translator_tts.py` switched to AI33 TTS v3, `uploader.py` base script
- [x] `story_adapter.py` connected to the Gemini text provider for source-backed no-invent cleanup
- [x] `metadata_generator.py` connected to the Gemini text provider for packaging options + SEO metadata
- [x] `pre_publish_qa.py` blocks upload when audio, adaptation, evidence, metadata, or render report fail
- [x] `thumbnail_generator.py` connected to VectorEngine image generation behind explicit spend confirmation
- [x] `storyboard_generator.py` and `render.py` create a no-spend dry-run `final_output.mp4`
- [x] Slide-based RedditSim rendering: first story screen without comments, comment-only screens, long story chunking, clean no-karaoke visuals, timed slide boundaries, and larger Reddit-like render-mode fonts
- [x] GitHub Actions workflow `video_dry_run.yml` renders and uploads a live dry-run MP4 artifact
- [x] GitHub Actions workflow `auto_publish.yml`
- [x] Scrapers research & comparison documentation
- [x] Verified GitHub dry-run rendering (`chonkertalks-dry-run-video` artifact generated)

### 🔄 Next Steps (Priority Order)
- [ ] **1. Commit-aware source validation** - record git SHA/config digest, force one family per review, save bounded candidate bodies, and compare two independent snapshots.
- [ ] **2. Validate distinct Reddit-native pilots** for `acc4`, `acc7`, then `acc1`; keep every channel automation-disabled until its gate passes.
- [ ] **3. Build the evidence-dossier lane** for `acc2`, `acc3`, `acc5`, and `acc6` with independent sources, original scripts, timelines, and evidence visuals.
- [ ] **4. Fix delayed-cron routing** so scheduled jobs map from `github.event.schedule` rather than the runner's current UTC hour.
- [ ] **5. Run small unlisted pilots and analytics readback** before any public schedule; collect Engaged views, Stayed to watch, average percentage viewed, shares/comments/subscribers per 1,000 engaged views, and returning viewers.
- [ ] **6. Select final voices and channel art** only after the channel promise and pilot format are accepted.

### 🔮 Future
- [ ] Broader source discovery beyond Reddit: primary sources, official data, Google Trends, rights-safe archives, and RSS/news sources behind explicit spend/API boundaries
- [ ] Custom Chonker cat avatars per language
- [ ] Analytics readback - promote repeated winning story signatures and retire bottom-half content bets
- [ ] Auto A/B test thumbnails

## DESIGN.md Agent Bridge

Status: DESIGN.md agent bridge installed 2026-07-08.

[`../DESIGN.md`](../DESIGN.md) is the project-root visual source for AI/UI agents. It uses the plain Markdown DESIGN.md pattern from https://github.com/VoltAgent/awesome-design-md, but it does not replace this documentation index or the topic-specific source-of-truth documents. For visual/frontend work, read `AGENTS.md`, this `docs/README.md`, `docs/PROJECT_STATE.md`, the relevant topic document, and then `DESIGN.md`.
