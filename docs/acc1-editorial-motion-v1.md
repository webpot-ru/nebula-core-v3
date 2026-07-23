# acc1 `editorial_motion_v1`

Last verified: 2026-07-19

> **Historical renderer evidence only.** On 2026-07-22 every creative
> reference board described below was superseded by
> [`acc1-format-visual-system-v3.md`](acc1-format-visual-system-v3.md). Do not
> use the former six-series, Ink & Gouache or editorial-collage boards in new
> prompts. This file remains solely to explain legacy renderer behaviour,
> tests and artifacts.

## Active implementation — six adult animated-comic series

The active profiles are implemented in `acc1_visual_contract.py`, not merely
recorded as style references. The no-spend daily plan carries the exact
`editorial_motion_style_profile`, and the factory re-derives and checks it from
the `pilot_id` before an editorial-motion run can spend credits.

| Pilot | Profile | Repertoire and story behaviour |
| --- | --- | --- |
| 01 relationships/family | `adult_animation_family_v1` | warm domestic rooms, reactions, objects and parallel spaces |
| 02 work/money/justice | `adult_animation_work_v1` | office/transit structures, paperwork, counterpoints and release frames |
| 03 SAGA | `adult_animation_saga_absurd_v1` | quiet empty rooms, odd objects and unease without noir treatment |
| 04 confessions | `adult_animation_confessions_v1` | close emotion, mirrors, phones and memory objects |
| 05 professions | `adult_animation_professions_v1` | tools, routines, workspaces and observation comedy |
| 06 THREAD | `adult_animation_daily_weird_v1` | minimal objects and domestic oddness; visual profile is ready, renderer remains blocked pending the dedicated THREAD hybrid |

Each profile has ten named layouts. `select_adult_animation_layouts()` derives
a unique sequence from `SHA-256(profile + source_id)`: one source always gets
the same ordered layouts, while later videos in the same thematic lane use a
different composition. No episode silently mixes profiles or relies on random
layout selection. This is the anti-template contract.

The former preview builder and creative board were retired to project Trash on
2026-07-22. The captured direct HyperFrames render remains historical evidence:
`build/acc1-adult-animation-work-preview-v2/manual-silent.mp4` (48 seconds,
1920x1080, 30 fps). It reuses crops of the locked reference board only to
prove distinct panel geometry and seek-safe motion; it is not a final image
generation canary and used no provider credit.

### Lightweight Chrome work-page proof — local visual test

The earlier Motion Canvas work pilot was stopped at the user's request and its
scratch output was moved to project Trash. The active low-storage test is
`build/chrome-comic-page-test/work-comic-pages-silent-v3.mp4`: a silent,
10.000-second H.264/yuv420p, 1920x1080, 30-fps MP4 rendered by local Google
Chrome DevTools plus FFmpeg. It uses two original `adult_animation_work_v1`
pages: the first has three unequal panels and the second has four. The camera
slowly crosses each page with one cream-paper flash transition. There are no
captions, speech bubbles, generated text, audio, factual overlays or real
source claims in this visual test.

Exactly two VectorEngine `gpt-image-2` attempts completed with zero automatic
retries. Their prompts are hash-recorded, and the output checksums are in
`build/chrome-comic-page-test/paid-image-attempts.json`. Only the two pages,
HTML source, render report and 2.2 MB MP4 are kept in the live build folder;
the JPEG frame cache and transient Chrome profile were moved to project Trash
after visual inspection. The v1/v2 test videos are superseded and also in
project Trash. This is local visual proof only, not
a production-factory integration or release candidate: there is no narration,
rights clearance, GitHub run, upload or YouTube action.

### Intro, CTA and outro packaging proof

`build/chrome-comic-page-test/work-comic-pages-packaging-demo.mp4` is a silent
22.000-second Chrome/FFmpeg proof that layers deterministic Russian text over
the same art: a hook card, a single mid-story like/subscribe CTA, and a
question-led outro. The text is authored in
`scripts/render_chrome_comic_page_test.py`, not drawn by an image model, so it
is exact and can be substituted from an approved episode script. No new image,
AI33, GitHub, upload or YouTube operation occurred. Its JPEG scratch frames and
Chrome profile were moved to project Trash after visual inspection.

