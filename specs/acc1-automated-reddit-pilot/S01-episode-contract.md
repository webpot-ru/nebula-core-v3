# S01: Episode contract

## Goal

Create one canonical compilation contract shared by selector, translator/editor, reviewer, audio, storyboard, and QA.

## Deliverables

- `episode_contract.py` validates 3-6 distinct source snapshots, assembled story scripts, review decisions, 45-60 minute target, disclosure, ending evidence, unsupported-claim flags, and revision count.
- JSON fixtures and unit tests cover valid and fail-closed cases.
- Validation output is machine-readable and never calls a provider.

## Done when

- A valid 45-60 minute three-story fixture passes.
- Missing stories, duplicate post IDs, raw spoken URLs, missing fiction/unverified disclosure, unsupported factual additions, and a third revision fail.
