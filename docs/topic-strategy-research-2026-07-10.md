# Channel Topic and Growth Strategy - 2026-07-10

Status: strategy reset applied locally; all channels remain fail-closed for automated selection until their source and audience gates pass.

## Goal

The goal is not to fill seven channels or reach monetization with interchangeable uploads. The goal is to build distinct channel franchises capable of producing breakout videos, millions of views, and high engagement without becoming repetitive or misleading.

The operating chain is:

```text
distinct viewer promise
  -> repeatable owned content bet
  -> complete and appropriate source lane
  -> strong first screen and narrative payoff
  -> materially original editorial treatment
  -> engaged-view / retention / comment / share readback
  -> expand only proven winners
```

Raw Reddit upvotes, a successful scraper run, or an AI `PUBLISH` label are not audience proof.

## Decision

The previous configuration did not create seven distinct products. It reused global English Reddit presets across languages, allowed exact stories to appear on multiple channels, and mixed Reddit-native stories with factual formats that need independent evidence and richer visuals.

The reset establishes:

1. one viewer promise and owned content territory per channel;
2. two separate production lanes: `reddit_story_card` and `evidence_dossier`;
3. network-wide duplicate protection by default;
4. fail-closed automation while topic mixes are unvalidated or superseded;
5. a phased launch instead of fourteen generic uploads per day;
6. audience decisions based on engaged views and retention, not raw Shorts starts alone.

`channels.json` is now the local strategy source of truth through `viewer_promise`, `owned_content_bets`, `forbidden_bets`, `evidence_policy`, `render_contract`, `producer_brief`, `cadence_plan`, `strategy_status`, and `automation_enabled`.

The existing numeric `topic_mix` values are not approved publishing weights. Each is explicitly marked as either candidate-scouting-only or superseded pending a rebuild. Exact new weights are intentionally not invented from one source snapshot.

## Network Ownership

| Channel | Owned viewer promise | Owned bets | Required lane | Current readiness | Cadence after gate |
|---|---|---|---|---|---|
| `acc1` Russian | Dark first-person stories with one memorable rule, escalation, and reveal | modern horror fiction; claimed personal encounters; later verified strange cases | Full-story atmospheric long-form; source-backed Shorts only as trailers after the long episode | `LONG-FORM PILOT REQUIRED` | Six unlisted 12-30 minute pilots; Shorts only after the source episode exists |
| `acc2` English | The hidden story behind the internet's strangest moments | internet case files; spectacle curiosity; exceptional high-concept human cases | Evidence dossier | `EVIDENCE LANE REQUIRED` | 3 high-concept pilots/week after lane exists |
| `acc3` German | Clear, precise explanation of how digital systems, scams, privacy, and technology affect real life | digital-system consequences; scam/privacy mechanisms; counterintuitive science | Evidence dossier | `EVIDENCE LANE REQUIRED` | 3 evidence-backed pilots/week after lane exists |
| `acc4` LATAM Spanish | One intimate conflict, two sides, one turn that changes the case; the viewer gives the verdict | relationship betrayal; family/money/entitlement; revenge/public humiliation | Reddit story card | `REDDIT PILOT CANDIDATE` | 5 Shorts/week after committed-config source gate; long-form from top-quartile Shorts only |
| `acc5` Brazil Portuguese | The human side of football: loyalty, injustice, pressure, identity, and comebacks beyond the score | player human arcs; fan identity; comeback/injustice/loyalty | Evidence dossier, rights-safe | `EVIDENCE LANE REQUIRED` | 3 pilots/week after lane exists |
| `acc6` French | One web mystery with facts, theories, and the genuinely unresolved separated clearly | web-mystery timelines; strange documented cases; theory checks | Evidence dossier | `EVIDENCE LANE REQUIRED` | 3 pilots/week after lane exists |
| `acc7` Italian | One concrete everyday social absurdity, escalating pressure, and a comic reversal | food/etiquette conflict; dating/family awkwardness; neighbor/work reversal | Reddit story card | `REDDIT PILOT CANDIDATE` | 5 Shorts/week after a distinct-source gate; long-form from top-quartile Shorts only |

### Hard ownership boundaries

