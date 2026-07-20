# Design System: ChonkerTalks / RedditSim

**Installed:** 2026-07-08
**Format source:** https://github.com/VoltAgent/awesome-design-md
**Primary sources:** `docs/README.md`, `docs/PROJECT_STATE.md`, `style.css`, `app.js`

## 1. Visual Theme & Atmosphere

This project creates story-entertainment videos with clean Reddit-style cards. The visual system should feel native to the RedditSim format: dark, legible, focused on the story, and free from editor UI during render.

The goal is not a general SaaS interface. The video frame is the product.

## 2. Color Palette & Roles

Use the existing RedditSim themes first:

- Reddit Midnight / dark surfaces for most rendered Shorts and long-form cards;
- Reddit Light only when intentionally selected for the format;
- Reddit orange and blue as platform-native accents, not broad decorative gradients;
- gold/yellow karaoke highlight only when the workflow explicitly requires karaoke.

## 3. Typography Rules

Render text must be readable in 9:16 and 16:9 video frames. Use the existing system UI stack and render-mode sizing in `style.css`. Do not squeeze long posts onto one screen; use slide chunking.

## 4. Component Stylings

- **Reddit Card:** centered, clean, story-first.
- **Slides:** first story screen can show header/title, middle continuations show text only, final screen reveals footer metrics.
- **Comments:** comment slides are separate and should not clutter story slides.
- **Clean/Render Mode:** hide editor/sidebar/nav/safe-zone controls.
- **Karaoke:** off by default in current dry-run/review artifacts unless explicitly required.

## 5. Layout Principles

Shorts up to 180 seconds render vertical 9:16; longer videos default to horizontal 16:9. Both modes need no horizontal overflow, no clipped text, no visible editor controls, and stable audio/video timing.

## 6. Do's And Don'ts

- Do verify with rendered MP4/frame previews, not code-only claims.
- Do keep source-backed story/adaptation/evidence gates before upload.
- Do not use decorative backgrounds that distract from the story card.
- Do not copy external brand DESIGN.md profiles into the video frame.

## 7. Agent Prompt Guide

Before visual/render work, read `docs/README.md`, `docs/PROJECT_STATE.md`, this `DESIGN.md`, and the relevant renderer files. Any live workflow that calls Reddit/Gemini/AI33/YouTube can spend provider quota and needs explicit approval.

## 8. Acc1 Editorial Motion Target

The baseline Reddit-card renderer above remains valid for `reddit_pages`.
For the separate `editorial_motion_v1` SAGA/BUNDLE lane, the approved target is
`ink_gouache_story_pages_v1`, shown in
`docs/assets/acc1-ink-gouache-topic-layouts-v1.png`.

- Use adult Ink & Gouache Reportage: charcoal/ink contours, opaque gouache,
  dry-brush shadow and tactile paper; character scenes are illustrated rather
  than near-photorealistic.
- Preserve believable adult anatomy, expressions and cinematic staging, but do
  not make every scene a full-frame portrait.
- Keep exact names, dates, messages, quotations and evidence in HTML/SVG.
- Select a story family and its page rhythm: `relationships`, `work`, `digital`,
  `memory`, `odd_job`, or `dark_saga`.
- Use one to five unequal panels per page according to the beat; no mandatory
  four-panel grid and no repeated equal-sized panel layout.
- Use photorealism only for real documents, messages, interfaces or archival
  evidence, not as the default character art.
- Do not use superhero/pop-art styling, speech balloons, action words,
  Ben-Day/halftone dots, manga, childlike cartoons, generic scrapbook or a
  repeated equal-panel template.

This is an implemented opt-in profile, not the current renderer default. Its
contract requires a story-family palette, a beat-specific unequal-panel layout
and one episode-wide recurring-character identity description before any image
provider call. `contemporary_cutup_v1` remains the production default until the
new Ink & Gouache canary passes visual, identity-consistency and motion QA and
is explicitly promoted.
