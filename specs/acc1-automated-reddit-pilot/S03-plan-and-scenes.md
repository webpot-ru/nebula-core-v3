# S03: Translation and story editing

## Goal

Translate and lightly edit every complete source into natural Russian without changing its events, order, characters, or ending.

## Deliverables

- One bounded call translates one story; one independent review checks it against the complete source.
- Allowed changes are narration cleanup, removal of Reddit housekeeping and limited repetition compression, all recorded in a change ledger.
- Source images are recorded in a media manifest. Only verified local assets may enter render; links remain visible in source metadata and are never spelled aloud.
- Every call requires `--confirm-spend`; `--dry-run` performs input/preflight validation only.
- Checkpoints record input/config/prompt hashes and never overwrite a mismatched prior result.

## Done when

- Interrupted generation resumes only missing stories.
- A story without ending-preservation evidence or with an unsupported event fails before assembly.