- `acc4` owns serious emotional moral court: betrayal, family loyalty, money boundaries, parenting, entitlement, and two arguable sides.
- `acc7` owns performable social absurdity: a concrete scene involving food, etiquette, dates, neighbors, service, or work, ending in a reversal. Generic AITA is not enough.
- `acc1` owns dark story tension. `r/nosleep` must be labeled fiction; claimed encounters remain unverified personal accounts.
- `acc2` does not publish generic English Reddit readings. Heavy English competition requires a high-concept evidence-first case file.
- `acc3` owns mechanism and consequence, not vague mystery or celebrity gossip.
- `acc5` owns human football culture, not live scores, match clips, or transfer rumors.
- `acc6` owns skeptical mystery dossiers, not horror fiction presented as reporting.

## Production Lanes

### `reddit_story_card`

Allowed:

- complete first-person moral conflict;
- complete social-absurdity story with a visible scene and payoff;
- clearly labeled scary fiction;
- explicitly framed unverified personal encounter.

Required shape:

```text
0-2s   first-screen accusation, rule, or anomaly
2-12s  minimum setup
12-45s escalation and competing perspective
45-65s reversal or payoff
end    natural verdict question or retellable takeaway
```

The narrator must add material editorial value: selection, restructuring, context, and an original producer take. A translated reading of somebody else's post over a repeated card template is not the end product.

### `evidence_dossier`

Required for:

- facts, science, technology, scams, privacy, and explainers;
- real-world mysteries, crime claims, and public-person allegations;
- internet/creator/community timelines;
- football history, player arcs, and fan-culture claims.

Minimum contract:

- at least two independent supporting sources when the claim permits it;
- a primary source where available;
- explicit separation of fact, attributed claim, theory, and unknown;
- an original evidence-backed script;
- timeline/evidence visual treatment rather than one Reddit question card;
- no match footage or other rights-dependent media unless rights are established.

Reddit may identify a lead. Reddit alone does not establish a factual claim.

## Live Reddit Candidate Review

### Scope and safety

Twelve source-only GitHub runs were dispatched for `acc1`, `acc3`, `acc4`, `acc5`, `acc6`, and `acc7`, two slots per channel. They used:

- `AI_QUALITY_CHECK=0`;
- `AI_QUALITY_FAIL_OPEN=0`;
- one subreddit and one time window per family;
- ten posts maximum per bounded source;
- `comment_limit=0`;
- `--no-save-history`;
- no Gemini, AI33, image generation, render, YouTube, or git write.

Artifacts are under `/tmp/reddit-topic-review-20260710/<run-id>/` and are intentionally ephemeral.

Run IDs:

| Channel | Slot 1 | Slot 2 |
|---|---:|---:|
| `acc1` | `29073999465` | `29074002476` |
| `acc3` | `29074005955` | `29074009752` |
| `acc4` | `29074012412` | `29074015110` |
| `acc5` | `29074018685` | `29074022343` |
| `acc6` | `29074026277` | `29074029475` |
| `acc7` | `29074033035` | `29074038795` |

### Critical limitation

These runs checked commit `010fb95`, while the revised `channels.json` existed only as an uncommitted local diff. The logs therefore used the old checked-in labels, families, and weights. Slot 2 was also only `skip_rank=1` against the same snapshot, not a second independent time sample.

Consequently, the runs prove live Reddit access and expose source behavior, but they do not validate the exact revised mixes.

### Channel verdicts

| Channel | Verdict | Evidence |
|---|---|---|
| `acc1` | `BLOCKED` for current-mix validation; old lane `CHANGE` | 4/4 candidates were generic `r/AmItheAsshole` human drama. Selected 1897/802-character stories were self-contained and card-compatible, but no dark/fact promise appeared. |
| `acc2` | `BLOCKED` / not reviewed | It was deliberately outside the original bounded scope and still needs an English competitor/source review. |
| `acc3` | `BLOCKED` | 4/4 candidates were `r/OutOfTheLoop` questions. Selected bodies were 579/595 characters, contained external links, and did not contain the answer. |
| `acc4` | `CHANGE` | Its 8-candidate pool was the exact union of the generic AITA and OutOfTheLoop pools; selected stories duplicated `acc1` and `acc3`, with no LATAM-specific source ownership. |
| `acc5` | `CHANGE` | 4/4 candidates were the same AITA pool used by other channels. TIL produced no candidate and the one visible football source was too long for Shorts. |
| `acc6` | `BLOCKED` | The same source-incomplete OutOfTheLoop question pool as `acc3`; factual, political, and reputational risks cannot be resolved from those bodies. |
| `acc7` | `CHANGE` | The exact same AITA pool and selections as `acc5`; no Italian social-scene ownership. Its current local mix was not tested. |

