# nebula-core-v3 Project State

Last updated: 2026-06-30

## Current Shape

`/Users/lali/Projects/reddit` is a multilingual YouTube story-entertainment pipeline for the ChonkerTalks channel network.

Current content strategy: the old "one language = one Reddit niche" plan has been replaced. The active plan is audience-first:

- One channel is defined by language, viewer promise, and tone.
- Shorts test fast hooks across region-specific entertainment topics.
- Long-form videos expand the winners into 8-18 minute explainers, story documentaries, moral-drama breakdowns, mystery timelines, or compilations.
- Reddit stories remain one useful source, not the whole strategy.
- The strongest priority markets are LATAM Spanish and Brazil Portuguese, followed by France, Germany, English, Italy, and opportunistic Russian-speaking/CIS diaspora coverage.

- `index.html`, `style.css`, `app.js` implement the local RedditSim recorder UI.
- `scraper.py` fetches candidate Reddit stories through PRAW OAuth2, weighted topic-family source planning, local duplicate/signature/similarity guards, velocity scoring, topic-fatigue penalties, and a bounded Gemini quality gate, then writes `story_data.json`.
- `translator_tts.py` localizes non-English `story_data.json` through VectorEngine Gemini, then builds narration text and submits it to AI33 TTS v3.
- `metadata_generator.py` generates YouTube title, description, tags, hashtags, SEO keywords, thumbnail text and thumbnail prompt through VectorEngine Gemini.
- `thumbnail_generator.py` can generate a thumbnail image through VectorEngine image generation, but only with explicit `--confirm-spend`.
- `storyboard_generator.py` creates a deterministic no-API `storyboard.json` from `story_data.json`.
- `render.py` opens the existing RedditSim UI in headless Chrome/Chromium, captures deterministic typing or karaoke screenshots, and uses FFmpeg to render a 9:16 MP4 from `storyboard.json`. If `narration.mp3` exists, it merges that file as an AAC audio track; if `narration.json` exists, it passes the transcript to RedditSim for bright gold word-level highlighting directly inside the Reddit card text.
- `uploader.py` is a base YouTube Data API uploader.
- `.github/workflows/auto_publish.yml` sketches the cloud pipeline, but the end-to-end production path is not fully verified.
- `.github/workflows/video_dry_run.yml` is currently a live manual workflow: it fetches Reddit content, can spend VectorEngine/AI33 credits for quality/localization/TTS, renders `final_output.mp4`, and uploads story, audio, transcript, video, and previews.

## GitHub Dry-Run Status

- Dry-run renderer commits were pushed to `origin/main` and transferred to `webpot-ru/nebula-core-v3`.
- GitHub Actions run `28421055129` succeeded on 2026-06-30 under the `webpot-ru` account.
- The `render-dry-run` job completed in 1m 21s, passed validation tests, and successfully uploaded the `chonkertalks-dry-run-video` artifact.
- The artifact was downloaded locally to `build/render/chonkertalks-dry-run-video` and contains `final_output.mp4` (594 KB, verified codec and resolution).
- The transition from `startup_failure` to success was resolved by migrating repository ownership to `webpot-ru` (which has a healthy billing profile) and setting all required repository secrets.

## Verified Locally

- Python syntax check passed for `scraper.py`, `translator_tts.py`, and `uploader.py`.
- `channels.json` parses as valid JSON and now includes weighted `topic_mix` per channel; the weights are initial production hypotheses and still need live artifact tuning.
- `python3 -m py_compile storyboard_generator.py render.py` passed.
- `python3 storyboard_generator.py --input sample_story_data.json --output storyboard.json` passed and produced 6 scenes.
- `python3 render.py --storyboard storyboard.json --output final_output.mp4` passed once locally through the RedditSim Chrome DevTools path and captured 8 simulator frames.
- A later local macOS Chrome run timed out during `Page.captureScreenshot`; this appears to be local system Google Chrome instability, not an API/spend/upload blocker.
- FFmpeg encoding was independently verified from the captured RedditSim frames: H.264, 1080x1920, 30 fps, 22.0s, 660 frames.
- `test -s final_output.mp4` passed on a local generated artifact, but the current GitHub artifact is still pending.
- `app.js` passes `node --check`.
- RedditSim loaded in a real browser at `http://localhost:8080/`; the typewriter animation completed and rendered title, body, and comments.
- Browser console only showed missing `favicon.ico` 404s during that smoke, not JavaScript runtime errors.

## AI33 TTS State

- `translator_tts.py` now uses `POST https://api.ai33.pro/v3/text-to-speech` with multipart FormData and `xi-api-key`.
- `translator_tts.py` sends `model_id=eleven_v3` by default; override with `--model-id` or `AI33_TTS_MODEL_ID` only intentionally.
- The expected secret is `AI33_API_KEY`; `A133_API_KEY` is accepted only as a compatibility fallback for older local notes.
- `channels.json` uses `tts_provider: "ai33"` and prefixed `edge_...` voice ids as the current baseline.
- Live AI33 v3 smoke passed on 2026-06-29 using the gitignored LUNA2 local env key as a one-off user-approved read. The secret was not printed or copied into this repo.
- The first smoke submitted an ElevenLabs-prefixed voice id (`elevenlabs_21m00Tcm4TlvDq8ikWAM`) with text containing `[sighs]`, `[laughs]`, and `[whispers]`; AI33 returned `task_id=3f489e0b-3b73-40c2-95fd-071ee694055c`, task polling returned `status=done`, and `/tmp/reddit_ai33_laugh_sigh.mp3` was written.
- A second smoke explicitly sent `model_id=eleven_v3` with `[laughs]` and `[sighs]`; AI33 returned `task_id=08c146ad-82a0-4efb-a4e2-f8ec65254852` and wrote `/tmp/reddit_ai33_eleven_v3_laugh.mp3`.
- `afinfo` verified the explicit `eleven_v3` smoke output as a 5.64s MP3, 44.1 kHz stereo, 128 kbps, 90,740 bytes.
- AI33 v3 task polling uses `/v3/task/{task_id}` with `Authorization: $AI33_API_KEY` by default. If account-specific routing differs, set `AI33_TASK_URL_TEMPLATE` or `AI33_TASK_AUTH_HEADER` before running TTS.