The production script contract now mirrors that shape without using the demo
copy verbatim. `intro_contract` remains a topic-playoff-bound cold open plus
truth disclosure and first-source cue. `mid_story_cta_contract` selects one
exact source anchor at the deterministic source break and produces a short
discussion/subscription line from the episode format and pillar. `outro_ru`
stays question-led and grounded in the first source/pillar. The narration
builder emits the CTA as a separate `mid_story_cta` service segment, and the
editorial-motion contract renders it as a short HTML/SVG factual-text scene
using the existing verified story asset pack. This is still artifact-only:
production defaults, provider spend, GitHub workflows, YouTube upload and
publication authorization are not changed by the CTA contract.

## Decision

`editorial_motion_v1` is the opt-in SAGA/BUNDLE motion-design mode for the
adult editorial-collage direction. Motion-plan v2 locks the reusable visual
profile `contemporary_cutup_v1`: photographic material is integrated into
cobalt/coral/butter torn-paper planes, a detail plate becomes a portal, and
the camera travels through overlapping virtual layers instead of presenting
paper cards, dossiers or newspapers. One source-bound system selects semantic
motion according to the narration:

- `nested_collage_zoom` for the hook and portal transitions;
- `living_photo_depth` for observational story beats;
- `digital_memory_stack` for messages, screens and digital traces;
- `evidence_transform` for documents and proof;
- `graphic_timeline` for dates and chronology;
- `dark_semantic_reveal` when a later fact changes the meaning of an earlier image.

Exact names, dates, quotations, captions and evidence labels are deterministic
HTML/SVG. `gpt-image-2` creates illustration plates only; generated text is
never accepted as factual evidence.

### Historical target art direction: `ink_gouache_story_pages_v1`

On 2026-07-18 the user replaced the earlier full-frame / near-photoreal
graphic-novel target with an adult **Ink & Gouache Reportage** system. The
former visual board (SHA-256
`c3a18ef4ee2714a7b85537d73e1b3b4a8135cb468a469aaa33cf691801a220f1`)
was retired to project Trash on 2026-07-22 and is not an allowed prompt input.

This is not superhero/pop-art, a conventional motion comic, a scrapbook, or a
fixed four-card template. It uses:

- clearly illustrated but emotionally credible adult characters: expressive
  charcoal/ink contours, restrained opaque gouache, dry brush and tactile
  paper grain rather than default photorealistic character art;
- a page may have **one to five unequal panels**, chosen by the beat; full-frame
  scenes are allowed, and equal four-panel grids are prohibited;
- an irregular page rhythm: one dominant emotional frame, narrow time/evidence
  slits, small object details, or memory fragments may sit beside a wide scene;
- a restrained hand-drawn vermilion connective line only where it carries a
  relationship between a message, object, date, memory or decision;
- separate character, environment and object depths suitable for HyperFrames
  parallax, panel-to-panel camera travel and semantic reveals;
- exact HTML/SVG for messages, dates, quotations, labels and evidence.

The channel identity remains the drawing, paper treatment, typography and
motion language; the palette and page rhythm change with the story family:

| Family | Palette and treatment |
| --- | --- |
| `relationships` | terracotta, indigo, tobacco brown, warm lamp amber; dominant emotional frame plus message/object fragments |
| `work` | office green, paper cream, charcoal; narrow vertical routine panels plus one wide release frame |
| `digital` | electric blue, black, cold white, acid-lime accent; phone/interface space as a large panel with inset traces |
| `memory` | faded peach, dusty teal, warm paper; scattered unequal fragments around one central recollection |
| `odd_job` | sodium orange, cobalt and off-white; two cinematic wides plus a small symbolic detail |
| `dark_saga` | midnight blue, dirty ivory, restrained burgundy; one atmospheric large scene cut by narrow evidence slits |

Photorealistic material remains allowed only when the story needs a real
document, interface, message, archival source or other evidence treatment. It
must not become the default character/scene art. `ink_gouache_story_pages_v1`
is now implemented as a separate opt-in profile. Before provider spend it
requires one story-family palette and one supported unequal-panel layout for
every asset pack, plus an episode-wide recurring-character identity contract.
The renderer applies eight distinct beat choreographies instead of placing new
images into one repeated page. `contemporary_cutup_v1` remains the production
default until the new canary passes visual, identity-consistency and motion QA
and the user explicitly approves promotion.

