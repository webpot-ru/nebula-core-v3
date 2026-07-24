# Chonker Talks acc1 — format visual system v3

Last updated: 2026-07-24

Status: **current approved creative reference for new acc1 episodes**.

This is the single creative source of truth for the Russian Chonker Talks
channel. It supersedes the former six-series adult-animation, Ink & Gouache,
editorial-collage and standalone cinematic-webtoon reference boards. Those
systems may remain in Git history or technical notes as implementation
evidence, but they must not be used in new image prompts, style comparisons or
episode art.

This approval fixes the visual direction. It does not authorize provider
spend, a GitHub workflow, publication or YouTube upload. The renderer still
needs a separately verified MP4 using these references before the style can be
called production-verified.

## Shared channel language

All formats use one recognizable illustrated universe:

- fully drawn adult graphic novel; never photography, photomontage,
  photorealistic reconstruction or stock-video imitation;
- believable adult anatomy, expressive mature faces and stable identity,
  hair, wardrobe and age inside one story;
- elegant variable ink contours, restrained cel shading, subtle gouache and
  paper grain;
- cream gutters, unequal panels and one dominant emotional image per page;
- contemporary Russian or broadly European-looking environments and clothing;
- narration carries the story; provider images contain no paragraphs,
  captions, speech bubbles, logos or generated pseudo-text;
- exact Russian text, subtitles, dates, messages and UI are rendered later in
  deterministic HTML/SVG;
- the mascot belongs only to channel identity, intro, transition, CTA and
  outro, never inside a reconstructed story scene.

Forbidden defaults: orange-dominated art, childlike cartooning, glossy romance
manhwa, black-and-white manga, superhero pop art, identical panel grids,
repeated reaction templates and mechanical equal-duration zoom loops.

### Provider canvas and video crop

- Fixed-release image generation requests a horizontal `1536x1024` provider
  canvas and never asks the provider to infer portrait, square or automatic
  orientation.
- The complete page, every panel, face, hand and evidence object stays inside
  the centered 16:9 safe zone. Only unimportant paper texture or atmospheric
  bleed may occupy the additional top and bottom area.
- A verified landscape response is preserved with its checksum, then
  deterministically normalized to the `1536x864` video page. The permitted
  crop is bounded; portrait, square, undersized or excessive-crop responses
  fail closed and are never silently rotated, stretched or accepted.
- The one-image GitHub canary uses the exact first production prompt before a
  new batch can be approved. It has no automatic retry, AI33 or YouTube access.
  Run `30100693747` returned a `1672x941` landscape image in exactly one call;
  no-spend recovery `30101554291` reused that frozen artifact and verified the
  final `1536x864` normalization with no new provider or YouTube action.

### Meaning-led panel rhythm

A page is not fixed at three panels. The planner selects its internal grammar
from the source-bound narrative beat, never randomly:

- **1 panel** — hook, geography, intimate aftermath or a final emotional hold;
- **2 panels** — contrast: person/reaction, message/consequence or before/after;
- **3 panels** — ordinary development with one dominant interaction and two
  supporting details;
- **4 panels** — escalation: a major scene plus cause, reaction and evidence;
- **5 panels** — one turning point only: a dominant emotional image surrounded
  by four short source-supported fragments.

`BUNDLE`, `SAGA` and `THREAD` use different named beat sequences but share this
rule. The five-panel mosaic is an accent, not a default; no adjacent pages may
be selected merely to satisfy a numerical pattern. The exact panel count is
bound into every newly generated source pack for renderer and QA traceability.

## Format references

### BUNDLE — several complete stories

Reference:
[`bundle-relationships-v1.png`](assets/acc1-format-visual-system-v3/bundle-relationships-v1.png)

SHA-256: `4ddde856fe5bdf484f812752ca5dd2fb19208a15077db89277c7f6290feca0c8`

- Three to five stories from one content pillar become separate mini-comics.
- The episode keeps one base palette and drawing grammar.
- Every story receives a separate character lock, location, supporting accent
  colour and panel rhythm.
- Characters, clothing and story-specific motifs never leak into the next
  story.
- A short branded chapter transition resets the viewer before the next story.
- The first page of every story is established in full before guided reading.

### SAGA — one continuous long story

Reference:
[`saga-strange-v1.png`](assets/acc1-format-visual-system-v3/saga-strange-v1.png)

SHA-256: `dcb000a564ca41d89a3872607cfe71f2ae08565764bb44981dccf96a2fc89176`

- One recurring cast, wardrobe and environment system spans the episode.
- Wide establishing scenes and panoramic hero panels dominate.
- Smaller panels appear at discoveries, messages, decisions and payoff beats.
- Layered foreground, character and background planes support restrained 2.5D
  parallax.
- Camera moves follow narrative meaning: establish, inspect a relevant detail,
  hold on the reaction and transition without a mandatory reset.

### THREAD — one prompt, many materially different responses

Reference:
[`thread-confessions-v1.png`](assets/acc1-format-visual-system-v3/thread-confessions-v1.png)

SHA-256: `ed0ecab08350914bbe90982d407a6b4301d13890e2229cc42960dc22b6fdc585`

- The prompt is the visual anchor; each response becomes a distinct portrait
  or compact situational vignette.
- Response blocks follow a zigzag i-flow suitable for mobile viewing inside a
  horizontal 16:9 frame.
- Each response changes character, pose, environment fragment and emotional
  role; one universal reaction card is forbidden.
- Exact response text remains a deterministic overlay and the configured
  comment voice remains separate from the narrator.

## Topic adaptations

The format controls page structure. The content pillar controls palette,
lighting, environment density and pacing. It does not create a different art
brand.

| Pillar | Treatment |
| --- | --- |
| Relationships / family | aesthetic webtoon plus soft cinematic cel shading; ivory, muted olive, dusty rose, burgundy and deep navy; intimate rooms and expressive close-ups |
| Work / money / justice | textured graphic realism plus cel shading; graphite, cold blue, paper ivory and restrained red; denser workplaces, objects and documents |
| Confessions / awkward / taboo | airy webtoon minimalism; plum, dusty pink, cool lavender and desaturated teal; faces, hands, phones and negative space |
| Professions / human experience | observational graphic comic; teal, cobalt, off-white and a restrained muted yellow; more environmental and tool detail |
| Strange / dark / unexplained | dark cinematic cel shading with limited neo-noir at peaks; indigo, green-black, dirty ivory, steel blue and tiny dim brass accents; no gore default |

Do not mix unrelated pillars inside one BUNDLE. A relationships BUNDLE may
vary domestic sub-palettes between stories but must not suddenly switch to the
visual grammar of a horror SAGA.

## Motion and text

- Establish the full page for roughly 1.0–1.5 seconds when geography matters.
- Move to the character, interaction, object or evidence named by narration.
- Use a hold, pan, semantic match cut or restrained settle; do not repeat the
  same push-in/pull-back sequence for every panel.
- A new visual state should communicate a new beat, not merely satisfy a timer.
- The fixed subtitle band remains stationary while the comic moves behind it.
- Intro, transparent subscribe CTA and outro do not interrupt narration
  captions; the active one-line subtitle remains visible in the fixed band
  whenever narration continues.
- Keep important faces, hands and evidence outside the subtitle exclusion area.

## Approval boundary

The three images above are approved format references produced with the
built-in Imagen path. They demonstrate creative intent only. They are not a
finished episode, renderer QA proof, provider budget authorization, GitHub
artifact or YouTube approval.
