# S01: Episode contract

## Goal

Create one canonical deterministic contract shared by planner, scene writer, reviewer, audio, storyboard, and QA.

## Deliverables

- `episode_contract.py` validates source snapshots, plans, scenes, assembled scripts, review decisions, runtime range, disclosure, source anchors, unsupported-claim flags, and revision count.
- JSON fixtures and unit tests cover valid and fail-closed cases.
- Validation output is machine-readable and never calls a provider.

## Done when

- A valid 30-50 minute fixture passes.
- Missing scenes, duplicate IDs, empty narration, bad anchors, missing fiction/unverified disclosure, unsupported factual additions, and a third revision fail.