## Production path

```text
accepted narration + exact timings
        -> paired source-bound image packs
        -> motion-plan.json + caption-track.json
        -> HyperFrames 0.7.61 / one paused GSAP timeline
        -> Chromium frames + FFmpeg audio mux
        -> mode-aware media QA / review / release evidence
```

HyperFrames is the production renderer. The locally installed `html-video`
0.1.0 repository is useful as an alpha studio, catalog and orchestration layer,
but its adapter is not the final renderer: the verified local bridge truncates
fixed compositions beyond 30 seconds. The production factory therefore calls
HyperFrames directly.

HyperFrames 0.7.61 currently injects `data-end` into an audio element and then
rejects that compiled element through its own StaticGuard. The renderer keeps
all video frames and timing HyperFrames-owned, renders a silent MP4, then muxes
the exact checksum-bound final audio through FFmpeg. The report records
`audio_mux=ffmpeg_post_render`.

## Image contract and spend

Every pack contains exactly two independently movable images:

1. `hero_plate` — broad environment and story context;
2. `detail_plate` — the object, screen, document or reinterpretation used by
   the semantic transition.

The renderer reuses these two coordinated plates as deterministic virtual
layers: full environment, irregular hero cut-out, phone/portal crop, isolated
object crop and foreground tear. This avoids separate unreferenced generations
silently changing a person's identity while still providing 2.5D parallax.

The ordinary production target is 8-12 images for the first artistic canary.
The user-approved working allowance is up to 40 paid image attempts; the hard
factory ceiling is 60 attempts, including failures. Hidden retries are disabled.
The planner can allocate at most 29 packs / 58 story images, leaving the final
hard ceiling intact.

VectorEngine has historically returned 1672x941 for a 1536x864 request. In
this mode only, a near-16:9 result at least as large as the target is preserved
as `*.provider-original.*`, checksum-bound, then center-cropped/resampled to
1536x864. Unsafe aspect ratios or undersized images still fail closed. The
normalization record stores both dimensions and both paths/checksums.

## Files and commands

Main implementation:

- `acc1_editorial_motion.py` — exact scene, motion and caption contracts;
- `compilation_editorial_motion_renderer.py` — preflight, HyperFrames workspace,
  render and report;
- `acc1_episode_images.py` — paired-pack planning and image normalization;
- `compilation_storyboard.py`, `compilation_renderer.py`, `compilation_qa.py` —
  factory routing and QA;
- `acc1_episode_manifest.py`, `acc1_release_gate.py` — downstream evidence;
- `assets/acc1/video/editorial-motion/gsap.min.js` — vendored deterministic runtime.

No-provider geometry fixture:

```bash
python3 scripts/build_acc1_editorial_motion_fixture.py \
  --output-dir build/editorial-motion-production-fixture
```

Artistic local fixture using four already-paid `gpt-image-2` plates and no new
provider call:

```bash
python3 scripts/build_acc1_editorial_motion_art_pilot.py \
  --output-dir build/editorial-motion-art-pilot
```

Approved contemporary-cutup pilot using an existing styleframe and no new
provider call:

```bash
python3 scripts/build_acc1_contemporary_cutup_pilot.py \
  --source /absolute/path/to/approved-styleframe.png \
  --output-dir build/contemporary-cutup-pilot
```

Source-locked five-minute silent Reddit pilot (exactly 16 paid image attempts,
zero automatic retries):

```bash
python3 scripts/build_acc1_reddit_five_minute_cutup_pilot.py \
  --output-dir build/reddit-five-minute-cutup-pilot \
  --env-file /absolute/path/to/vectorengine.env \
  --confirm-spend
```

Run the same command with `--dry-run` and without `--confirm-spend` to write the
source lock and exact image plan without calling a provider.

Approved Ink & Gouache Reportage re-render of that same source (separate from
the existing contemporary-cutup proof):

```bash
python3 scripts/build_acc1_reddit_five_minute_ink_gouache_pilot.py \
  --output-dir build/reddit-five-minute-ink-gouache-pilot \
  --env-file /absolute/path/to/vectorengine.env \
  --confirm-spend
```