There is no `PASS` for a current `topic_mix` in this review.

### Network overlap

Across the twelve queues:

- only 8 unique candidates existed: 4 AITA and 4 OutOfTheLoop;
- only 4 unique stories were selected;
- one AITA post was selected for `acc1`, `acc4`, `acc5`, and `acc7`;
- one OutOfTheLoop post was selected for `acc3`, `acc4`, and `acc6`;
- every AI field was null and every `PUBLISH` verdict meant only `AI quality check disabled`.

Historical evidence also showed 19 Reddit post IDs assigned 26 times across channels, with four exact posts reused across multiple channels. Network-wide duplicate protection is now the default in `scraper.py`; an explicit override is required to return to channel-only behavior.

### Family readiness from this snapshot

| Family | Snapshot result | Current renderer decision |
|---|---|---|
| `human_drama` | Four complete AITA selftexts; selected bodies had no link/screenshot dependency | Eligible only for the channel that owns the specific editorial treatment; personal claims remain unverified |
| `dark_curiosity` | No candidate from the first `nosleep/week` source; earlier project artifacts show the lane can return stories | Pilot only; fiction/claim disclosure is mandatory |
| `curiosity_facts` | No complete TIL selftext candidate | Blocked until evidence dossier lane |
| `football_culture` | No eligible short candidate; one visible body exceeded 2400 characters | Blocked until evidence dossier and rights-safe visual lane |
| `internet_lore` | Four OutOfTheLoop questions; selected posts depended on links and omitted answers | Blocked in current form |
| `visual_comedy` | No candidate from the first `tifu/day` source | Static card cannot perform a sketch; only complete narrated social absurdity may be piloted |

## Committed-Config Reddit Candidate Review - 2026-07-11

### Scope

The revised strategy and source-review evidence contract were committed and pushed to branch `codex/reddit-topic-source-review-20260711` at `ca6b0ad`. Twelve source-only runs then reviewed `acc1`, `acc3`, `acc4`, `acc5`, `acc6`, and `acc7` against separate `week` and `month` windows with:

- `channel_mix` from the committed `channels.json`;
- config SHA-256 `588466d4e6250328660a17f19fa8cb84462f82ccbca7934125d10b39184f56e1`;
- one subreddit per family and ten posts maximum per bounded source;
- complete bounded candidate selftexts preserved in the private artifact queue;
- `AI_QUALITY_CHECK=0`, `AI_QUALITY_FAIL_OPEN=0`, `comment_limit=0`, and `--no-save-history`;
- no Gemini, AI33, image generation, rendering, YouTube, or publication path.

Artifacts are under `/tmp/reddit-topic-review-20260711/`.

| Channel | Week run | Month run |
|---|---:|---:|
| `acc1` | `29152780077` | `29152778467` |
| `acc3` | `29152778416` | `29152779701` |
| `acc4` | `29152778435` | `29152777746` |
| `acc5` | `29152778356` | `29152779867` |
| `acc6` | `29152778361` | `29152779031` |
| `acc7` | `29152778457` | `29152780145` |

### Aggregate result

- all 12 GitHub runs passed credential preflight, tests, bounded PRAW fetch, artifact upload, and result enforcement;
- 63 queue entries collapsed to 19 unique Reddit posts;
- only two posts were selected across all runs;
- AITA post `1uqvgnb` was selected in eight runs across `acc1`, `acc4`, `acc5`, and `acc7`;
- OutOfTheLoop post `1uo7fu4` was selected in all four `acc3`/`acc6` runs;
- 28 of 63 entries had URL/link/image dependency, all concentrated in `internet_lore`;
- the candidate families represented were `human_drama` (20 entries), `internet_lore` (28), `visual_comedy` (13), and `football_culture` (2); `dark_curiosity` and `curiosity_facts` returned no eligible candidate from the bounded first sources.