## VectorEngine State

- LUNA2 is the source for VectorEngine local access data: `/Users/lali/Documents/LUNA2/.env.vectorengine.local`.
- `vectorengine_client.py` supports the LUNA2-compatible env names `VECTORENGINE_API_KEY`, `VECTOR_ENGINE_API_KEY`, and optional `VECTORENGINE_BASE_URL`.
- `metadata_generator.py` uses the LUNA2-compatible Gemini endpoint shape: `POST /v1beta/models/{model}:generateContent`, default `model=gemini-3.5-flash`.
- `thumbnail_generator.py` uses the LUNA2-compatible image endpoint shape: `POST /v1/images/generations`, default `model=gpt-image-2`, size `1536x864`.
- Live metadata smoke passed on 2026-06-29 using the gitignored LUNA2 VectorEngine env file as a one-off user-approved read. The secret was not printed or copied into this repo.
- Smoke command wrote `/tmp/reddit_vectorengine_metadata_live.json` with `source=vectorengine-gemini`, `model=gemini-3.5-flash`, `channelId=acc4`, `language=es-419`, 79-character Spanish title, 323-character description, 8 tags, 4 hashtags, thumbnail text, thumbnail prompt, SEO keywords, and no risk flags.
- Thumbnail image generation has only been dry-run checked in this repo. It is connected but not live image-spend verified.

## Current Pipeline Changes

- `translator_tts.py` now translates `title`, `body`, and each comment `body` for non-English channels before TTS. By default it overwrites `story_data.json` so downstream storyboard/render steps see localized text; use `--translated-story-output` to write a separate localized file.
- The default narration text mirrors visible card text for karaoke alignment: title, body, then comment bodies. `--include-comment-labels` can restore spoken "Comment by user" labels when strict word-level visual sync is not required.
- `render.py` now auto-detects default `narration.mp3` and `narration.json`, passes them to RedditSim as `audio` and `transcript` query parameters, captures deterministic karaoke frames when transcript words are available, and merges the audio track into `final_output.mp4`. Karaoke mode does not add extra words, lower captions, or overlay text; it highlights the currently spoken word directly in the existing Reddit card text with a bright gold treatment.
- `style.css` now hides editor/sidebar/HUD/desktop-nav/sidebar/safe-zone widgets under `.clean-mode` and `.render-mode`, including desktop layout states.
- `.github/workflows/auto_publish.yml` and `.github/workflows/video_dry_run.yml` now pass both `AI33_API_KEY` and `VECTORENGINE_API_KEY` to the TTS/localization step.
- `scraper.py` now supports `--time auto`, `--topic-family`, `--max-ai-candidates`, `--candidate-limit`, and `--similarity-threshold`. `auto` mode scans capped topic-family source plans rather than only `top/week`, then sends only the top bounded pool to Gemini.
- `published_history.json` remains backward-compatible with the old `{post_id: [channels]}` shape; the next scraper save migrates future entries to versioned records with story signatures, keyword signatures, topic family, time window, velocity, fatigue penalty, virality score, and AI quality data.
- `.github/workflows/auto_publish.yml` now supports manual `topic_family` test runs and uses `privacy_status=unlisted` by default for manual dispatch. The workflow and `video_dry_run.yml` use `time_filter=auto` by default for topic-family windows and set `AI_QUALITY_FAIL_OPEN=0`, explicit `MAX_AI_CANDIDATES`, `STORY_SIMILARITY_THRESHOLD=0.72`, and `TOPIC_FATIGUE_LOOKBACK=10`.
- `uploader.py` now supports `--privacy-status public|unlisted|private`, merges `tags` + `seo_keywords`, appends returned `hashtags` to the description, and passes metadata language to YouTube. Manual `auto_publish.yml` dispatch defaults to `unlisted`; scheduled runs default to `public`.

## Known Blockers

- Topic-family weights in `channels.json` are configured but not yet validated against live artifacts or YouTube retention/readback.
- `auto_publish.yml` still points at a production upload flow and must not be treated as safe until the new localization/audio-aware render path is verified with a full live artifact and uploader readback.
- `uploader.py` still needs a focused live upload/readback pass before public production use, especially verifying title/description/tags/language on the uploaded YouTube video.
- There is no project safe-trash helper under `scripts/`, so generated scratch artifacts should not be deleted by agents without adding a safe workflow first.

## Next Steps

1. Run a live topic-discovery artifact check for `--time auto` on priority channels, then tune `topic_mix` weights from candidate variety and Gemini verdicts.
2. Choose final ElevenLabs or MiniMax voice ids from AI33 Voice Library and update `channels.json` if emotion tags such as `[laughs]` should be supported by default.
3. Run a full live workflow artifact check for localized story text, narration audio, audio stream in MP4, clean capture, and karaoke highlighting.
4. Run one intentional VectorEngine image generation smoke if custom thumbnail generation should be enabled in the automated path.
5. Fix and verify `uploader.py` CLI account selection before any production upload.
