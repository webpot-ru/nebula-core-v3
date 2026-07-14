# S07: Audience learning and breakout loop

## Goal

Turn the artifact pipeline into a measurable learning system capable of finding repeatable breakout formats rather than producing interchangeable uploads.

## Pre-publication experiment manifest

Every accepted script must produce `growth_experiment.json` with:

- one falsifiable `viewer_hypothesis`;
- `archetype_id`, setting, impossible rule, threat type, emotional cost, and payoff type;
- the exact cold-open promise and the scene that pays it off;
- scene IDs and planned time ranges;
- three materially different, honest title/thumbnail pairs;
- one story-specific participation question for the afterword;
- the expected failure mode: click, intro, middle, payoff, or satisfaction.

Candidate selection performs a cheaper version of this packaging test before script spend. Final packaging is regenerated from the accepted Russian script so an early angle cannot promise a scene or ending that the episode does not contain.

The three packaging options must differ in angle, not punctuation. YouTube's native A/B test can compare up to three title/thumbnail combinations and selects by watch-time share, so CTR alone must never choose the winner.

## Measurement checkpoints

Read back each published pilot at 24 hours, 72 hours, 7 days, and 28 days. Store immutable snapshots tied to video ID, script hash, packaging option, and render hash.

Automatable through YouTube Analytics API:

- views, estimated watch time, average view duration, and average view percentage;
- comments, shares, and subscribers gained;
- `audienceWatchRatio` and `relativeRetentionPerformance` over `elapsedVideoTimeRatio` for scene-level retention mapping.

Studio/manual readback remains explicit where the public API does not expose an equivalent field, especially impressions CTR, native A/B test verdict, first-30-second intro card, and new/casual/regular audience segments.

## KPI hierarchy

### Primary outcomes

1. **Watch-time yield per impression** — impressions CTR multiplied by average view duration for the same channel and format. It joins click appeal with actual watching and prevents clickbait CTR from looking like success.
2. **Retention quality** — first-30-second survival, average percentage viewed, payoff-scene retention, and retention relative to videos of similar length.
3. **Audience compounding** — returning/casual/regular viewer movement, with subscribers gained per 1,000 views as an earlier diagnostic while the channel is young.

### Engagement diagnostics

Track comments, shares, and subscribers gained per 1,000 views separately. Do not hide a weak share rate inside a blended engagement score. Label Reddit-only claims as fiction or unverified regardless of engagement upside.

## Decision rules

- The first six comparable long-form pilots establish the channel baseline; do not invent universal CTR or retention targets before it exists.
- At seven days, call a pilot a provisional winner only when it is top quartile in at least three primary/driver measures against the same channel and duration class.
- Promote an archetype to a franchise only after at least two wins across three distinct source stories. One viral outlier does not change allocation.
- `CLICK FAILURE`: packaging loses while retention is healthy — retest title/thumbnail, not the script.
- `INTRO FAILURE`: click is healthy but viewers leave in the first 30 seconds — rewrite cold open and promise delivery.
- `MIDDLE FAILURE`: repeated dip maps to a scene — repair causality, repetition, voice direction, or visual pacing in that scene type.
- `PAYOFF FAILURE`: viewers reach the climax but leave before completion or report dissatisfaction — reject that ending/payoff pattern.
- `SATISFACTION FAILURE`: watch metrics are acceptable but shares, comments, return behavior, or subscriber yield stay weak — do not franchise it.
- Increase cadence only after a repeatable winner and a clean quality/cost readback. Automation volume is never itself a success metric.

## Franchise memory

Persist one performance row per episode signature rather than only per Reddit post:

```text
setting + impossible_rule + threat_type + emotional_cost + payoff_type
```

The next candidate scorer may use this memory only after sufficient audience evidence. Source upvotes and Reddit comments remain discovery signals, not proof of YouTube demand.

## Official evidence

- YouTube native A/B testing compares up to three title/thumbnail options, selects the option with the highest watch-time share, and may need a few days to two weeks: https://support.google.com/youtube/answer/13861714?hl=en
- The audience-retention report identifies intro survival after 30 seconds, top moments, spikes, and dips, and compares videos of similar length: https://support.google.com/youtube/answer/9314415?hl=en
- YouTube describes consistent topics/formats and popular series as ways to grow casual and regular viewers: https://support.google.com/youtube/answer/10246996?hl=en
- YouTube says recommendations optimize for relevance and long-term viewer satisfaction using choices, watch behavior, likes/dislikes, and feedback rather than a simple upload-volume rule: https://support.google.com/youtube/answer/141805?hl=en
- YouTube Analytics API documents average view duration/percentage, comments, shares, subscribers gained, and audience-retention metrics: https://developers.google.com/youtube/analytics/metrics
