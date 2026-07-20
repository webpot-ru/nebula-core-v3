# acc1 Russian Reddit Story Strategy - 2026-07-13

## Decision

`acc1` is a Russian Reddit-story entertainment channel, not a horror-only channel and not a random translated-post feed.

Viewer promise:

> Самые захватывающие истории, признания и обсуждения Reddit на русском: сильный конфликт, эскалация и полноценная развязка без выдуманных продолжений.

The channel keeps the copper Chonker mascot, `@ChonkerTalksRussia`, the male primary narrator, and the female comment voice. The selected animated reading-room loop remains the current compatible baseline, while a separate full-screen cinematic mode is staged by [`acc1-cinematic-production-plan-2026-07-16.md`](acc1-cinematic-production-plan-2026-07-16.md). Horror remains a recognizable series inside the channel. The channel name, description, banner copy, content pillars, episode formats, packaging rules, and pre-production greenlight change.

This is a confirmed local strategy change. It is not yet applied to YouTube. `channels.json.channel_branding.status` must remain `local_proposal_not_applied_to_youtube` until an authorized channel update and live readback succeed.

## Public Brand Package

- Proposed name: `Chonker Talks — Истории Reddit`
- Handle: keep `@ChonkerTalksRussia`
- Banner copy: `CHONKER TALKS` / `ИСТОРИИ REDDIT` / `НА РУССКОМ`
- Avatar: keep the same copper cat, cropped to the head, headphones, and microphone; no small text
- Current video baseline: keep the copper-cat loop for the in-flight candidate and all artifacts that declare the existing Reddit/Chonker visual contract. It is imported at `assets/acc1/video/chonker-reading-loop-v1.mp4`, checksum-bound by the adjacent JSON manifest, and locally wired into both compilation workflows; GitHub execution remains unverified.
- Planned format experiment: `cinematic_story_v1` uses full-screen source-bound scene images, deterministic slow camera movement, and a smaller optional Chonker brand anchor. It is not implemented or selected in `channels.json`; promotion requires the comparison and QA gates in the cinematic implementation plan.

Proposed description:

> Самые захватывающие истории, признания и обсуждения Reddit на русском.
>
> Отношения и семейные конфликты, работа и справедливость, неловкие признания, необычные профессии, странные и необъяснимые случаи. Мы сохраняем смысл оригинальных постов, читаем апдейты и лучшие комментарии — без выдуманных продолжений и лишней воды.
>
> Два формата: большие истории с продолжением и тематические подборки ответов Reddit.
>
> Личные рассказы пользователей не подтверждены независимо. Истории из r/nosleep — художественная выдумка.

Local assets:

- Final banner: awaiting the user's safe-area-composed asset; `channels.json.channel_branding.banner_asset` remains `null` until that file is supplied and checked
- `assets/acc1/branding/youtube-banner-safe-area-guide-2560x1440.png` - transparent 2560x1440 overlay with the central 1546x423 all-device safe area
- `assets/acc1/branding/acc1-channel-banner-v1.png` - deterministic reference only, not the selected upload asset
- `assets/acc1/branding/acc1-channel-banner-safe-area-preview-v1.png` - reference safe-area proof; do not upload this guide
- `assets/acc1/branding/acc1-channel-avatar-v1.png` - current 800x800 local avatar candidate
- `assets/acc1/branding/chonker-reading-source-frame-v1.png` - reference frame from the user-selected loop
- `scripts/build_acc1_brand_assets.py` - deterministic local rebuild command

Rebuild without any provider call:

```bash
python3 scripts/build_acc1_brand_assets.py \
  --source assets/acc1/branding/chonker-reading-source-frame-v1.png \
  --version v1 \
  --output-dir assets/acc1/branding
```

## Content Pillars

1. Relationships and family conflict.
2. Work, money, revenge, and justice.
3. Confessions, awkward situations, and taboo subjects.
4. Professions and unusual human experience.
5. Strange, dark, and unexplained incidents.

These are channel pillars, not permanent `topic_mix` weights. No audience weight is approved before comparable pilot data exists.

