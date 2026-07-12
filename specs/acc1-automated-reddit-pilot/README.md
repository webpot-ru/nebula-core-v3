# acc1 Automated Reddit Pilot

## Outcome

Two repeatable, artifact-only `acc1` pilots can take 3-6 complete Reddit stories through source-preserving Russian translation/editing, independent review, Eleven v3 narration, a 45-60 minute 16:9 compilation render, and fail-closed QA without YouTube upload or publication-history writes.

## Invariants

- Reddit is the source; Reddit-only claims are labelled fiction or unverified personal accounts, never verified fact.
- Test runs use `rights_mode=test_only_not_cleared` and `publication_authorized=false`. Rights do not block internal artifacts, but the artifacts cannot authorize publication.
- The complete source body is snapshotted and hashed before any paid call.
- `r/nosleep` fiction and `r/LetsNotMeet` unverified encounters are tested as separate compilations and never mixed.
- Events, characters, order, and ending are preserved; the model may improve Russian narration but may not expand a source into a new plot.
- Deterministic validation runs before provider calls and between every paid stage.
- Review may request a targeted story correction at most twice. A third failure is `BLOCKED_EDITORIAL`.
- Metadata is produced only from the accepted Russian script.
- AI33 requests and validates `eleven_v3`; story/chunk checkpoints prevent duplicate paid submissions on resume.
- The lane has no uploader, YouTube secret, history mutation, or public-publish step.

## Slice graph

1. [S01: Episode contract](S01-episode-contract.md)
2. [S02: Source selection](S02-source-selection.md)
3. [S03: Translation and story editing](S03-plan-and-scenes.md)
4. [S04: Review loop](S04-review-loop.md)
5. [S05: Audio, storyboard, render and QA](S05-media-and-qa.md)
6. [S06: GitHub pilot workflow](S06-github-workflow.md)
7. [S07: Audience learning and breakout loop](S07-growth-loop.md)
7. [S07: Audience learning and breakout loop](S07-growth-loop.md)

## Explicit non-goals

- No public or unlisted YouTube upload in the first two pilots.
- No change to `channels.json` or the existing Shorts/Reddit-card workflow.
- No automatic claim that a Reddit story is true.
- No paid run until the exact pilot count and provider scope are approved.

## First review surface

The first checkpoint is a fixture-built `compilation_script.json` plus validation report. It proves distinct sources, 45-60 minute target accounting, disclosures, ending preservation, safe narration, and the revision ceiling before Gemini or AI33 can be called.

## Breakout principle

Automation is not successful when it merely publishes more videos. It is successful when each result changes the next source choice, hook, packaging, scene structure, performance direction, or franchise bet. No topic signature receives higher production allocation from one outlier; it must win repeatedly against same-channel, same-format baselines.
