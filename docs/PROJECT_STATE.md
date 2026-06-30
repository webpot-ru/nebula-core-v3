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
- `render.py` opens the existing RedditSim UI in headless Chrome/Chromium, captures deterministic typing or karaoke screenshots, and uses FFmpeg to render an MP4 from `storyboard.json`. In default `--orientation auto` mode, videos up to 180 seconds render vertical 9:16 (`1080x1920`, mobile layout), while videos longer than 180 seconds render horizontal 16:9 (`1920x1080`, desktop layout). Both orientations use the same in-text karaoke highlight; the horizontal render path fills the 16:9 viewport with a clean Reddit card and hides editor/sidebar widgets. If `narration.mp3` exists, it merges that file as an AAC audio track; if `narration.json` exists, it requires karaoke mode and passes the transcript to RedditSim for bright gold word-level highlighting directly inside the Reddit card text.
- `scripts/move-to-trash.sh` is the project safe-trash helper. Generated previews and scratch files must be moved to `Trash/<timestamp>/...`; agents must not use direct deletion commands.
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
- Localization/TTS succeeded using the old Spanish Edge-placeholder voice that was configured at the time; this was before the channel voice migration to ElevenLabs. `story_data.json` was localized to Spanish (`es-419`), `narration.mp3` was produced, and `narration.json` was saved.
- Render succeeded, but exposed a format bug: `final_output.mp4` was 1080x1920 for a 237.672s video. Videos longer than 180 seconds should be horizontal, so the renderer now switches `--orientation auto` outputs over 180 seconds to 1920x1080.
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
- `channels.json` now uses ElevenLabs-prefixed AI33 voice ids for all seven channels. Edge voice ids remain only historical placeholders and should not be used for production publishing.
- Raw ElevenLabs candidate ids provided from AI33 Voice Library screenshots/readback must be written with AI33 prefixes in this repo, for example `elevenlabs_cCYjmrGZaI86GUJ7F2Nn`. Currently documented candidates include active pairs for Russian, English, German, LATAM Spanish, Brazil Portuguese, French, and Italian, plus spare/alternate voices.
- Voice selection is per channel and per role; there is no need to find one universal voice for every language. `acc4` now has a Spanish Latin-accent narrator/comment pair in `channels.json`: `elevenlabs_22VndfJPBU7AZORAZZTT` for title/body narration and `elevenlabs_8mBRP99B2Ng2QwsJMFQl` for comments. AI33 metadata readback confirmed both as Spanish `es-AR` with `latin american` accent. This still needs a short AI33 sound test before public use.
- `acc5` now has a Brazilian-accent narrator/comment pair in `channels.json`: `elevenlabs_dX7gRq1dIvLTgUaWpEFn` for title/body narration and `elevenlabs_4r3G9XKliGgVZLKMgjik` for comments. AI33 metadata readback confirmed both as Portuguese `pt-BR` with `brazilian` accent. This still needs a short AI33 sound test before public use.
- `acc1` now has a standard Russian narrator/comment pair in `channels.json`: `elevenlabs_rQOBu7YxCDxGiFdTm28w` for title/body narration and `elevenlabs_ymDCYd8puC7gYjxIamPt` for comments. AI33 metadata readback confirmed both as Russian `ru-RU` with `standard` accent. This still needs a short AI33 sound test before public use.
- `acc3` now has a standard German narrator/comment pair in `channels.json`: `elevenlabs_aTTiK3YzK3dXETpuDE2h` for title/body narration and `elevenlabs_LB5G0Z4EP98YaEgL654m` for comments. AI33 metadata readback confirmed both as German `de-DE` with `standard` accent. `elevenlabs_5KvpaGteYkNayiswuX2h` is documented as a spare older German male voice. This still needs a short AI33 sound test before public use.
- `acc2` now has a US English narrator/comment pair in `channels.json`: `elevenlabs_sB7vwSCyX0tQmU24cW2C` for title/body narration and `elevenlabs_DODLEQrClDo8wCz460ld` for comments. AI33 metadata readback confirmed both as English `en-US` with `american` accent. `elevenlabs_nzFihrBIvB34imQBuxub` is documented as a spare young English male voice. This still needs a short AI33 sound test before public use.
- `acc6` now has a France-standard French narrator/comment pair in `channels.json`: `elevenlabs_wufFsVwuYBePWKO6dMMN` for title/body narration and `elevenlabs_i6ke7jvmGEVUyV4zjSaT` for comments. AI33 metadata readback confirmed `wuf...` as French `fr-FR` standard male and `i6...` as French `fr-FR` Parisian female. `elevenlabs_93nuHbke4dTER9x2pDwE` remains a Québec male spare. This still needs a short AI33 sound test before public use.
- `acc7` now has a standard Italian narrator/comment pair in `channels.json`: `elevenlabs_ImsA1Fn5TNc843fFdz99` for title/body narration and `elevenlabs_RXoaSpLaWTEckJgPUBG3` for comments. AI33 metadata readback confirmed both as Italian `it-IT` with `standard` accent. This still needs a short AI33 sound test before public use.
- `.github/workflows/voice_metadata_check.yml` and `scripts/check_ai33_voice_metadata.py` provide a no-audio readback path for AI33 voice metadata through the repository `AI33_API_KEY` secret. The workflow uses `GET /v3/voices?provider=elevenlabs&search=<voice_id>`, prints only sanitized metadata for requested voice IDs, and must not call `/v3/text-to-speech`.
- Current remaining voice coverage: all seven channels have narrator/comment pairs configured. Remaining blocker is sound quality verification, not missing catalog coverage.
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
- `render.py` now auto-detects default `narration.mp3` and `narration.json`, passes them to RedditSim as `audio`, `transcript`, and `karaoke=1` query parameters, captures deterministic karaoke frames when transcript words are available, and merges the audio track into `final_output.mp4`. If transcript/audio are provided but karaoke cannot initialize, render fails instead of falling back to typewriter animation. Karaoke mode does not add extra words, lower captions, or overlay text; it highlights the currently spoken word directly in the existing Reddit card text with a bright gold treatment. Render orientation is duration-aware: `<=180s` stays vertical 9:16, `>180s` becomes horizontal 16:9. A local no-spend horizontal karaoke smoke was visually checked with silent audio/transcript and confirmed the gold highlight appears on the Reddit card text.
- `style.css` now hides editor/sidebar/HUD/desktop-nav/sidebar/safe-zone widgets under `.clean-mode` and `.render-mode`, including desktop layout states. The 16:9 render layout uses a wide clean Reddit card with horizontal-specific spacing so long-form output is not a vertical canvas with empty side filler.
- `.github/workflows/auto_publish.yml` and `.github/workflows/video_dry_run.yml` now pass both `AI33_API_KEY` and `VECTORENGINE_API_KEY` to the TTS/localization step.
- `.github/workflows/audit_voice_youtube.yml` is a manual audit workflow for two isolated checks: short AI33 voice samples through `scripts/generate_ai33_voice_samples.py`, and YouTube refresh-token mapping via `uploader.py --check-channel-only` for `acc1` through `acc7`. It does not fetch Reddit, call VectorEngine, render video, or upload to YouTube.
- Audit run `28457170166` on 2026-06-30 generated all 14 AI33 voice samples successfully and uploaded the `ai33-voice-samples` artifact. The local review page is `build/audit/run_28457170166/ai33-voice-samples/20260630T154616Z/voice_samples_review.html`.
- Mapping-only audit run `28458168727` saved per-account logs under `build/audit/run_28458168727/youtube-mapping-acc*/acc*.log`. All seven accounts reached YouTube with repository secrets but failed before channel comparison with Google `403 insufficient authentication scopes`; the current refresh tokens do not permit `channels.list(mine=true)`. Because the API could not read the authenticated channel title/handle, the audit could not yet compare against the country/language-bearing channel names in `channels.json`.
- `scraper.py` now supports `--time auto`, `--topic-family`, `--max-ai-candidates`, `--candidate-limit`, and `--similarity-threshold`. `auto` mode scans capped topic-family source plans rather than only `top/week`, then sends only the top bounded pool to Gemini.
- `published_history.json` remains backward-compatible with the old `{post_id: [channels]}` shape; the next scraper save migrates future entries to versioned records with story signatures, keyword signatures, topic family, time window, velocity, fatigue penalty, virality score, and AI quality data.
- `.github/workflows/auto_publish.yml` now supports manual `topic_family` test runs and uses `privacy_status=unlisted` by default for manual dispatch. Scheduled cron entries are also temporarily `unlisted` until the YouTube token/channel mapping is verified. The workflow and `video_dry_run.yml` use `time_filter=auto` by default for topic-family windows and set `AI_QUALITY_FAIL_OPEN=0`, explicit `MAX_AI_CANDIDATES`, `STORY_SIMILARITY_THRESHOLD=0.72`, and `TOPIC_FATIGUE_LOOKBACK=10`.
- `uploader.py` now supports `--check-channel-only`, `--privacy-status public|unlisted|private`, merges `tags` + `seo_keywords`, appends returned `hashtags` to the description, passes metadata language to YouTube, verifies the authenticated YouTube channel before upload, and reads back uploaded video metadata afterward. `auto_publish.yml` runs the channel check before any content-generation spend. Manual and scheduled runs stay `unlisted` until token mappings are proven.