## Episode Formats

### `BUNDLE`

- `pilot_01`: 4-5 complete relationships/family stories;
- `pilot_02`: 3-5 complete work/money/justice stories;
- 2,340-3,900 aggregate source words and an 18-30 minute target;
- every component must have a full body, complete payoff, unique author/source/signature, one shared truth mode, and no screenshot/link dependence;
- the 3-5 review candidates must be materially different source sets, not reordered copies;
- comments are not appended to narrative bundles.

| Pilot | Pillar | Allowed subreddits |
|---|---|---|
| `pilot_01` | relationships / family | `relationship_advice`, `AmItheAsshole`, `AITAH`, `offmychest` |
| `pilot_02` | work / money / justice | `MaliciousCompliance`, `prorevenge`, `talesfromyourserver`, `tifu` |

### `SAGA`

- one complete primary story with available authored updates; comments are omitted by default;
- 18-30 minutes;
- title and thumbnail sell one concrete conflict or impossible situation;
- faithful, natural Russian treatment: no invented event, motive, dialogue, or ending;
- source-backed scene beats, original framing, sound direction, and visual direction.

The existing `human_drama` and `dark_curiosity` source families can support bounded manual SAGA reviews. The old 45-60 minute `reddit_horror_compilation` implementation is retained as a specialized dark-series artifact lane; it does not define the whole channel.

Exact current source plans:

| Pilot | Pillar | Allowed subreddits |
|---|---|---|
| `pilot_03` | strange / dark / unexplained | `nosleep`, `LetsNotMeet`, `creepyencounters`, `Glitch_in_the_Matrix` |

Each SAGA source must contain 2,340-3,900 source words, the complete full body, a source-backed payoff and cold-open quote, no screenshot/link dependency, and the correct truth mode. These are discovery gates, not audience proof or publication approval.

Comments are conditional, not a mandatory SAGA ending. `narrative_story` follows only the source post and its authored updates and uses no comment voice. An explicit `question_prompt` or advice request may add a 2-4-answer coda only when those answers directly address the question and improve the episode; a question mark in a dramatic title is not sufficient. This pack is a separate gate, not raw top-score scraping. Preserve exact comment/post/parent IDs, author, integer score, full body/hash, official permalink, and retrieval snapshot hash. Reject deleted/removed/truncated, link- or screenshot-dependent, generic reaction-only, unsafe, irrelevant, duplicate, near-duplicate, and story-restating comments. Require at least two useful roles from counterpoint, empathy, practical context, clarifying question, and concise humor. Bind the configured female comment voice only when the selected comment plan requires it and block on mismatch; never silently fall back to the narrator. The current hardened SAGA workflows still use `--comment-limit 0`, so conditional comment collection is not yet production-wired.

### `THREAD`

- one strong Reddit prompt;
- 8-15 complete, materially different top-level responses;
- 15-25 minutes;
- distinct response blocks and the configured female comment voice;
- no deleted, removed, truncated, duplicate, screenshot-dependent, or outbound-link-dependent response.

`acc1_thread_collector.py` now stores prompt/response IDs, full top-level bodies, hashes, scores, source URLs, dependency flags, runtime-selection evidence, and diversity evidence for 8-15 materially different responses. `acc1_thread_source.py` is the bounded read-only PRAW adapter and refuses network access without `--confirm-reddit-read`. The exact search queries are fixed per pilot: confessions/awkward/taboo, professions/workplace experience, and strange/unexplained experience. The daily factory integration is local-only; live collection and GitHub artifact readback for these exact lanes remain unverified and therefore fail closed when the bounded source cannot satisfy the contract.

Production THREAD selection now requires each response to contain 80-650 source words, pass deterministic prompt-relevance and high-confidence safety/PII blockers, and receive an explicit editorial role. The selected 8-15 responses must total 1,950-3,250 words, contain at least three distinct roles, and cap any one role at 40%. Reddit score orders only already eligible responses and never overrides a blocker; the manifest records all rejection and role evidence.

## Six-Pilot Matrix

