# Russian Horror Editorial System

## Decision

`acc1` is a Russian horror channel built from Reddit stories, not a literal translated-Reddit reading channel.

The primary product is a 45-60 minute themed compilation of 3-6 complete Reddit horror stories built for Russian listening habits. `r/nosleep` fiction and `r/LetsNotMeet` unverified encounters are separate series and are not mixed inside one compilation. Stories receive natural literary Russian editing but are not expanded into new plots: events, characters, order, and ending remain source-preserving.

Reddit is the primary story source and author-acquisition surface. The pipeline should find complete Reddit stories, shortlist them, obtain the required rights from the Reddit author, and then turn the cleared source into an original Russian-language episode. A public post is not a publishing license. The first two explicitly approved internal, artifact-only automation tests may cross into adaptation, paid AI, voice, and render with `rights_mode=test_only_not_cleared` and `publication_authorized=false`; they may not upload or publish. Any distribution beyond that test boundary requires a recorded rights basis.

The dated competitor and policy evidence behind this decision lives in [`russian-longform-competitor-analysis-2026-07-11.md`](russian-longform-competitor-analysis-2026-07-11.md). Current implementation state and blockers live in [`PROJECT_STATE.md`](PROJECT_STATE.md).

## Source Tiers

All `acc1` stories originate on Reddit. Use Reddit sources in this order:

1. Direct Reddit author submissions that explicitly include a written commercial adaptation agreement.
2. Existing Reddit stories whose authors grant permission for translation, abridgment, narration, audiovisual synchronization, and YouTube distribution.
3. Reddit stories carrying a verified compatible open license, with the author and license checked rather than inferred from the platform.
4. Discovery-only Reddit posts whose authors have not yet granted permission. They may be scored and shortlisted, but they are not production scripts.

Attribution is required where the license or agreement requires it, but attribution alone never substitutes for permission.

## Rights Gate

Every candidate needs a fail-closed rights record before any adaptation spend. The record must identify the author, exact source work and parts, rights status, evidence path or hash, allowed commercial use, translation, abridgment and adaptation rights, narration and audiovisual synchronization, territory, term, exclusivity, payment, and required credit.

`submitted_with_permission`, `licensed`, and an independently verified compatible open-license status may proceed to distribution. `discovery_only` and `requested` may be researched and shortlisted; only the two bounded internal test artifacts described above may proceed further, and their manifests must remain publication-blocked. Contacting a Reddit author or changing an external rights record is a separate external write that requires explicit user approval.

## Ideal Story Contract

An ideal story starts with a familiar place, job, or relationship and introduces one impossible rule, anomaly, or threatening encounter. The compilation combines materially different threats and rejects incomplete serial fragments. Every selected story must preserve its own setup, escalation, payoff, and ending.

Promising initial archetypes are a night shift, remote work camp or taiga road, last train, apartment entrance or intercom, archive recording, village, bathhouse, hospital corridor, delivery route, and an inherited house. These are hypotheses from competitor packaging, not proven channel winners. YouTube appeal, retention, and satisfaction data must decide which become franchises.

One breakout video is evidence for a hypothesis, not a franchise decision. Promote a signature only after it repeats across distinct Reddit sources; store the signature as setting, impossible rule, threat, emotional cost, and payoff type so the system learns a reusable viewer promise instead of copying one successful plot.

Runtime is measured from the combined approved Russian narration, not English source characters. The target is 45-60 minutes, with a hard QA envelope of 40-70 minutes. A thin source is never padded; the selector adds another complete story instead.

## Editorial Ownership

The pipeline separates responsibilities deliberately:

1. **Scout** - deterministic collection, deduplication, provenance, structural tags, and demand signals. It proposes leads only.
2. **Producer model** - reads the complete beginning, middle, and ending and returns an advisory shortlist. It cannot approve rights or truth claims.
3. **Rights producer** - a human owner records permission or license evidence and is the only role that can clear a third-party text.
4. **Russian translator/editor** - produces a natural source-preserving Russian narration for each complete story. AI may assist, but it may not invent or expand events.
5. **Russian story editor** - owns natural language, pacing, cultural fit, audience promise, fiction labeling, and the final meaning of the episode.
6. **Continuity reviewer** - compares the script with the licensed canon and the change ledger, catching lost beats, unsupported additions, accidental factual framing, and unresolved series dependence.
7. **Narration director** - approves the performance script and voice direction before AI33/Eleven v3 synthesis.
8. **Visual and sound director** - builds the compilation treatment. Verified Reddit-hosted source photos may appear at the relevant point; arbitrary linked images are not fetched, and a Reddit card is only attribution context.
9. **Pre-publish QA** - checks rights, fiction/claim disclosure, source-versus-script integrity, approved changes, ad suitability, reused-content risk, runtime, packaging truth, TTS contract, and the rendered artifact.

The same model must not silently act as producer, writer, translator, continuity reviewer, and final approver. Independent gates matter more than model branding.

### Internal automation pilots

The first two automation tests may use `rights_mode=test_only_not_cleared` as a non-blocking test marker. This permits private artifact generation only: the manifest must keep `publication_authorized=false`, and the workflow must contain no YouTube upload or publication-history write. It does not clear the source for publication or weaken the production rights gate above.

## Script Contract

The production artifact is a compilation script separate from all source snapshots. It contains a short intro, 3-6 ordered Russian story narrations, short transitions, an outro/question, per-story disclosure, ending-preservation evidence, media manifests, and change ledgers.

A licensed adaptation may reorganize or dramatize only what the agreement allows. Any newly written bridge, composite detail, dialogue, or ending must be identified in the change ledger and approved by the Russian editor and continuity reviewer. It must never be presented as something the source author claimed.

An ambiguous ending is acceptable when the story resolves the protagonist's emotional question. An incomplete serial fragment is rejected unless the whole required cycle is available and licensed.

## Current Implementation Boundary

The current code does not yet implement this product. `scraper.py` discovers Reddit candidates, `story_adapter.py` cleans a selected source without inventing, and `translator_tts.py` translates that text while preserving its sequence. `storyboard_generator.py` and `render.py` then present the translated story through the Reddit-card visual system. This remains a localized reading workflow even when the output is horizontal.

Before an `acc1` production pilot, implementation therefore needs:

1. a rights manifest and pre-spend gate;
2. truth-mode classification (`fiction`, `unverified_account`, or `verified_case`);
3. complete-story producer review rather than a short prefix;
4. a dedicated Russian episode-script artifact and change ledger;
5. a manual shortlist and script-approval checkpoint;
6. metadata generation from the approved Russian script;
7. scene-based storyboard and editorial QA gates.

Until those exist, `acc1` stays automation-disabled and source reviews prove availability only, not production readiness.

The isolated implementation plan lives in [`../specs/acc1-automated-reddit-pilot/README.md`](../specs/acc1-automated-reddit-pilot/README.md). A local deterministic contract or selector does not mean that a paid pilot has run.
