# S02: Source selection

## Goal

Select one full-body candidate from `topic-review.json` without touching publication history.

## Deliverables

- Deterministic selector writes `source_snapshot.json` and `pilot_manifest.json`.
- Manifest records post identity, source/body hashes, search inputs, truth mode, selection rationale, `rights_mode=test_only_not_cleared`, and `publication_authorized=false`.
- Only `month` and `year` windows are accepted for the first long-form pilots.
- A pre-spend packaging gate must find three materially different, source-backed viewer promises with a concrete visual symbol and an identifiable payoff. Generic variants of "страшная история с Reddit" do not count; a candidate that cannot support three honest angles is rejected before long-script generation.

## Done when

- The same queue/config produces the same selection.
- Two-pilot mode cannot choose the same post twice.
- Missing full body or incomplete/open-series sources fail before spend.
- Every proposed promise points to the source beat that can pay it off; packaging potential is advisory until the final Russian script exists.
