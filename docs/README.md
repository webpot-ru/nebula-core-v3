# 🚀 nebula-core-v3 — Project Documentation

Agent entrypoint: [`../AGENTS.md`](../AGENTS.md). Read it together with [`PROJECT_STATE.md`](PROJECT_STATE.md) before non-trivial work.

**Internal project name**: `nebula-core-v3`  
**GitHub**: [github.com/webpot-ru/nebula-core-v3](https://github.com/webpot-ru/nebula-core-v3) *(private)*
**Brand**: ChonkerTalks  
**Purpose**: Automated multilingual YouTube story-entertainment publishing pipeline
**Last updated**: 2026-07-18

**Current state for new chats**: read [`PROJECT_STATE.md`](PROJECT_STATE.md) first.

**Current topic decision**: [`topic-strategy-research-2026-07-10.md`](topic-strategy-research-2026-07-10.md) is the source of truth for channel ownership, source lanes, the 90-day plan, evidence boundaries, and validation gates.

**Current Russian channel decision**: [`acc1-russian-reddit-story-strategy-2026-07-13.md`](acc1-russian-reddit-story-strategy-2026-07-13.md) is the canonical viewer promise, SAGA/BUNDLE/THREAD contract, six-slot daily pilot matrix, S-tier target gates, brand package, and visual/thumbnail system for `acc1`.

**Acc1 production-candidate review**: [`acc1-visual-qa-checklist.md`](acc1-visual-qa-checklist.md) is the human-facing visual and editorial gate for a rendered MP4; it complements technical media QA and never authorizes publication.

**Acc1 cinematic implementation plan**: [`acc1-cinematic-production-plan-2026-07-16.md`](acc1-cinematic-production-plan-2026-07-16.md) defines the staged full-screen scene-motion and narration/mix migration, the compatibility boundary with the current Reddit/Chonker renderer, and the evidence required before cinematic can become a default.

**Acc1 editorial motion implementation and visual history**: [`acc1-editorial-motion-v1.md`](acc1-editorial-motion-v1.md) is the source of truth for the HyperFrames renderer, the six pilot-bound adult-animated-comic profiles, their deterministic anti-template layout repertoires, provider spend ceiling and local proof. The locked reference is [`assets/acc1-adult-animation-six-series-v1.png`](assets/acc1-adult-animation-six-series-v1.png). Earlier collage and Ink & Gouache work remains technical history only, not the future art direction.

**Acc1 current web-comic candidate**: root [`../frame.md`](../frame.md) and [`acc1-cinematic-ink-webtoon-v1.md`](acc1-cinematic-ink-webtoon-v1.md) record the new `cinematic_ink_webtoon_v1` style, exact palette, text rules, image density and guided panel-camera language. It is a local candidate pending an actual pilot review; it does not yet replace the implemented six-series profile or production default.

**Acc1 first-release preparation**: [`acc1-first-release-preproduction-v1.md`](acc1-first-release-preproduction-v1.md) records the no-spend human source review, four-story order, source-faithful Russian treatment, character locks and 68-image plan derived from the successful source-only artifact of run `29757914575`. It is not a production or publication authorization.

The local first-release image contract registers `cinematic_ink_webtoon_v1`
under `editorial_motion_v1` and accepts explicit even per-story image targets.
The locked allocation is `18 / 18 / 16 / 16` scene plates, with one separately
budgeted thumbnail: 69 maximum image calls, no automatic retry. This enlarged
ceiling is not provider-spend approval.

The dedicated fixed-input command is:

```bash
python scripts/run_acc1_fixed_first_release.py \
  --output-dir build/acc1-fixed-first-release
```

Without `--produce` this performs a no-network preflight and proves the exact
provider envelope: 68 scene images, one thumbnail, zero automatic image
retries and 61 AI33 narration tasks. The corresponding manual workflow is
`.github/workflows/acc1_fixed_first_release.yml`. Its production step requires
three explicit confirmations and contains no Reddit, Gemini, OpenAI or YouTube
credentials or calls. `--produce --confirm-image-ai33-spend` is spend-enabled
and must not be run locally or in GitHub without exact authorization.

**Russian dark-series references**: [`russian-longform-competitor-analysis-2026-07-11.md`](russian-longform-competitor-analysis-2026-07-11.md) and [`russian-horror-editorial-system.md`](russian-horror-editorial-system.md) remain the specialized evidence/editorial contracts for the horror series; they no longer define the whole `acc1` channel.

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

After the committed-config source review exposed cross-channel substitutions, `acc4`, `acc5`, and `acc7` keep single-family `forced_family_validation_only` gates. `acc1` now has a broad SAGA/BUNDLE/THREAD pilot contract; its old `dark_curiosity=1.0` array is marked `superseded_pending_rebuild` rather than being presented as an audience weight. The exact daily factory reads the six configured pilot rows and never uses that legacy numeric array as a fallback. All channels remain automation-disabled.

### Strategy Rule

One channel should be defined by **language + viewer promise + tone**, not by a single subreddit or a single narrow topic. Shorts and long-form videos can cover different topics inside one channel if they satisfy the same viewer promise. Topic selection must start from the outside audience job ("why this viewer would click and stay"), then choose source material. Reddit posts are raw material, not the product.

Operational split:
- **Shorts**: fast hook testing, trend response, punchy facts, mini-dramas, mysteries, quizzes.
- **Long-form**: expand proven Shorts topics into 8-18 minute explainers, story documentaries, moral-drama breakdowns, mystery timelines, or compilation-style episodes.
- **Reddit**: one source of story material, especially for human drama and scary stories. It should not be treated as the whole channel concept.

### Channel Ownership

| Channel | Owned viewer promise | Production lane | Status |
|---|---|---|---|
| `acc1` Russian | compelling Reddit stories, confessions, and discussions in Russian | BUNDLE (2-5 complete stories), SAGA (one complete story), or THREAD (8-15 responses); horror is one series | daily factory implemented locally; new workflow/provider artifact not yet live-verified |
| `acc2` English | high-concept internet case file: what happened, why people cared, what changed | evidence dossier | evidence lane required |
| `acc3` German | precise explanation of digital systems, scams, privacy, and tech consequences | evidence dossier | evidence lane required |
| `acc4` LATAM Spanish | intimate moral conflict with two sides and a verdict-changing turn | Reddit story card | Reddit pilot candidate |
| `acc5` Brazil Portuguese | human football story about identity, loyalty, pressure, injustice, or comeback | rights-safe evidence dossier | evidence lane required |
| `acc6` French | skeptical web-mystery dossier separating facts, theories, and unknowns | evidence dossier | evidence lane required |
| `acc7` Italian | concrete everyday social absurdity with escalation and a comic reversal | Reddit story card | Reddit pilot candidate |

The detailed owned bets, forbidden bets, cadence gates, and 90-day rollout are in [`topic-strategy-research-2026-07-10.md`](topic-strategy-research-2026-07-10.md).

### Production Lanes

1. **`acc1_bundle`** - 4-5 complete relationship/family stories or 3-5 complete work/money/justice stories, 18-30 minutes aggregate, with no unrelated comment coda.
2. **`acc1_saga`** - one complete strange/dark/unexplained Reddit story with available authored updates, 18-30 minutes, source-preserving Russian treatment, original framing, scene direction, and three packaging concepts.
3. **`acc1_thread`** - one prompt plus 8-15 complete diverse responses, 15-25 minutes. `acc1_thread_collector.py` implements the deterministic manifest and `acc1_thread_source.py` provides the bounded read-only PRAW adapter with exact pillar-specific search queries.
4. **`reddit_horror_compilation`** - retained specialized dark-series lane: 3-6 complete stories and 45-60 minutes. `r/nosleep` and `r/LetsNotMeet` remain separate truth modes.
5. **`reddit_story_card`** - only complete first-person moral conflict or complete social absurdity for the channels that own those treatments. The current renderer supports this lane.
6. **`evidence_dossier`** - required for facts, science/tech, scams, real mysteries, public-person allegations, internet timelines, and football. It needs independent evidence, an original script, and timeline/evidence visuals; one Reddit card is not sufficient.

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
- **Russian six-slot pilot first**: `acc1` interleaves BUNDLE relationships, THREAD confessions, BUNDLE work/justice, THREAD professions, SAGA dark/unexplained, and THREAD dark/unexplained. Events/order/endings remain source-preserving; natural Russian translation cleanup is allowed, artificial plot expansion is not. The legacy 45-60 minute compilation remains a dark-series option, not the channel-wide default. Shorts are trailer-only after the long episode exists.
- **Topic families**: channels now use weighted `topic_mix` values instead of one flat subreddit list. The scraper has rules for `human_drama`, `dark_curiosity`, `curiosity_facts`, `football_culture`, `internet_lore`, and `visual_comedy`.
- **AI budget**: Gemini quality checks are bounded by `MAX_AI_CANDIDATES` / `--max-ai-candidates`; local Reddit metrics and duplicate guards run before any AI call.
- **Producer gate**: Gemini must reject topics that are merely high-metric Reddit filler. The prompt now scores first-screen hook, discussion potential, Shorts/long-form fit, novelty, character-voice fit, AI-slop risk, source/link dependency, duplicate risk, and legal risk. For `shorts`, it receives the complete short-source body up to the Shorts source-length limit, not the old 800-character preview.
- **No-spend topic review**: `scripts/review_reddit_topics.py` checksum-binds a bounded full-body queue and deterministic review. For exact acc1 SAGA pilots it verifies the canonical source plan, allowed subreddit, 2,340-3,900 source-word range, viewer-promise pillar, truth mode, source completeness, payoff evidence, link/screenshot/native-media independence, and full-body hash. Runtime word counting is identical in scraper, review, and greenlight binding, including dates, ages, and amounts. `SAGA_SOURCE_ELIGIBLE_FOR_GREENLIGHT` means only that the source may enter a human greenlight; it is not publication, rights, or creative-quality approval. When `AI_QUALITY_CHECK=0`, scraper quality state is `UNREVIEWED`, never `PUBLISH`.
- **Outside-in brief**: before scoring the Reddit post, Gemini receives a market/channel producer brief and a `content_bet` brief for the topic family. It must decide whether the idea would be worth pitching even without Reddit metrics, then return packaging fields such as `content_bet`, `audience_job_fit`, `first_screen_promise`, `first_screen_text`, `packaging_thesis`, `why_now`, `shorts_cut`, and `longform_angle`.
- **Evidence-backed hooks**: Gemini must return `hook_evidence` with an exact title/body quote supporting the hook. The scraper writes `producer_queue.json`, ranks all approved candidates by producer score, and only then picks the slot winner.
- **No-invent adaptation**: `story_adapter.py` runs after selection and before metadata/translation. It may tighten, clean, and move a source-backed hook into the opening, but it must preserve facts, point of view, URLs, and timeline. In `--strict-evidence` mode it fails if no hook quote is found in the source text.
- **Network ownership guard**: exact Reddit post ids, normalized story signatures, and similar keyword signatures are blocked across the whole channel network by default. `--allow-cross-channel-reuse` is an explicit escape hatch for a separately approved campaign.
- **Strategy preflight**: `automation_enabled=false` channels fail before Reddit access. `--allow-disabled-channel` is reserved for an approved review and is used by the isolated source-smoke workflow.
- **Velocity scoring**: fresh `day/week` candidates get a small bonus for upvotes/hour and comments/hour, so rising stories can beat older high-total posts.
- **Topic fatigue**: recently repeated topic families receive a penalty so one channel does not publish the same kind of story too many times in a row.
- **Channel exclusions**: channels can define `topic_exclusions` in `channels.json`. `acc1` blocks Minecraft/gaming-server topics before any AI quality check because they do not fit its five-pillar Russian Reddit-story promise.

### Exact acc1 source-review commands

The SAGA command below performs a bounded live Reddit read but no Gemini, AI33, image, render, or YouTube call. Run it only after the exact Reddit-read scope is approved. `--pilot-id` owns the family, format, pillar, and subreddit plan; do not also pass a conflicting `--topic-family` or `--format-intent`.

```bash
AI_QUALITY_CHECK=0 python3 scraper.py \
  --channel acc1 \
  --pilot-id pilot_01 \
  --time auto \
  --max-ai-candidates 0 \
  --candidate-limit 10 \
  --comment-limit 0 \
  --allow-disabled-channel \
  --include-source-body-in-queue \
  --no-save-history \
  --producer-queue-output /tmp/acc1-pilot-01-queue.json \
  --output /tmp/acc1-pilot-01-story.json

python3 scripts/review_reddit_topics.py \
  --queue /tmp/acc1-pilot-01-queue.json \
  --output /tmp/acc1-pilot-01-review.json \
  --top-n 6

python3 scripts/build_acc1_greenlight_template.py \
  --queue /tmp/acc1-pilot-01-queue.json \
  --review /tmp/acc1-pilot-01-review.json \
  --output /tmp/acc1-pilot-01-greenlight-draft.json
```

The generated greenlight is intentionally `DRAFT_BLOCKED`; a human must supply the three packaging concepts, source-backed cold open, story beats, originality plan, scores, and decisions. Binding validation requires the same exact queue and review:

```bash
python3 acc1_story_strategy.py \
  --channels channels.json \
  --pilot-id pilot_01 \
  --source-queue /tmp/acc1-pilot-01-queue.json \
  --topic-review /tmp/acc1-pilot-01-review.json \
  --greenlight /tmp/acc1-pilot-01-greenlight.json
```

The THREAD adapter is separately bounded and read-only. It never expands `MoreComments`, scans only the configured top-level response limit, and writes a raw snapshot plus checksum-bound manifest:

```bash
python3 acc1_thread_source.py \
  --confirm-reddit-read \
  --subreddit AskReddit \
  --time-filter month \
  --candidate-limit 10 \
  --response-scan-limit 50 \
  --max-responses 15 \
  --snapshot-output /tmp/acc1-thread-snapshot.json \
  --manifest-output /tmp/acc1-thread-manifest.json
```

---

## 3. Tech Stack

| Component | Technology |
|---|---|
| Reddit scraping | PRAW (Python Reddit API Wrapper) + OAuth2 |
| AI Translation | Prompt-engineered per-language translation (culturally adapted) |
| Voice synthesis | **AI33 TTS v3** via multipart FormData (`xi-api-key`) |
| AI text routing | Direct **Google Gemini API** (`gemini-3.5-flash` / `gemini-3.1-flash-lite`) via `GOOGLE_GEMINI_API_KEY`, with VectorEngine Gemini fallback |
| Metadata / SEO | Gemini text provider via `vectorengine_client.py` |
| Thumbnail image generation | Deterministic local Cyrillic overlay, or **VectorEngine image** (`gpt-image-2`) via explicit `--confirm-spend` |
| Dry-run video rendering | RedditSim headless Chrome/Chromium lane plus acc1 Pillow/FFmpeg Reddit-pages lane |
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
├── acc1_story_strategy.py          ← exact six-pilot source/greenlight contract
├── acc1_thread_collector.py        ← deterministic full-response THREAD manifest
├── acc1_thread_source.py           ← bounded read-only PRAW adapter for THREAD
├── acc1_release_gate.py            ← checksum-bound unlisted-review gate; never publication authorization
├── story_adapter.py               ← Source-backed no-invent story cleanup / hook adapter
├── metadata_generator.py          ← Gemini YouTube packaging + SEO metadata
├── thumbnail_generator.py         ← local Cyrillic overlay or explicitly paid VectorEngine base image
├── vectorengine_client.py         ← Shared Gemini text router + VectorEngine image client
├── translator_tts.py              ← AI33 TTS v3 narration generator
├── compilation_translation.py      ← full-story translation + exact local review patches + atomic resume
├── compilation_tts_runner.py       ← chunked Eleven v3 state/resume for long compilations
├── compilation_images.py           ← guarded 3-5 source-backed scene visuals per accepted story
├── compilation_storyboard.py       ← cumulative Reddit-pages storyboard + checksum-bound background
├── compilation_renderer.py         ← deterministic 1920x1080 H.264/AAC Reddit-pages renderer
├── compilation_metadata.py         ← three-angle packaging for a compilation
├── compilation_qa.py               ← fail-closed voice/text/background/video/thumbnail QA
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

`compilation_narration.py` is the no-spend narration preflight. It builds ordered `intro`, `story_*`, `transition_*`, and `outro` segments, forces `eleven_v3`, removes raw spoken URLs, and reuses the existing Russian integer/percent/plus normalization. Valid 24-hour `HH:MM` tokens are deterministically expanded for Russian narration (`3:15` -> `три часа пятнадцать минут`; whole hours use `ровно`); the US emergency service `911` is deterministically voiced as `девять один один`. Invalid times, contextual years, dates, decimals, and currencies still fail closed until the script provides an explicit natural spoken form; they are not sent to AI33 as ambiguous digits.

`compilation_tts_runner.py` persists every AI33 task ID before polling and checksum-binds each completed MP3. Artifact resume restores the state plus finished audio, polls existing `SUBMITTED` tasks before any new submission, and applies bounded exponential backoff to retryable HTTP 500/502/503/504 polling failures. Non-retryable provider errors, plan/hash changes, model mismatches, missing task IDs, and checksum changes remain fail-closed.

The first complete artifact-only compilation (`29184260452`) proves the technical 54-minute provider-to-MP4 path, not publish readiness. Its eight-slide static storyboard is sufficient for codec/audio/integrity QA but insufficient for retention-focused long-form horror. Before any distribution pilot, split accepted narration into source-backed scenes and provide materially more frequent visual changes through distinct scene assets, controlled crop/motion variants, or both; retain the no-invent and per-story review contracts.

The current production-oriented acc1 surface is `compilation_storyboard.py` -> `compilation_renderer.py` -> `compilation_qa.py`. It builds cumulative Reddit pages with exact narration coverage: old lines keep fixed coordinates, metadata/title appear only on page one, continuation pages do not repeat the title, and vector upvote/comment/share actions appear exactly once after the final chunk of each `story-*` segment. Actions are forbidden on intro, transitions, intermediate story chunks, and outro. The first screen is a special `story_title` Reddit-card mode: it shows the real first post title and exact source header while the compact spoken intro runs, so no greeting or generic channel promise is printed as faux post text; long source titles can use up to five compact lines only in this mode. A local MP4 background may be supplied only from the artifact root; its checksum and use are bound through the storyboard, creative manifest, render report, and QA. The factory also copies and checksum-binds the approved `brand_sting`, transparent `brand_cta`, and full-frame `brand_outro`: they are overlaid after the cold open, at the first-story midpoint, and over the final six narration seconds respectively. Branding-asset audio is always discarded, so narration duration and synchronization remain unchanged. QA binds each overlay's checksum, start, duration and audio-discard receipt in addition to the configured voice, actual H.264/AAC MP4, actual 1280x720+ thumbnail, text timing/coverage, and slide-duration ceiling.

The approved loop is now stored at `assets/acc1/video/chonker-reading-loop-v1.mp4` with a checksum manifest beside it. Both acc1 compilation workflows copy it into the run artifact root and pass it to the storyboard; the renderer maps only its video stream and reports that source audio was discarded. Long stories request an explicit 3-5 source-backed images. Storyboard scheduling prefers exact editorial story beats and otherwise uses deterministic word-position scenes, keeping the image stable through page rollover. The image and its readability shade end at `mascot_safe_x=1040` with a feathered boundary, leaving the cat layer unchanged. `compilation_qa.py` verifies scene counts/hashes/stability, the exact visual contract, background-audio discard, and the mascot-safe boundary. Its planned 12-second page target has a narrow `12.25s` hard ceiling for a real word-aligned AI33 punctuation boundary; it does not allow materially slow static pages. These workflow changes are locally tested but not GitHub-verified.

Story-page chrome must preserve Reddit source identity rather than localize it. `compilation_storyboard.py` carries exact `r/subreddit`, optional `u/author`, score, and comment count from `source_snapshot`. `compilation_renderer.py` uses separate transparent current-Reddit-style vote, comment, and share pills with thin white outlines, white icons/text, and compact `K`/`M` metrics only when the source snapshot contains an integer value; it never invents a translated community, relative time, engagement count, award, or overflow action. Missing vote/comment metrics use neutral English action labels. The final controls are visible only on the completed story state and receive at least a 3.5-second storyboard hold. First pages allow up to 48 words / 340 characters and continuation pages up to 62 words / 440 characters so the text uses the lower part of the frame without colliding with the mascot or action controls. Timed narration chunks prefer comma/semicolon/colon/dash clause boundaries and allow up to 22 words, reducing rapid changes and orphaned phrase fragments. When valid AI33 alignment is available, each new text state starts 80 ms before the next aligned spoken word to absorb video frame quantization; AI33 timing remains the source of truth. Intro, transitions, and outro retain their separate presentation modes, except the first-screen `story_title` card described above.

Two different no-spend proofs must not be confused. `scripts/build_acc1_visual_proof_fixture.py` is a long-text layout stress test and now generates silence; it is not for judging pacing, voice, or story quality. `scripts/build_acc1_format_review_fixture.py` builds a human-paced synthetic preview with the approved cat loop and macOS system speech. Its output proves presentation behavior only and explicitly does not prove Reddit source selection or the production voice.

The current hardened SAGA path intentionally has no comments: both compilation workflows use `--comment-limit 0`. `acc1_story_strategy.resolve_comment_plan()` records the next contract: `narrative_story` uses no comments; an explicit `question_prompt` may use 2-4 selected answers; THREAD requires 8-15 responses and refuses a narrative source. The old `fetch_top_comments()` route is not acceptable because it truncates bodies and does not preserve the full provenance contract. Selected answers require exact comment/post/parent IDs, author, integer score, full body and SHA-256, official permalink, and retrieval snapshot hash. Reject deleted, removed, truncated, duplicate, link/media-dependent, generic-reaction-only, irrelevant, unsafe, and story-restating comments. Production THREAD responses additionally require 80-650 source words each, deterministic prompt relevance, high-confidence safety/PII clearance, at least three selected editorial roles, and a 40% cap on any one role; score cannot override a blocker. Comment TTS binds `elevenlabs_MOgsVr0EwwxqQs5cNDhu` only when the resolved plan requires it and fails closed rather than falling back to the narrator.

`scripts/build_acc1_creative_review_template.py` creates a checksum-bound human review with every creative acceptance false by default. For historical compilation artifacts, `acc1_release_gate.py` joins exact source/greenlight evidence, technical media QA, thumbnail manifest, creative review, and actual file hashes; that legacy path tops out at `READY_FOR_UNLISTED_REVIEW`. The same gate now also accepts the v2 daily-factory artifact plus a completed version-3 creative review and `acc1_rights_manifest.py` evidence. The factory path tops out at `READY_FOR_PRIVATE_REVIEW`, keeps both `publication_authorized=false` and `upload_authorized=false`, and requires a separate exact private-upload authorization.

```bash
python3 scripts/build_acc1_creative_review_template.py \
  --video final-output.mp4 \
  --thumbnail youtube-thumbnail.png \
  --output creative-review.json

python3 acc1_release_gate.py \
  --strategy-report strategy-report.json \
  --greenlight-report greenlight-report.json \
  --media-qa compilation-qa.json \
  --thumbnail-manifest thumbnail-report.json \
  --creative-review creative-review.json \
  --video final-output.mp4 \
  --thumbnail youtube-thumbnail.png \
  --output release-gate.json
```

For a daily-factory artifact, first generate and complete the fail-closed rights template outside the artifact directory. Sensitive agreement text stays in approved storage; the manifest contains only an opaque evidence locator and SHA-256. Then run the factory-aware gate:

```bash
python3 acc1_rights_manifest.py template \
  --episode-plan artifact/episode-plan.json \
  --source-queue artifact/source-queue.json \
  --output rights-manifest.json

python3 acc1_release_gate.py \
  --factory-artifact-root artifact \
  --factory-creative-review creative-review.json \
  --rights-manifest rights-manifest.json \
  --source-run-id EXACT_FACTORY_RUN_ID \
  --output release-gate.json
```

The bounded acc1 emotion-video proof uses `scripts/generate_ai33_voice_samples.py --roles narrator --with-transcript` plus `scripts/render_emotion_video_sample.py`. AI33 subtitle/alignment data is normalized through the existing timing parser and grouped into short on-screen phrases; if the provider returns no usable timing, the report explicitly marks an estimated fallback. In `reddit_pages` mode the renderer precomputes final wrapping and reveals timed prefixes within fixed lines, so old text neither moves nor flashes. This mode fails closed unless `--font-dir` contains official Reddit Sans. The Chonker-right layout uses meta/title/body/action sizes 28/46/48/27 px, 62 px body-line steps, a 44-character measure, and 520/640-character page capacities. Avatar/username/time appear only on page one; the vote/reply/share/overflow row appears only for the final 3.2 seconds and sits 84 px below the last body line. The exact values are repeated in `emotion-video-report.json`.

Live proof `29186076815` confirmed that AI33 can return usable real word timings for the acc1 narrator. Caption grouping should prefer punctuation boundaries after at least four words, then use word/character ceilings only as safety limits; this avoids splitting semantic units such as spoken clock times. Visual review also established that the already-dark horror art needs only a light readability grade rather than heavy additional darkening.

`scripts/render_emotion_video_sample.py --style reddit_pages` is the earlier direct-background presentation proof. Page one owns the subreddit/author line and title; timed phrases append into individually positioned stable lines without an opaque card; continuation pages omit the title. The proof's ending action row follows the last visible line instead of remaining pinned to the viewport bottom. Production action placement is governed by the stricter per-story contract above.

The proof renderer accepts either a still image or a short MP4 background. MP4 inputs are looped to the narration duration and only their video stream is mapped; narration audio always comes from the verified AI33 sample. Use `--reddit-line-chars 44` for the Chonker-right / text-left composition so larger text uses more horizontal space while staying clear of the mascot; the full-width competitor-like layout keeps the default 76-character measure.

An optional `--story-image` adds a still behind only the left 1180x1080 Reddit-text region. `--story-image-start` and `--story-image-end` bound its screen time; the renderer applies a slow center zoom, 0.8-second alpha fades, brightness `-0.10`, saturation `0.78`, blur `1:1`, and 70% opacity before drawing the stable ASS text above it. A 320 px horizontal alpha feather dissolves the image from x=760 to x=1080 so the composited layer does not darken the mascot's left edge or paw. This is the deterministic no-spend compositing path for future story-beat imagery; provider generation and multi-image semantic scheduling remain separate unimplemented gates.

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
python3 translator_tts.py ru --voice-id elevenlabs_JBFqnCBsd6RMkjVDRZzb
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
- Current Russian voice contract: `elevenlabs_JBFqnCBsd6RMkjVDRZzb` is the male primary narrator and `elevenlabs_MOgsVr0EwwxqQs5cNDhu` is the female comment voice. Use provider speed `1.0`, plain narration text and no emotion/audio tags. Locally accelerated or tagged proofs are comparison artifacts and must not be treated as production settings.

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
| Russia | `elevenlabs_JBFqnCBsd6RMkjVDRZzb` | `elevenlabs_MOgsVr0EwwxqQs5cNDhu` |
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
| `ymDCYd8puC7gYjxIamPt` | `elevenlabs_ymDCYd8puC7gYjxIamPt` | AI33 readback verified: Russian `ru-RU` / `standard`, female, middle-aged | Historical `acc1` comment alternate | Superseded by user-selected `MOgs...` |
| `rQOBu7YxCDxGiFdTm28w` | `elevenlabs_rQOBu7YxCDxGiFdTm28w` | AI33 readback verified: Russian `ru-RU` / `standard`, male, middle-aged | Historical `acc1` narrator alternate | Superseded by user-selected `JBF...` |
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

`thumbnail_generator.py` supports two separate modes. `--base-image` performs a deterministic local Cyrillic overlay and can write a checksum/dimension manifest without any provider call. A generated base image still uses `youtube_metadata.json.thumbnail_prompt` and VectorEngine only after explicit spend confirmation:

```bash
# No provider call; payload preview only
python3 thumbnail_generator.py --metadata youtube_metadata.json --dry-run

# No provider call; real local thumbnail and verification report
python3 thumbnail_generator.py \
  --metadata youtube_metadata.json \
  --base-image thumbnail-base.png \
  --output youtube-thumbnail.png \
  --report thumbnail-report.json

# Paid image generation
python3 thumbnail_generator.py \
  --metadata youtube_metadata.json \
  --confirm-spend \
  --output youtube-thumbnail.png \
  --report thumbnail-report.json
```

The default image model is `gpt-image-2`, default size `1536x864`. The report records status, output checksum, dimensions, mode, and whether a provider was called. Provider image generation is intentionally not run automatically.

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

### acc1 Daily Review-Ready Episode Factory

The current local first-release editorial packet is documented in
[`acc1-first-release-preproduction-v1.md`](acc1-first-release-preproduction-v1.md).
Its unsent author-permission template and exact outreach queue are in
[`acc1-first-release-rights-outreach-v1.md`](acc1-first-release-rights-outreach-v1.md).
The first Russian narration draft is stored at
`../specs/acc1-first-release-v1/narration-draft-ru.md`; it covers all four
retained stories but is not independently source-reviewed, provider-reviewed or
approved for TTS. Author outreach is deliberately not being pursued for this
release by owner decision; missing permission evidence remains explicit and
does not imply upload or publication authorization.

`.github/workflows/acc1_daily_episode.yml` is the one-dispatch, artifact-only long-form factory for `acc1`. Its base revision is active on GitHub `main` as workflow `312924313` at commit `bbfe22d`; its latest run failed before paid providers and produced no review-ready artifact. The richer local revision described below has not yet been merged: it adds the OpenAI translation/review lane, the PRAW lazy-fetch fix, and the separate private-upload workflow. Neither revision can guarantee views or invoke `uploader.py` from the factory; its maximum result is `READY_FOR_HUMAN_REVIEW`.

The planner resolves one Europe/Moscow production date against the fixed interleaved cycle `pilot_01, pilot_04, pilot_02, pilot_05, pilot_03, pilot_06`. It reads exact pilot rows from `channels.json`, not the superseded `topic_mix`. The source stage then performs only bounded read-only Reddit collection with `AI_QUALITY_CHECK=0` and `AI_QUALITY_FAIL_OPEN=0`; SAGA/BUNDLE may scan up to three configured time windows and THREAD uses its bounded year pool. It must retain exactly 3-5 complete candidates before any paid stage is allowed. SAGA/BUNDLE stories and THREAD responses are rejected before finalist selection for incomplete source/provenance, link or screenshot dependence, high-confidence safety/PII failures, viewer-promise mismatch, or fictional-as-real risk. They are also rejected when normalized source characters exceed 12 per source word or a source token exceeds 80 characters; THREAD prompts have a 2,000-character spoken-source ceiling. These are source, renderability, and spend-envelope gates, not claims that Reddit text is factual.

For each finalist, a producer and independent critic score the same source-bound candidate. The topic playoff requires both reviews to pass, total score at least 90/100, every category floor, three materially distinct title/thumbnail/first-screen options, exact source evidence, and no hard veto for incomplete payoff, wrong pillar, screenshot/link dependence, fictional-as-real framing, unverified claims presented as fact, or viewer-promise mismatch. Reddit metrics remain discovery signals, not factual or audience proof.

After a winner is locked, the local revision performs source-preserving Russian translation plus a separate translation-review request with the exact pinned OpenAI model `gpt-5.4-2026-03-05` and `reasoning_effort=none`. Gemini remains limited to topic producer/critic scoring and final packaging; it is not the translator or translation reviewer in that revision. The OpenAI lane reads only `OPENAI_API_KEY`, uses strict JSON, has no fallback to Gemini and no automatic retry. Its journal records the API usage envelope, where billable/quota total is `input_tokens + output_tokens`; `reasoning_tokens` is a subset of `output_tokens` and is not added again. A conservative reservation is checked before transport and the actual total is checked afterward against `openai_token_cap` (maximum `1,000,000`). The same-model reviewer is an independent request and prompt, but it is not cross-model diversity. GitHub `main` does not yet contain this lane and must not be invoked with OpenAI inputs until the revision is reviewed and merged.

Production then continues with source-bound packaging, bounded `gpt-image-2` scene/thumbnail generation through VectorEngine, role-aware AI33 `eleven_v3` narration, an explicit visual mode, media QA, and a checksum-bound creative-review template. `reddit_pages` is still the workflow and factory default and preserves exact Reddit-card page/layout validation plus the verified cat-background renderer. `cinematic_story_v1` is an opt-in SAGA/BUNDLE branch with full-screen accepted scene images, deterministic 1.06-1.10 slow push/pan shots, no cat-background dependency, caption/SRT sidecars and mode-specific QA; THREAD fails closed until it has a separate response-card contract. Neither mode is a fallback for the other. Before TTS the factory builds a fail-closed `intro_contract`: winning source-backed cold open -> exact format/count promise -> truth disclosure -> source-in-description note -> generic truthful thanks -> pillar-safe Chonker Talks sting -> first story/prompt cue. The cold open is 8-30 words and hash-bound to the playoff winner; the whole intro is at most 90 spoken words. Named sponsors or payment claims are forbidden because there is no verified supporter ledger. `Свет можно оставить включённым` is dark-pillar-only; all other pillars use `Устраивайтесь поудобнее`. The factory does not yet emit complete post-TTS chapters, so the spoken intro never claims that timestamps exist. The male `elevenlabs_JBFqnCBsd6RMkjVDRZzb` voice narrates; THREAD responses use the separate female `elevenlabs_MOgsVr0EwwxqQs5cNDhu` voice. The five canonical pillar profiles tune speed, stability, style and pause policy without changing either voice ID or source text. Thumbnail generation accepts only a meaningful exact quote and a deterministic non-photoreal source-bound prompt; generated images must decode to an accepted image format and exact dimensions before AI33 is called. The YouTube description is a deterministic neutral disclosure-plus-source template, so a provider cannot append an unsupported factual claim. TTS state binds semantic chunks, exact profile settings, actual `ffprobe` duration and exact AI33 word alignment when valid, or a declared timing estimate derived from the exact audio duration. A local pause map inserts beat/segment pauses without altering narration punctuation; the final voice-only WAV is two-pass loudness-normalized around `-16 LUFS` (±1 LU) with true peak no higher than `-1.5 dBTP`, measured and checksum-bound in the audio-mix report. Both renderers consume that same final mixed-audio contract. A pre-TTS estimate must fit the slot's duration range with tolerance and final media QA enforces the exact canonical duration. Generated asset paths are artifact-root-relative so the GitHub artifact is portable. Manifest v2 binds mode, profile, pause map, mix, shot/caption sidecars and final media; historical manifest v1 remains strict-compatible. Every downstream artifact is bound to the exact daily plan, episode plan, narration plan, audio, source, and final media hashes.

The local revision also adds opt-in `editorial_motion_v1` for SAGA/BUNDLE. Motion-plan v2 supports both `contemporary_cutup_v1` and the implemented opt-in `ink_gouache_story_pages_v1`. The Ink & Gouache profile requires an explicit story family, unequal-panel page layout and episode-wide recurring-character identity contract before provider spend. It applies eight beat-specific camera/layout choreographies and family palettes for relationships, work, digital traces, memories, unusual jobs and dark SAGA; it does not reuse the old universal blue/coral/mustard cut-up palette. Photorealism is reserved for real documents, messages, interfaces and archival evidence. Exact captions, dates, quotations and evidence remain HTML/SVG. HyperFrames is the production renderer; `html-video` stays an alpha studio/catalog layer because its verified adapter truncates long fixed compositions. Editorial oversized near-16:9 provider responses are preserved and deterministically normalized to 1536x864 with original and normalized checksums; unsafe crops still fail closed. `contemporary_cutup_v1` remains the production default pending explicit promotion of the new profile. THREAD remains blocked in this mode. Full contracts, reference board, pilot commands and evidence are in [`acc1-editorial-motion-v1.md`](acc1-editorial-motion-v1.md).

The current Ink & Gouache canary is `build/reddit-five-minute-ink-gouache-v6/reddit-five-minute-ink-gouache-s-tier-v6.mp4`: source-locked Reddit/BORU `1i8nufm`, H.264/AAC, 1920x1080/30, exactly 300 seconds, SHA-256 `5cf32e036e34f983bb6df041878060fe8a2bfea92c5ceedcda7793a84347a37d`. It reuses the 16 accepted `gpt-image-2` plates from v3 with zero new provider calls. HyperFrames 0.7.61 reports zero runtime/layout/motion/contrast errors; eleven chapter samples and exact former-risk boundaries passed visual review, and FFmpeg black detection found no black intervals. The contact-sheet SHA-256 is `1b0b1197202524ef89e9d79c8427f6c6745063e9de33695fdabf5695529ae1dc`. This is local silent visual evidence only and changes no workflow, channel default, rights or publication state.

Local no-spend proof is generated by `scripts/build_acc1_cinematic_fixture.py` and checked by `tests.test_acc1_cinematic_fixture`. The 2026-07-17 evidence at `/tmp/acc1-cinematic-comparison-20260717-v4` contains two real mode-bound MP4s, two separate v2 manifests/pause/mix chains, one shared source/narration/raw-chunk contract and byte-identical final voice-only WAVs. Both media-QA reports are `PASS`; `comparison-report.json` has self-hash `bca27e2ecf1a6ad0d053138d90ed5a84846ed267c4d3b4cd93fc505536aafe74`. Rendered MP4/SRT paths are artifact-root-relative, so the report remains valid after artifact download or relocation. This fixture uses synthetic drawings and tones, so it proves the local pipeline and motion geometry only. Human creative/audio review, real narrator continuity, provider-image semantics, rights and any production canary remain unproven and separately gated.

After source success, a no-provider paid preflight validates all paid confirmations, credential presence, model/provider contracts, exact source hashes, and source-dependent call ceilings. The maximum five-finalist pool needs Gemini cap `11` for topic producer/critic scoring plus packaging. A 15-response THREAD winner whose sources each fit one fallback chunk needs OpenAI cap `90` for the conservative full translation/review path; exact source-dependent counts are calculated before spend. Non-semantic source whitespace is canonicalized only in the translation working copy so space/tab floods cannot inflate provider chunks, while the exact Reddit body and hash remain unchanged in source evidence. Every accepted source envelope fits AI33 cap `96`, and the exact planned chunks are checked again before image or voice spend. The workflow then creates and uploads a self-hashed spend lease bound to the episode, source artifacts, caps, models, repository, workflow, run identity, commit, and every candidate source's canonical ID/URL/body SHA/story signature before the first paid request. The acc1 build job is globally serialized; after collection it rescans all unexpired `acc1-paid-lease-*` artifacts and blocks any same-episode or reserved-source overlap across dates. Paid-provider attempt journals are written before each request; an ambiguous result blocks every later request for that provider and reuse of that work directory. Hidden Gemini/OpenAI/image retries are disabled. Translation character/token bounds apply to exact post-number-normalization narration, and cold opens have a 500-character spoken ceiling. The final release candidate hashes 25 evidence files, including paid preflight, spend lease, text-layout proof, runtime estimate, media QA, and all provider journals.

The lease and journals are fail-closed duplicate-spend detectors, not a full cross-dispatch response cache. AI33 is additionally locally resumable without another POST: it atomically records `SUBMITTING` before transport, submits every missing chunk, persists all returned task IDs before the first poll, then polls the saved IDs with bounded concurrency under one shared deadline. An ambiguous submission never retries automatically. The workflow gives the complete produce step 300 minutes, supplies AI33 an absolute deadline 240 minutes from produce start, reserves the remaining 60 minutes for render/QA, and keeps the job's 360-minute ceiling for setup, source and artifact upload. Maximum Gemini/image caps still do not constitute a proven worst-case completion envelope, and a fresh GitHub runner cannot yet restore every prior provider response automatically. Treat the first live run as a separately approved canary and manually adjudicate every timeout or partial-spend result.

Private YouTube upload is deliberately a separate local-only manual workflow, `.github/workflows/acc1_private_upload.yml`, after the factory artifact has been downloaded and visually reviewed. It is not registered on GitHub `main` and its command must not be run until it has been separately reviewed and merged. Once available, it accepts the successful factory `source_run_id`, `expected_manifest_sha256` equal to the exact reviewed `release_candidate_manifest_sha256`, and `confirm_private_upload=true`; it verifies the bound artifact and acc1 OAuth mapping, uploads exactly one private video, applies the custom thumbnail, and preserves the readback receipt. It contains no Reddit, Gemini, OpenAI, image, AI33, history write, public, or unlisted path.

`workflow_dispatch` must already exist on the repository default branch. Therefore the local OpenAI revision, background assets, all-channel `videos_per_day=0` hold, and private-upload workflow must first be reviewed and merged to `main`; `--ref` alone cannot bootstrap them from a feature branch. The following commands are future-only references for that merged revision, not commands for the current GitHub `main`.

```bash
gh workflow run acc1_daily_episode.yml \
  --repo webpot-ru/nebula-core-v3 \
  --ref main \
  -f production_date="" -f pilot_id=auto -f visual_mode=reddit_pages \
  -f confirm_reddit_read=true -f reddit_request_cap=24 \
  -f confirm_gemini_spend=true -f gemini_call_cap=128 \
  -f confirm_openai_spend=true -f openai_call_cap=96 \
  -f openai_token_cap=500000 \
  -f confirm_image_spend=true -f image_call_cap=16 \
  -f confirm_ai33_spend=true -f ai33_call_cap=96
```

Only after that future factory run succeeds, its exact video/audio/thumbnail receive a completed human review, and its source rights are recorded should the no-provider release-review workflow be dispatched. The review bundle is a repo-relative directory under `release-reviews/acc1/` containing `creative-review.json` and `rights-manifest.json`:

```bash
gh workflow run acc1_release_review.yml \
  --repo webpot-ru/nebula-core-v3 --ref main \
  -f source_run_id=EXACT_FACTORY_RUN_ID \
  -f expected_manifest_sha256=EXACT_FACTORY_MANIFEST_SHA256 \
  -f review_bundle_path=release-reviews/acc1/EXACT_EPISODE_KEY \
  -f confirm_release_review=true
```

That workflow calls no content provider and performs no upload. It emits a self-hashed `release-gate.json` only after the exact factory evidence, completed version-3 creative review with timestamped visual/audio observations, and private-scope rights manifest all pass. The private-only upload then requires both the factory identity and that separate release-gate receipt:

```bash
gh workflow run acc1_private_upload.yml \
  --repo webpot-ru/nebula-core-v3 --ref main \
  -f source_run_id=EXACT_FACTORY_RUN_ID \
  -f expected_manifest_sha256=EXACT_FACTORY_MANIFEST_SHA256 \
  -f release_gate_run_id=EXACT_RELEASE_GATE_RUN_ID \
  -f expected_release_gate_sha256=EXACT_RELEASE_GATE_SHA256 \
  -f confirm_private_upload=true
```

The factory command can consume Reddit/API quota, OpenAI/Gemini, image-generation, AI33, GitHub runner, and artifact storage. The private-upload command mutates YouTube. Do not run either without exact approval of its scope. `visual_mode=reddit_pages` is the safe default; requesting `cinematic_story_v1` does not grant any additional provider or upload authority. The factory artifact contains `daily-plan.json`, source evidence, 3-5 finalist reviews, `topic-playoff.json`, immutable `episode-plan.json`, paid-preflight and spend-lease evidence, script, metadata, scene images, thumbnail, narration state/audio, pause map, measured audio-mix report, exact layout/runtime reports, storyboard, mode-specific shot/caption/SRT sidecars where applicable, `final-output.mp4`, media QA, creative-review template, provider attempt journals, and `release-candidate-manifest.json`. Human creative/audio review, exact source rights and a separately authorized upload remain mandatory. The adapter and revised two-workflow chain are locally tested but not committed or registered. Live readback on 2026-07-17 found the older `acc1 Private Artifact Upload` workflow id `313326356` active on GitHub `main`; it must not be dispatched because it lacks the new mandatory release-gate receipt. The new `acc1 Release Review Gate` is not registered, and no YouTube upload was made.

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
- [x] `thumbnail_generator.py` supports deterministic local Cyrillic overlay/report and VectorEngine generation behind explicit spend confirmation
- [x] Exact acc1 BUNDLE/SAGA/THREAD routing, bounded source collectors/selectors, 3-5-candidate producer/critic 90/100 topic playoff with at least three passing finalists, immutable episode plan, role-aware TTS, Reddit-pages renderer/QA, and human-review release ceiling are implemented locally
- [x] Local `cinematic_story_v1` implementation for SAGA/BUNDLE: explicit non-default mode, deterministic full-screen shot plan, caption/SRT sidecars, five pillar narration profiles, semantic pause map, measured voice-only mix, manifest v2, factory/workflow propagation and mode-aware renderer/QA; no provider, GitHub or YouTube canary has run
- [x] Local `editorial_motion_v1` implementation for SAGA/BUNDLE: paired source-bound image packs, six semantic collage modules, HyperFrames/GSAP renderer, exact HTML/SVG factual text, motion/caption sidecars and mode-aware QA/release evidence; the current visually inspected proof is a source-locked 300-second silent pilot using 16 successful `gpt-image-2` attempts with zero retries, while GitHub/YouTube publication remains untouched
- [x] Base `acc1_daily_episode.yml` is active on GitHub `main`, but no successful review-ready artifact exists. The local OpenAI/private-upload extension is not yet merged and has no GitHub artifact proof.
- [x] `storyboard_generator.py` and `render.py` create a no-spend dry-run `final_output.mp4`
- [x] Slide-based RedditSim rendering: first story screen without comments, comment-only screens, long story chunking, clean no-karaoke visuals, timed slide boundaries, and larger Reddit-like render-mode fonts
- [x] GitHub Actions workflow `video_dry_run.yml` renders and uploads a live dry-run MP4 artifact
- [x] GitHub Actions workflow `auto_publish.yml`
- [x] Scrapers research & comparison documentation
- [x] Verified GitHub dry-run rendering (`chonkertalks-dry-run-video` artifact generated)

### 🔄 Next Steps (Priority Order)
- [ ] **1. Review and merge the local factory extension and all-channel legacy-publish hold, then run one explicitly approved bounded `acc1_daily_episode.yml` artifact** - inspect exact source evidence, topic playoff, voice roles, thumbnail, MP4, and QA; do not infer audience demand from a successful build.
- [ ] **2. Complete human creative and rights review for that exact hash-bound artifact** - the local factory-aware adapter and no-provider release-review workflow are ready, but an actual version-3 human review and exact rights manifest do not yet exist. Only their `READY_FOR_PRIVATE_REVIEW` receipt may feed the separately authorized private upload.
- [ ] **3. Validate distinct Reddit-native pilots** for `acc4` and `acc7`; keep every channel automation-disabled until its gate passes.
- [ ] **4. Build the evidence-dossier lane** for `acc2`, `acc3`, `acc5`, and `acc6` with independent sources, original scripts, timelines, and evidence visuals.
- [ ] **5. Fix delayed-cron routing** so scheduled jobs map from `github.event.schedule` rather than the runner's current UTC hour.
- [ ] **6. Run small unlisted pilots and analytics readback** before any public schedule; collect Engaged views, Stayed to watch, average percentage viewed, shares/comments/subscribers per 1,000 engaged views, and returning viewers.

### 🔮 Future
- [ ] Broader source discovery beyond Reddit: primary sources, official data, Google Trends, rights-safe archives, and RSS/news sources behind explicit spend/API boundaries
- [ ] Custom Chonker cat avatars per language
- [ ] Analytics readback - promote repeated winning story signatures and retire bottom-half content bets
- [ ] Auto A/B test thumbnails

## DESIGN.md Agent Bridge

Status: DESIGN.md agent bridge installed 2026-07-08.

[`../DESIGN.md`](../DESIGN.md) is the project-root visual source for AI/UI agents. It uses the plain Markdown DESIGN.md pattern from https://github.com/VoltAgent/awesome-design-md, but it does not replace this documentation index or the topic-specific source-of-truth documents. For visual/frontend work, read `AGENTS.md`, this `docs/README.md`, `docs/PROJECT_STATE.md`, the relevant topic document, and then `DESIGN.md`.