## Known Blockers

- Topic-family weights in `channels.json` are configured but not yet validated against retention/readback.
- Public scheduled publishing is blocked until all `YOUTUBE_REFRESH_TOKEN_ACC1-7` values are reissued with sufficient YouTube Data API scopes and audited against `channels.json`. User/browser readback showed videos landing on the wrong target channel; current tokens cannot be mapped because `channels.list(mine=true)` returns `403 insufficient authentication scopes`.
- Public/manual `auto_publish.yml` no longer has an Edge-voice blocker in `channels.json`; all seven channels pass the ElevenLabs-prefix requirement. Public use is still blocked until short sound tests and YouTube token/channel mapping are verified through the isolated audit workflow or equivalent local env readback.
- `uploader.py` still needs authenticated YouTube metadata readback before public production use, especially verifying title/description/tags/language and channel id after upload.
- There is no project safe-trash helper under `scripts/`, so generated scratch artifacts should not be deleted by agents without adding a safe workflow first.

## Next Steps

1. Listen to `build/audit/run_28457170166/ai33-voice-samples/20260630T154616Z/voice_samples_review.html` and decide which voices to keep or replace.
2. Reissue every `YOUTUBE_REFRESH_TOKEN_ACC1-7` with YouTube upload plus read-only/channel-read permission, then rerun `.github/workflows/audit_voice_youtube.yml` with `check_youtube_mapping=true` and `generate_voice_samples=false`.
3. Replace any YouTube refresh token whose authenticated channel does not match the expected handle/name before any public scheduled run.
4. Add authenticated uploader readback for title, description, tags, language, privacy, channel id, and optionally thumbnail state.
5. Run one intentional VectorEngine image generation smoke if custom thumbnail generation should be enabled in the automated path.
6. Tune `topic_mix` weights from live candidate variety, Gemini verdicts, and YouTube retention once account mapping is safe.
