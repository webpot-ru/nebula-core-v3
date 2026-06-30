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
- `translator_tts.py` localizes non-English `story_data.json` through VectorEngine Gemini, sanitizes narration/card text so raw URLs are replaced with localized on-screen-link phrases, then builds narration text and submits it to AI33 TTS v3. Channels can use separate `tts_voice` and `comment_tts_voice` roles; the script concatenates role segments into one `narration.mp3` and writes combined word timings for karaoke.
- `metadata_generator.py` generates YouTube title, description, tags, hashtags, SEO keywords, thumbnail text and thumbnail prompt through VectorEngine Gemini.
- `thumbnail_generator.py` can generate a thumbnail image through VectorEngine image generation, but only with explicit `--confirm-spend`.
- `storyboard_generator.py` creates a deterministic no-API `storyboard.json` from `story_data.json`.
- `render.py` opens the existing RedditSim UI in headless Chrome/Chromium, captures deterministic typing or karaoke screenshots, and uses FFmpeg to render a 9:16 MP4 from `storyboard.json`. If `narration.mp3` exists, it merges that file as an AAC audio track; if `narration.json` exists, it requires karaoke mode and passes the transcript to RedditSim for bright gold word-level highlighting directly inside the Reddit card text.
- `uploader.py` is a YouTube Data API uploader with a fail-closed channel-token preflight against `channels.json` and post-upload metadata readback.
- `.github/workflows/auto_publish.yml` runs the cloud publish pipeline. It now verifies the YouTube refresh token against `channels.json` before Reddit/Gemini/AI33/render work. The first full live smoke succeeded as an unlisted upload, but account-token/channel mapping is not yet safe for public scheduled publishing.
- `.github/workflows/video_dry_run.yml` is currently a live manual workflow: it fetches Reddit content, can spend VectorEngine/AI33 credits for quality/localization/TTS, renders `final_output.mp4`, and uploads story, audio, transcript, video, and previews.

## GitHub Dry-Run Status

- Dry-run renderer commits were pushed to `origin/main` and transferred to `webpot-ru/nebula-core-v3`.
- GitHub Actions run `28421055129` succeeded on 2026-06-30 under the `webpot-ru` account.
- The `render-dry-run` job completed in 1m 21s, passed validation tests, and successfully uploaded the `chonkertalks-dry-run-video` artifact.
- The artifact was downloaded locally to `build/render/chonkertalks-dry-run-video` and contains `final_output.mp4` (594 KB, verified codec and resolution).
- The transition from `startup_failure` to success was resolved by migrating repository ownership to `webpot-ru` (which has a healthy billing profile) and setting all required repository secrets.

## Live Publish Smoke Status

