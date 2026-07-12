# S06: GitHub pilot workflow

## Goal

Run one or two sequential artifact-only pilots with durable checkpoints and no upload path.

## Deliverables

- Dedicated manual workflow with `permissions: contents: read`.
- Inputs: `story_count=3..6`, `time_filter=month|year`, and explicit provider-spend confirmation.
- Checkpoint artifacts upload with `if: always()`; the first workflow is the `r/nosleep` artifact-only pilot.
- Static tests assert no uploader, YouTube secrets, history write, or model other than required `eleven_v3`.

Implemented locally as `.github/workflows/acc1_compilation_pilot.yml`. It remains unverified in GitHub until an explicitly approved provider-spend run is dispatched.

## Done when

- A no-spend fixture run succeeds.
- A live run cannot start paid stages without the explicit confirmation input.
