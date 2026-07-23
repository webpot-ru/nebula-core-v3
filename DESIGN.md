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

## 8. Current acc1 illustrated target

The baseline Reddit-card renderer above remains valid for `reddit_pages`.
For new acc1 visual work, the approved target is
`acc1_format_visual_system_v3`, documented in
`docs/acc1-format-visual-system-v3.md` with three references under
`docs/assets/acc1-format-visual-system-v3/`. Older six-series animation,
Ink & Gouache, cinematic-webtoon and collage boards are historical only and
must not enter new prompts.

- Fully drawn adult graphic novel: stable believable adults, variable ink,
  restrained cel shading, matte gouache, paper grain and cream gutters.
- `BUNDLE` uses separate mini-comics and separate character locks per story.
- `SAGA` keeps one cast and geography, with panoramas and discovery panels.
- `THREAD` keeps the prompt as anchor and gives every response a distinct
  portrait or situational vignette in a zigzag reading flow.
- Topic pillars adapt palette and density without changing the channel's art
  universe.
- Exact Russian text, dates, messages, UI and subtitles are HTML/SVG overlays;
  AI art contains no pseudo-text or narration paragraphs.
- Photography, photomontage, near-photoreal reconstruction, orange-dominated
  universal styling, glossy manhwa, superhero pop art, manga and childlike
  cartooning are forbidden defaults.
- Camera movement follows the narrated beat; equal-duration mechanical zoom
  loops and mandatory resets are forbidden.

The `acc1_format_visual_system_v3` prompt profile and local HyperFrames proof
are implemented. Provider or GitHub execution still requires exact approval.