| Pilot | Format | Pillar |
|---|---|---|
| 01 | BUNDLE | relationships / family |
| 02 | BUNDLE | work / money / justice |
| 03 | SAGA | strange / dark / unexplained |
| 04 | THREAD | confessions / awkward / taboo |
| 05 | THREAD | professions / unusual experience |
| 06 | THREAD | strange / dark / unexplained |

The daily cycle is interleaved as `01, 04, 02, 05, 03, 06` so adjacent episodes change both format and pillar. The matrix is an experiment design, not a claim that the pillars deserve equal long-term publishing weight. Compare the same 24-hour, 7-day, and 28-day windows before changing the mix.

## One-Dispatch Daily Factory

`acc1_daily_planner.py` derives exactly one Europe/Moscow slot from `channels.json`; it does not consult the superseded numeric `topic_mix`. `.github/workflows/acc1_daily_episode.yml` then runs a fail-closed sequence in order:

1. bounded read-only Reddit source collection with `AI_QUALITY_CHECK=0`, `AI_QUALITY_FAIL_OPEN=0`, exact confirmation, a hard HTTP-request cap, and 3-5 complete finalists; SAGA/BUNDLE can scan up to three configured time windows;
2. deterministic source, truth-mode, lexical/render, safety/PII, viewer-promise, link/screenshot, and fictional-as-real gates;
3. source-dependent paid preflight for credentials, provider/model contracts, source hashes, confirmations, and call ceilings;
4. a 90-day self-hashed spend lease uploaded before the first paid request, followed by separately confirmed/capped Gemini, GPT Image 2 through VectorEngine, and AI33 production. The globally serialized acc1 job reserves every candidate source by ID, canonical URL, exact body SHA and story signature; GitHub reruns, another lease for the same episode, and cross-date source overlap fail closed before paid spend.

Every finalist receives an independent producer and critic review. A candidate is eligible only when both pass, both totals are at least 90/100, all category floors pass, exactly three materially different packaging options are source-backed, and no hard veto exists. Pillar, cold-open, payoff, story-beat, originality, title/thumbnail, and thumbnail-image evidence must name one source and carry a meaningful exact quote rather than a token substring. The thumbnail image prompt is a deterministic non-photoreal template around that quote, and the YouTube description is a deterministic disclosure-plus-source template; neither may contain provider-authored factual additions.

### Intro Contract

The daily factory assembles one deterministic spoken intro after translation, without another provider call. Its order is fixed: the winning 8-30-word source-backed cold open; an exact format/count promise derived from the locked plan and source set; the mandatory truth-mode disclosure; a truthful note that original Reddit publications are listed in the description; the generic line `Спасибо всем, кто помогает каналу расти.`; the Chonker Talks brand sting; and a format-aware cue for the first story or THREAD prompt. The final script is rejected if this order changes, the cold-open hash no longer matches the topic-playoff winner, the source quote is not exact, the disclosure is duplicated, or a sponsor/name/payment claim is inserted without a future checksum-bound supporter manifest.

`Свет можно оставить включённым` is reserved for `strange_dark_unexplained`. Other pillars use the neutral `Устраивайтесь поудобнее` line so the horror tone does not contaminate relationships, work, confessions, or professions. The intro says only that original sources are in the description: the factory does not yet generate a complete post-TTS chapter map, so it must not promise timestamps. The complete intro is capped at 90 spoken words and remains one male-narrator segment; THREAD responses still use the separate female comment voice.

The winning source set, daily plan, episode plan, translations, packaging, scene images, thumbnail, narration chunks/audio, exact text-layout report, runtime estimate, storyboard, render report, final MP4, and review package are joined by canonical SHA-256 bindings with artifact-root-relative paths. Generated images must decode and match exact dimensions before voice spend. Provider attempt journals enter the 24-file final evidence chain; an ambiguous paid request blocks further requests in the same dispatch. TTS timing uses actual verified audio duration and exact provider word alignment when valid. The full Gemini fallback/review ceiling is computed from the exact finalist bodies before the first paid text request: a 15-response THREAD set with one fallback chunk per source needs `107`, while any source-dependent result above workflow cap `128` fails closed. Non-semantic whitespace is collapsed only in the translation working copy; the exact Reddit body and hash stay unchanged in source evidence. Source character density and token length are bounded during deterministic selection, translation size is validated after the exact spoken-number normalization used by TTS, and the cold open is bounded after the same narration preflight. The resulting accepted SAGA/BUNDLE/THREAD envelopes fit the precomputed AI33 cap `96`; actual chunks are checked again before image or voice spend. A pre-TTS runtime estimate and final exact-duration media QA prevent an off-length episode from reaching review-ready status.