Every `PUBLISH` label in these artifacts means only `AI quality check disabled`; it is not an editorial or factual approval.

### Current-mix verdicts

| Channel | Verdict | Evidence and next decision |
|---|---|---|
| `acc1` | `CHANGE` | Both windows returned only generic AITA (`2` week, `3` month); no dark story candidate appeared. The selected story was complete and card-compatible but violated the dark first-person promise. Do not invent a replacement weight until a forced `dark_curiosity` pool is reviewed. |
| `acc3` | `BLOCKED` | Both windows returned only link-dependent OutOfTheLoop questions (`3` week, `4` month). The selected 579-character body contained questions and a link, not the answer. Topic weights cannot repair the missing evidence-dossier lane. |
| `acc4` | `CHANGE` | Pools were diverse in family count (`10` week, `15` month), but mixed moral stories with factual OutOfTheLoop questions and broad TIFU comedy. The selected 1,953-character AITA story was self-contained, debatable, and card-compatible, but also won three other channels. A forced `human_drama` review is required before setting exact weights. |
| `acc5` | `CHANGE` | Each window returned the same generic AITA winner plus only one 387-character football quote. The quote is an attributed Reddit claim without independent support. Keep the channel evidence-lane blocked; do not treat a football-only weight as proof of viable Reddit supply. |
| `acc6` | `BLOCKED` | Its pools were identical to `acc3`: link-dependent OutOfTheLoop questions with factual, political, and reputational claims but no verified answer. Keep the evidence-dossier requirement. |
| `acc7` | `CHANGE` | The configured mix returned generic AITA plus link-dependent OutOfTheLoop (`5` week, `7` month), while the channel promise requires a concrete social-comedy scene. A separate shared-family signal exists: `visual_comedy` produced 13 complete selftexts in the `acc4` scans, but this is not enough to assign an Italian-channel weight without a forced `visual_comedy` review. |

There is no `PASS` and no evidence-backed exact replacement weight in this review. The correct next use of Reddit quota is limited forced-family validation for the three Reddit-native lanes, not more channel-mix repetitions.

### Fail-closed source-family correction

The confirmed failure mode was cross-channel substitution: when the owned family had no eligible candidate, a high-metric generic AITA or link-dependent OutOfTheLoop question won instead. The local config therefore replaces the contaminated multi-family scouting mixes with single-family validation gates for the channels where ownership is unambiguous:

| Channel | Validation family | Meaning of `1.0` |
|---|---|---|
| `acc1` | `dark_curiosity` | Search only the promised dark-story lane; return no candidate instead of generic AITA |
| `acc4` | `human_drama` | Search only moral-conflict stories; exclude factual internet questions and broad comedy |
| `acc5` | `football_culture` | Search only football leads; remain evidence-dossier blocked and return no generic drama |
| `acc7` | `visual_comedy` | Search only concrete social-comedy/awkward-scene stories; exclude generic AITA and OutOfTheLoop |

These `1.0` values are routing gates, not measured audience weights and not publishing approval. `acc3` and `acc6` remain evidence-lane blocked; changing their Reddit weights cannot supply the missing verified answer, original dossier, or evidence visuals.

### GitHub validation of the source-family gates

The corrected gates were pushed at commit `0b21d75` and checked with two bounded windows per channel, two subreddits maximum per owned family, ten posts maximum per source, `AI_QUALITY_CHECK=0`, no history write, and no Gemini/AI33/render/YouTube path.

| Channel | Week run | Month run | Result |
|---|---:|---:|---|
| `acc1` | `29153295786` | `29153296108` | `BLOCKED`, correctly fail-closed: no eligible short dark story; month `nosleep` candidates were 3,960-24,285 characters and exceeded the complete-Shorts source limit |
| `acc4` | `29153294775` | `29153294178` | `CHANGE`: 10/7 complete selftexts, only `human_drama`, no link dependence; supply passes the numeric floor but manual promise-fit is uneven and the same funeral story ranked first in both windows |
| `acc5` | `29153294958` | `29153295297` | `BLOCKED`: 6/7 football-only candidates, but they were mostly opinion/news/attributed claims; three week candidates were dependency-flagged and no independent evidence was collected |
| `acc7` | `29153294914` | `29153294476` | `CHANGE`: 5 week and 12 month complete selftexts, only `visual_comedy`, no link dependence; month supply passes while week remains below the six-candidate gate |

