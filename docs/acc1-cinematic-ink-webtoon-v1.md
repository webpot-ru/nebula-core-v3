# acc1 `cinematic_ink_webtoon_v1`

Last updated: 2026-07-20

Status: **local visual candidate; pilot and promotion are not approved yet**.
The root [`frame.md`](../frame.md) is the compact render/generation contract.
The current styleframe is
[`assets/acc1-cinematic-ink-webtoon-styleframe-v1.png`](assets/acc1-cinematic-ink-webtoon-styleframe-v1.png).
It is a 1672×941 PNG with SHA-256
`d5b8cb39228b6bd284dd1d21c4109d7df12a982b2d0da504af5223c4222bdd25`.

## Creative direction

`cinematic_ink_webtoon_v1` is an adult colour web-comic language for all five
acc1 story pillars. It combines modern cinematic composition, readable emotion
and stable recurring characters with ink contours, restrained gouache and
tactile paper. Keep the image approximately 75% clean contemporary webtoon and
25% handmade texture.

Shared invariants:

- believable adult anatomy, expressive faces, stable identity, hair and outfit
  within one story;
- one dominant emotional image rather than a wall of equal panels;
- irregular pages with two or three panels, alternated with full-screen scenes;
- no childlike cartoon, superhero/pop-art, black-and-white manga, generic
  glossy romance-manhwa or near-photoreal AI people;
- generated plates contain no important text. Exact copy is deterministic
  HTML/SVG and subtitles remain a separate SRT track.

## Base palette

| Token | Hex | Role |
| --- | --- | --- |
| Midnight navy | `#101A2C` | night, depth, dark backgrounds |
| Deep teal | `#174B52` | secondary fields, calm tension |
| Warm amber | `#D49345` | light, warmth, attention |
| Coral | `#D76558` | emotion, human emphasis |
| Ivory | `#F1E7D3` | paper, readable light surface |
| Vermilion | `#A83E31` | rare semantic connector or decisive accent |
| Charcoal | `#24252A` | linework and primary type |

Vermilion is not a decorative border. Use it only to connect a message,
object, date, memory or decision whose relationship matters to the narration.

### Pillar adaptations

| Pillar | Dominant treatment |
| --- | --- |
| relationships / family | burgundy, coral, dark blue, warm domestic amber |
| work / money / justice | graphite, cold blue, paper ivory, restrained red |
| confessions / awkward / taboo | plum, dusty pink, electric-blue detail |
| professions / human experience | teal, sodium amber, cobalt and off-white |
| strange / dark / unexplained | indigo, green-black, dirty ivory, dim amber |

The base brand colours remain recognizable, but a single episode uses only its
pillar palette. Do not mix all accents in every scene.

## Formats

### BUNDLE

Four or five stories become separate mini-comics. Each story receives its own
characters and controlled palette variation. Short branded transitions reset
the viewer between stories without inserting the mascot into the plot.

### SAGA

Use more full-screen cinematic scenes, environments and panoramas. Panel pages
appear at turns, discoveries, messages and payoff beats rather than on every
paragraph.

### THREAD

Use a faster portrait/reaction rhythm, usually two or three panels, with
messages or short exact quotations as deterministic overlays. Each response
must still feel visually distinct; do not repeat one reaction template.

## Image and editing density

- Target `16–20` unique illustrations per story, not `6–10`.
- One illustration may yield two or three purposeful crops or depth states.
- A five-story BUNDLE therefore targets roughly `80–100` unique illustrations
  and `180–220` cuts/visual states.
- Introduce a materially new visual state every `6–10` seconds, adjusted to
  narration beats. A crop alone does not count if it communicates nothing new.
- Recommended long-form mix: 50% full-screen cinematic illustrations, 30%
  unequal-panel pages, 15% messages/documents/photos/evidence, 5% branded
  transitions, CTA and outro.

These are creative targets, not permission to call an image provider. Every
paid generation run still requires separate exact-scope approval.

## Guided comic-page camera

The recurring technique is a narration-driven **guided reading path** (also
describable as panel reveal, rostrum camera or push-in/pull-out):

1. Show the complete page for about `1.0–1.5` seconds.
2. Push into panel one on its narration beat.
3. Pull back far enough to restore page geography.
4. Pan or push into panel two.
5. Return to the page, then enter panel three or an evidence detail.
6. End on the full page or use a semantic match cut into the next page.

The sequence is not mandatory when the story calls for a full-screen hold.
Camera direction follows speaking rhythm and visual hierarchy, never a blind
equal-duration loop. Store normalized crop rectangles per panel so rendering
is deterministic and seek-safe. Subtle parallax, practical light, water,
screens and paper movement are allowed; face/hand warping is not.

## On-screen text

Narration carries the full story. The image may show only:

- title or chapter marker;
- role/name label when needed for comprehension;
- a key phrase of `3–8` words;
- an exact short source quote;
- date, amount, message or document detail;
- payoff question, CTA or outro copy.

Do not print paragraphs over the comic. Never rely on text generated inside an
illustration. Apply safe margins and test the actual 1920×1080 browser/MP4
frame. Subtitles are independent of decorative type.

## S-tier review gate

A pilot can be proposed for promotion only after the actual MP4 confirms:

- stable recurring character identity across the story;
- clear reading order and no repeated equal-panel template;
- text accuracy, subtitle readability and safe margins;
- no malformed faces, hands or pseudo-text;
- every camera move supports the narrated beat;
- distinct visual treatment across stories without losing channel identity;
- intro, CTA and outro feel related to the comic but do not interrupt it;
- technical render, motion, audio and visual QA pass.

This document records a visual decision only. It does not change
`channels.json`, production defaults, GitHub workflows, provider budgets,
rights state, upload or publication authorization.