- Manual `auto_publish.yml` run `28441721783` succeeded on 2026-06-30 for `acc4`, `video_slot=1`, `time_filter=auto`, `topic_family=human_drama`, `privacy_status=unlisted`.
- The selected story was `r/AmItheAsshole` / `top/week`: "AITA for being blunt with my boyfriend about why he isn't getting hire..." with about 7.3k upvotes and 1.5k comments. Gemini quality gate approved it as `REWRITE` after skipping one malformed-JSON quality response.
- Localization/TTS succeeded: `story_data.json` was localized to Spanish (`es-419`), AI33 voice `edge_es-MX-JorgeNeural` produced `narration.mp3`, and `narration.json` was saved.
- Render succeeded: `final_output.mp4`, 1080x1920, 300 captured frames, 237.672s total duration, with `audioDurationSec=237.672`, `audio=narration.mp3`, and `transcript=narration.json`.
- Upload succeeded as unlisted with YouTube video id `cFX2tZmLrAs`; public oEmbed readback returned the Spanish title "¿Soy la mala por decirle a mi novio la verdad de por qué nadie lo contrata?".
- Important blocker: public/user readback showed videos landing on the wrong channel for the requested account. Treat all `YOUTUBE_REFRESH_TOKEN_ACC1-7` mappings as unverified until `uploader.py` preflight confirms the authenticated channel for each token against `channels.json`.
- The workflow committed the published-history update to `origin/main` as `d54da14 chore: history [acc4] slot=1 [skip ci]`.

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
- `channels.json` still contains temporary `edge_...` narrator/comment voice ids. This does not satisfy the product requirement to use ElevenLabs v3 through AI33. `auto_publish.yml` now fails early unless both voices start with `elevenlabs_`, so no new publish run should spend Gemini/AI33 credits with Edge voices.
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
- If `comment_tts_voice` differs from `tts_voice`, `translator_tts.py` now runs multi-voice TTS: title/body use the narrator voice, comment bodies use the comment voice, FFmpeg concatenates the MP3 segments, and `narration.json` is rewritten with combined offset word timings. `--single-voice` disables this and `--comment-voice-id` overrides the configured comment voice.
- `translator_tts.py --check-voice-config --require-voice-prefix elevenlabs_` validates narrator/comment voice ids without reading story text or calling AI33. `auto_publish.yml` runs this preflight before Reddit/Gemini/AI33 work.
- `translator_tts.py` now replaces raw URLs and service link lines such as `Original thread: https://...` with localized phrases such as "el enlace está en pantalla" before TTS and storyboard handoff. This keeps screen text and narration aligned while avoiding robotic URL reading.
- `render.py` now auto-detects default `narration.mp3` and `narration.json`, passes them to RedditSim as `audio`, `transcript`, and `karaoke=1` query parameters, captures deterministic karaoke frames when transcript words are available, and merges the audio track into `final_output.mp4`. If transcript/audio are provided but karaoke cannot initialize, render fails instead of falling back to typewriter animation. Karaoke mode does not add extra words, lower captions, or overlay text; it highlights the currently spoken word directly in the existing Reddit card text with a bright gold treatment.
- `style.css` now hides editor/sidebar/HUD/desktop-nav/sidebar/safe-zone widgets under `.clean-mode` and `.render-mode`, including desktop layout states.
- `.github/workflows/auto_publish.yml` and `.github/workflows/video_dry_run.yml` now pass both `AI33_API_KEY` and `VECTORENGINE_API_KEY` to the TTS/localization step.
- `scraper.py` now supports `--time auto`, `--topic-family`, `--max-ai-candidates`, `--candidate-limit`, and `--similarity-threshold`. `auto` mode scans capped topic-family source plans rather than only `top/week`, then sends only the top bounded pool to Gemini.
- `published_history.json` remains backward-compatible with the old `{post_id: [channels]}` shape; the next scraper save migrates future entries to versioned records with story signatures, keyword signatures, topic family, time window, velocity, fatigue penalty, virality score, and AI quality data.
- `.github/workflows/auto_publish.yml` now supports manual `topic_family` test runs and uses `privacy_status=unlisted` by default for manual dispatch. Scheduled cron entries are also temporarily `unlisted` until the YouTube token/channel mapping is verified. The workflow and `video_dry_run.yml` use `time_filter=auto` by default for topic-family windows and set `AI_QUALITY_FAIL_OPEN=0`, explicit `MAX_AI_CANDIDATES`, `STORY_SIMILARITY_THRESHOLD=0.72`, and `TOPIC_FATIGUE_LOOKBACK=10`.
- `uploader.py` now supports `--check-channel-only`, `--privacy-status public|unlisted|private`, merges `tags` + `seo_keywords`, appends returned `hashtags` to the description, passes metadata language to YouTube, verifies the authenticated YouTube channel before upload, and reads back uploaded video metadata afterward. `auto_publish.yml` runs the channel check before any content-generation spend. Manual and scheduled runs stay `unlisted` until token mappings are proven.

## Known Blockers

- Topic-family weights in `channels.json` are configured but not yet validated against retention/readback.
- Public scheduled publishing is blocked until all `YOUTUBE_REFRESH_TOKEN_ACC1-7` values are audited against `channels.json`. User/browser readback showed videos landing on the wrong target channel; new uploads should fail before upload if the token resolves to the wrong authenticated channel.
- Public/manual `auto_publish.yml` is also blocked until `channels.json` uses real `elevenlabs_...` narrator/comment voice ids for the selected channel.
- `uploader.py` still needs authenticated YouTube metadata readback before public production use, especially verifying title/description/tags/language and channel id after upload.
- There is no project safe-trash helper under `scripts/`, so generated scratch artifacts should not be deleted by agents without adding a safe workflow first.

## Next Steps

1. Audit every YouTube refresh token against `channels.json` and replace any token whose authenticated channel does not match the expected handle/name before any public scheduled run.
2. Replace the temporary `edge_...` voices in `channels.json` with real AI33 `elevenlabs_...` narrator/comment pairs. Use a small AI33 Voice Library bake-off if the correct IDs are not already known.
3. Add authenticated uploader readback for title, description, tags, language, privacy, channel id, and optionally thumbnail state.
4. Run one intentional VectorEngine image generation smoke if custom thumbnail generation should be enabled in the automated path.
5. Tune `topic_mix` weights from live candidate variety, Gemini verdicts, and YouTube retention once account mapping is safe.
