# acc1 Automated Reddit Pilot

## Outcome

Two repeatable, artifact-only `acc1` pilots can take a complete Reddit candidate through a Russian long-form episode script, independent editorial review, Eleven v3 narration, a scene-based 16:9 render, and fail-closed QA without YouTube upload or publication-history writes.

## Invariants

- Reddit is the source; Reddit-only claims are labelled fiction or unverified personal accounts, never verified fact.
- Test runs use `rights_mode=test_only_not_cleared` and `publication_authorized=false`. Rights do not block internal artifacts, but the artifacts cannot authorize publication.
- The complete source body is snapshotted and hashed before any paid call.
- Long scripts are planned and written per scene; no single model response owns the whole episode.
- Deterministic validation runs before provider calls and between every paid stage.
- Review may request targeted scene changes at most twice. A third failure is `BLOCKED_EDITORIAL`.
- Metadata is produced only from the accepted Russian script.
- AI33 requests and validates `eleven_v3`; scene-level checkpoints prevent duplicate paid submissions on resume.
- The lane has no uploader, YouTube secret, history mutation, or public-publish step.

## Slice graph

1. [S01: Episode contract](S01-episode-contract.md)
2. [S02: Source selection](S02-source-selection.md)
3. [S03: Plan and scene writing](S03-plan-and-scenes.md)
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

The first checkpoint is a fixture-built `episode_script.json` plus `episode_validation.json`. It proves the contract, runtime accounting, source anchors, disclosure, change ledger, and revision ceiling before Gemini or AI33 can be called.

## Breakout principle

Automation is not successful when it merely publishes more videos. It is successful when each result changes the next source choice, hook, packaging, scene structure, performance direction, or franchise bet. No topic signature receives higher production allocation from one outlier; it must win repeatedly against same-channel, same-format baselines.
