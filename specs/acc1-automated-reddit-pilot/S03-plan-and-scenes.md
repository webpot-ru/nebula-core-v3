# S03: Plan and scene writing

## Goal

Generate a Russian episode plan and scenes from the complete source with bounded, resumable paid calls.

## Deliverables

- Planner produces 7-10 source-anchored scenes and a 30-50 minute word budget.
- Scene writer writes one scene per call with continuity input, visual/sound beats, and a change ledger.
- Every call requires `--confirm-spend`; `--dry-run` performs input/preflight validation only.
- Checkpoints record input/config/prompt hashes and never overwrite a mismatched prior result.

## Done when

- Interrupted generation resumes only missing scenes.
- A scene without exact or normalized source anchors fails before assembly.