It uses `ink_gouache_story_pages_v1`: adult illustrated reportage, irregular
one-to-five-panel page rhythm, and no photoreal reconstructed people. The
shared source lock, 16-image cap and zero-retry rule still apply.

Targeted contract check:

```bash
python3 -m unittest \
  tests.test_acc1_episode_images \
  tests.test_acc1_editorial_motion \
  tests.test_compilation_editorial_motion_renderer \
  tests.test_compilation_qa
```

## Verified state

The current long-form visual proof is
`build/reddit-five-minute-cutup-pilot/reddit-five-minute-cutup-pilot.mp4`:
H.264/AAC, 1920x1080, 30 fps, exactly 300 seconds, SHA-256
`6db8beba6973b41fd126365cc6dbfde1c530880fc90a9c9055fdc76a693171d9`.
It adapts the source-locked Reddit/BORU post `1i8nufm` into a 10-second hook and
eight story chapters. The artifact uses eight fresh paired `gpt-image-2` packs:
16 successful provider attempts, zero failed attempts and zero retries. Nine
scenes exercise all six motion modules; HyperFrames 0.7.61 reports PASS with
300 motion samples and zero runtime/layout errors. Ten review frames contain no
black-render failure. One frame sampled 0.5 seconds into a scene intentionally
shows the entrance wipe, and automated contrast QA retains one warning for
small white summary copy over a light photographic region. HyperFrames also
warns that the single HTML file has 75 heavy overlays; the inspected timeline
did not reproduce the documented black-frame failure, but production should
split chapters into mounted sub-compositions before scaling further.

The earlier 20-second contemporary-cutup proof remains useful as a compact
style check. The five-minute artifact proves source-bound paired generation,
chapter-specific composition and the complete local renderer without narration.
It does not prove AI33 synchronization, audience response, publication rights or
release readiness. No GitHub run, YouTube upload, publication, channel default,
OAuth or rights state changed.

On 2026-07-18 the current connected-motion Ink & Gouache Reportage canary
completed locally at
`build/reddit-five-minute-ink-gouache-v6/reddit-five-minute-ink-gouache-s-tier-v6.mp4`.
It is H.264/AAC, 1920x1080, 30 fps, exactly 300 seconds, SHA-256
`5cf32e036e34f983bb6df041878060fe8a2bfea92c5ceedcda7793a84347a37d`.
The source is the same locked `1i8nufm` adaptation. It reuses the 16 accepted
paired `gpt-image-2` plates from v3, so this pass made zero provider calls and
left the worst-case paid total at 38 of the approved 40. The eight story packs
retain distinct page layouts, explicit work/digital/dark palettes and the same
episode-wide identity contract.

The v6 renderer is a connected composition rather than a sequence of decorated
cards: art fills depth fields, typography changes position with the semantic
layout, the vermilion connector appears only when it links evidence, and scene
entrances overlap the previous semantic beat. One root GSAP timeline is the
sole visibility owner; per-section HyperFrames start/duration gates were removed
after they were proven to create one-frame black gaps at overlap boundaries.
HyperFrames 0.7.61 `check` and render passed with zero runtime, layout, motion and
contrast errors. Eleven visual samples are recorded in `contact-sheet.png`
(SHA-256
`1b0b1197202524ef89e9d79c8427f6c6745063e9de33695fdabf5695529ae1dc`).
Exact frame inspection at 46.5, 82.5, 118.75, 227.5 and 263.75 seconds passed;
FFmpeg `blackdetect=d=0.10:pix_th=0.12` found no black intervals. The earlier v3
near-black boundary is superseded. Remaining lint warnings are non-blocking:
intentional reuse of a plate crop, one 383-line generated composition, and 33
heavy-overlay nodes.

The zero-provider rerender path is:

```bash
python3 scripts/rerender_acc1_ink_gouache_pilot.py \
  --source-dir build/reddit-five-minute-ink-gouache-v3 \
  --output-dir build/reddit-five-minute-ink-gouache-v6
```

This canary is local-only, silent, `publication_authorized=false`, and does not
change the current production/default `contemporary_cutup_v1` profile.