The correction is successful as a safety/routing change: no AITA was substituted into `acc1`, `acc5`, or `acc7`, and no OutOfTheLoop question appeared in these four channel pools. It does not yet prove audience performance or authorize publishing.

### Optional Russian long-source Shorts trailer path

The `acc1` blocker was source length rather than absence of dark material. Competitor/source analysis now makes the complete long story the primary product. The isolated `shorts_from_long` contract remains available only for a later trailer or standalone source-backed scene after the long episode exists. It must:

- produce at most 2,200 characters;
- preserve the actual setup/rule, escalation, and source ending;
- return one exact source quote for each of those three beats;
- introduce no new fact, dialogue, motive, relationship, place, number, or ending;
- fail when the story cannot survive compression honestly.

This exception applies only to `acc1` trailers. It does not re-enable arbitrary body trimming for other channels and is not the default Russian-channel format.

## Market Signals

These signals guide positioning; they do not prove that a proposed ChonkerTalks format will win.

- YouTube's 2025 Germany review places edutainment channel Simplicissimus among the leading creators and says well-produced reports, educational formats, and series remain important. This supports an evidence-backed German explainer promise, not dry Reddit trivia: [YouTube Germany 2025 review](https://blog.youtube/intl/de-de/creator-and-artist-stories/die-erfolgreichsten-videos-creatorinnen-und-trends-des-jahres-2025/).
- YouTube Brazil's 2025 review highlights scripted reality/family challenges and football topics including Campeonato Brasileiro and Lamine Yamal. The strategic inference is a human-stakes football franchise, not a score/news scraper: [YouTube Brazil 2025 review](https://blog.youtube/intl/pt-br/culture-and-trends/listas-fim-de-ano-2025/).
- YouTube's Hispanic-America review describes creator-led events whose engagement comes from direct fan participation and community involvement. The LATAM moral-court format uses that participation through verdict and debate rather than copying the event format itself: [YouTube Hispanic America 2025 review](https://blog.youtube/intl/es-419/culture-and-trends/listas-eoy/).
- Think with Google reports creator-driven franchises, active fan participation, and creator-led entertainment/community behavior across markets, including Mexico and France. This supports repeatable named series and local identity rather than anonymous translated posts: [Google/YouTube trends](https://business.google.com/en-all/think/search-and-video/2025-youtube-trends/).
- YouTube's next-generation research describes faster, layered audiovisual complexity, narrative co-creation, internet references, and global influence. The strategic inference is that the current static card can be a Reddit-story pilot surface, but evidence formats need richer original visuals: [YouTube Creative Maximalism](https://blog.youtube/culture-and-trends/next-gen-creativity/).
- YouTube's monetization policy explicitly treats mass-produced or repetitive template content, readings of material the creator did not make, and low-value slideshows as inauthentic. Material variation and original value are channel-level requirements: [YouTube channel monetization policies](https://support.google.com/youtube/answer/1311392?hl=en).

## 90-Day Execution Plan

### Days 0-14: prove sources, not views

1. Keep all seven channels automation-disabled.
2. Update the source-smoke workflow to record the checked-out git SHA and a `channels.json` digest.
3. Run forced-family samples against a committed strategy config at two genuinely separate times.
4. Save full source bodies for the bounded review pool, not only selected bodies.
5. Measure per channel:
   - unique complete candidates;
   - link/screenshot dependence;
   - evidence-required share;
   - cross-channel collision rate;
   - fictional-as-real risk;
   - card-render eligibility.
6. Build the first `evidence_dossier` fixture before enabling `acc2`, `acc3`, `acc5`, or `acc6`.

Source gate for a Reddit-native pilot:

- two independent snapshots;
- at least six unique complete candidates per snapshot after exclusions;
- no selected story reused by another channel;
- no link/screenshot-dependent payoff;
- every fiction/unverified account correctly classified;
- manual editorial acceptance of at least half the bounded pool.

### Days 15-45: controlled channel pilots

1. Start with `acc4` only after its distinct-source gate passes.
2. Publish or review five Shorts per week, not two random uploads per day.
3. Add `acc7` only after its food/etiquette/social-scene pool is demonstrably different from `acc4`.
4. Add `acc1` only after fiction/claim disclosure is visible in artifacts.
5. In parallel, build one evidence-dossier pilot each for `acc3`, `acc5`, and `acc6`.
6. Keep `acc2` as the final high-competition R&D lane.

### Days 46-90: double down on proven patterns

1. Review every Short at 24 hours and seven days.
2. Promote only recurring story signatures that win on engaged-view and retention metrics.
3. Expand a Short into long-form only when it is top quartile for its channel in at least three of the primary metrics below.
4. Kill a content bet after three consecutive bottom-half results unless a packaging defect clearly explains the miss.
5. Increase cadence only after candidate supply and audience metrics remain stable for two weeks.
6. Never translate a winner automatically into every language. Cross-language reuse is a deliberate campaign with a different editorial treatment and explicit override.

## Measurement Contract

Since 31 March 2025, a Shorts view counts when a Short starts or replays, without a minimum watch-time requirement. YouTube retains `Engaged views` for viewers who continued watching. Therefore raw starts are a reach signal, not the primary quality signal: [YouTube Shorts view-count change](https://support.google.com/youtube/answer/10059070).

Primary metrics:

1. `Engaged views`.
2. `Stayed to watch`.
3. `Average percentage viewed` and retention drop points.
4. Shares per 1,000 engaged views.
5. Comments per 1,000 engaged views.
6. Subscribers gained per 1,000 engaged views.
7. Returning/casual viewer growth over time.

YouTube defines `Stayed to watch`, `Engaged views`, average view duration, and average percentage viewed in content analytics; channel decisions should use those fields rather than invented algorithm rules: [YouTube content performance metrics](https://support.google.com/youtube/answer/12220281?hl=en).

Winner rule for the first 30 published pilots:

- compare only within the same channel and format;
- call a video a winner when it is top quartile in at least three primary metrics after seven days;
- diagnose first-screen failure separately from mid-story retention and payoff failure;
- do not change channel identity from one high raw-view outlier;
- use repeated winning story signatures to revise numeric topic weights.

## Automatic Rejections

- story/post/signature already used anywhere in the network;
- generic AITA outside `acc4`, except a scene/reversal case that clearly satisfies `acc7`;
- OutOfTheLoop question without an included, verified answer;
- link-, screenshot-, image-, comment-, or clip-dependent payoff;
- factual, celebrity, political, crime, scam, or football claim based only on Reddit;
- `r/nosleep` presented as real;
- score-only football, transfer rumor, live reaction, or match-footage dependency;
- visual comedy that requires a sketch while using only the static card;
- long source cut down to Shorts or thin source padded into long-form;
- generic translated story that could appear unchanged on another channel.

## Validation Commands and Artifacts

Current source artifact root:

```text
/tmp/reddit-topic-review-20260710/
```

Read a run after download:

```bash
jq '{channel_id, candidates_total, selected_post_id, entries}' \
  /tmp/reddit-topic-review-20260710/<run-id>/reddit-source-smoke-*/queue.json

jq '{topic_family, subreddit, post_id, source_body_chars, title, body}' \
  /tmp/reddit-topic-review-20260710/<run-id>/reddit-source-smoke-*/story.json
```

Local deterministic checks:

```bash
python3 -m unittest tests/test_scraper_reddit_config.py tests/test_channel_strategy.py
python3 -B -m py_compile scraper.py story_adapter.py metadata_generator.py
jq empty channels.json
```

After the strategy config and workflow changes are committed and pushed with explicit user approval, one bounded forced-family snapshot is dispatched with:

```bash
gh workflow run reddit_source_smoke.yml --repo webpot-ru/nebula-core-v3 --ref main \
  -f channel=acc4 -f video_slot=1 -f topic_family=human_drama \
  -f time_filter=auto -f candidate_limit=10 \
  -f max_subreddits_per_topic=2 -f max_time_windows_per_topic=1 \
  -f review_label=snapshot-a
```

The workflow records the git SHA, `channels.json` SHA-256, exact scope inputs, a config snapshot, and bounded queue source bodies. A later `snapshot-b` must be dispatched at a genuinely different time; a slot offset is not a repeatability sample.