The resulting GitHub artifact is a complete episode package, but its strongest status is `READY_FOR_HUMAN_REVIEW`. It cannot guarantee millions of views, does not call YouTube, does not update publication history, and does not authorize unlisted or public release. The first live workflow run remains separately spend-gated and has not occurred. The workflow and exact approved `channels.json` contract must first exist together on the default branch; a feature-branch `--ref` cannot bootstrap a new `workflow_dispatch` file. The lease blocks duplicate paid execution and cross-date source reuse. AI33 submits all missing chunks, persists every task ID before parallel polling, and can resume preserved local state without resubmission under a shared deadline. Production is capped at 300 minutes with AI33's absolute deadline at 240 minutes and 60 minutes reserved for render/QA inside the 360-minute job. These are operational ceilings rather than a proven maximum-cap completion envelope; a fresh runner still lacks full paid-response restore, so the first live run remains a canary requiring manual adjudication after any timeout.

## Mandatory Episode Greenlight

`acc1_story_strategy.py` retains the deterministic no-provider/manual greenlight contract. The new daily artifact lane adds the stricter `acc1_topic_playoff.py`: 3-5 complete review candidates with at least three passing finalists, producer plus independent critic, 90/100 total and category floors, three materially different source-backed packages, and hard vetoes for source/truth/render/viewer-promise failures. Source eligibility alone never becomes publication approval.

| Criterion | Maximum |
|---|---:|
| title-thumbnail concept is clear in two seconds | 25 |
| first 30 seconds deliver the package promise | 20 |
| escalation and payoff are complete | 20 |
| fit with the channel viewer promise | 15 |
| source completeness and honest truth mode | 10 |
| visible original editorial/visual treatment | 10 |

The legacy manual pre-production worksheet uses 75/100. The automated daily factory is stricter: both structured reviews must reach at least 90/100 and every category floor. Automatic blockers include incomplete source, screenshot/link dependence, fiction presented as real, unverified claims presented as facts, weak/missing payoff, wrong pillar, viewer-promise mismatch, or dishonest packaging.

Every passing artifact also needs exactly three conceptually different title-thumbnail-first-screen options, a source-backed 8-30-word cold open, the deterministic intro contract above, at least three story beats, and an originality plan covering editorial framing, visual beats, and sound design.

Bounded SAGA source chain (the first command performs a live read-only Reddit call but no AI/provider generation):

```bash
AI_QUALITY_CHECK=0 python3 scraper.py \
  --channel acc1 --pilot-id pilot_01 --time auto \
  --max-ai-candidates 0 --candidate-limit 10 --comment-limit 0 \
  --allow-disabled-channel --include-source-body-in-queue --no-save-history \
  --producer-queue-output /tmp/acc1-pilot-01-queue.json \
  --output /tmp/acc1-pilot-01-story.json

python3 scripts/review_reddit_topics.py \
  --queue /tmp/acc1-pilot-01-queue.json \
  --output /tmp/acc1-pilot-01-review.json --top-n 6

python3 scripts/build_acc1_greenlight_template.py \
  --queue /tmp/acc1-pilot-01-queue.json \
  --review /tmp/acc1-pilot-01-review.json \
  --output /tmp/acc1-pilot-01-greenlight-draft.json
```

`AI_QUALITY_CHECK=0` records `UNREVIEWED`, not `PUBLISH`. The generated draft is always `DRAFT_BLOCKED`. After a human completes its creative fields, validate it against the same exact queue and review:

```bash
python3 acc1_story_strategy.py \
  --channels channels.json --pilot-id pilot_01 \
  --source-queue /tmp/acc1-pilot-01-queue.json \
  --topic-review /tmp/acc1-pilot-01-review.json \
  --greenlight /tmp/acc1-pilot-01-greenlight.json
```

## Visual System

The current baseline and the planned cinematic experiment must always declare
different `visual_mode` values. Topic-performance comparisons must not silently
mix them. The current in-flight candidate remains on the baseline; cinematic is
implemented and reviewed beside it before any default changes.

Current Reddit/Chonker baseline:

- Keep the copper Chonker on the right, looking toward the text.
- Keep stable Reddit Sans text pages on the left; old text must not move or flash when a new phrase appears.
- Use the title only on page one. Show upvote/comment/share actions exactly once after the final chunk of each story segment; never show them on intro, transitions, intermediate story chunks, or outro.
- For relationships/work stories, retain the warmer neutral grade.
- For strange/dark stories, use a cooler grade and source-backed story images behind the left text region.
- Change a story image or sound beat on a semantic turn, not on an arbitrary timer.
- Use 3-5 source-backed visual scenes per long story. Prefer exact editorial story beats; if they are not available, use the deterministic word-position fallback and record that fallback in the creative manifest.
- Keep both scene imagery and its readability shade left of `mascot_safe_x=1040`, with a feathered boundary, so neither layer darkens the cat, face, or paws.
- Do not use mouth lip-sync for full narration; restrained breathing, blink, whisker movement, steam, and gaze are enough.

Planned `cinematic_story_v1`:

- `SAGA` and `BUNDLE` may use full-screen scene imagery with locally generated
  push-in/pan shots; `THREAD` retains readable response blocks.
- One provider image may supply several deterministic virtual shots. Shot
  planning cannot increase provider spend.
- Full story text is replaced by short optional on-screen phrases plus a
  caption sidecar derived from verified word timings.
- The male narrator and female comment-role contract remain unchanged. Pillar
  controls performance direction, not source facts.
- Exact implementation order, audio contract and promotion gates are canonical
  in [`acc1-cinematic-production-plan-2026-07-16.md`](acc1-cinematic-production-plan-2026-07-16.md).

## Thumbnail Contracts

### SAGA

- one conflict scene;
- one clearly readable emotion or consequence;
- 3-5 honest Russian words at most;
- the story scene is primary; the cat is optional as a small brand anchor;
- no gore, generic collage, or series number at the beginning of the title.

### THREAD

- one large question or confession;
- minimal objects and one recognizable Reddit cue;
- response variety is promised honestly;
- no fake screenshot and no unreadable paragraph on the thumbnail.

Generate or choose the scene without text, then add Cyrillic deterministically. A model must not be trusted to draw final Russian typography.

`thumbnail_generator.py --base-image ... --report ...` implements this as a no-provider local overlay with checksum and dimension evidence. Provider image generation remains separately spend-gated.

## Truth and Originality Boundaries

- Reddit is the source, not independent factual confirmation.
- Preserve source meaning, updates, and endings; do not invent continuations.
- `r/nosleep` is fiction. Other personal accounts are unverified unless independent evidence exists.
- Original value must be visible and audible through selection, Russian editing, packaging, framing, voice direction, scene direction, sound design, and original commentary/question structure.
- The legacy horror rights/editorial system remains the specialized contract for the dark series.

## External-State Boundary

This decision changes local files only. The daily factory can at most produce `READY_FOR_HUMAN_REVIEW`; it does not authorize publication. The legacy `acc1_release_gate.py` still targets the earlier greenlight/report schema and cannot yet promote the new factory artifact after human review; an explicit tested adapter is required before `READY_FOR_UNLISTED_REVIEW`. The cat loop import and deterministic render contract are complete locally. Applying the proposed name, description, avatar, or banner to YouTube; calling Reddit/Gemini/AI33/image providers; running the changed GitHub workflow; rendering a paid episode; or publishing still requires the exact separately approved scope and post-change readback.
