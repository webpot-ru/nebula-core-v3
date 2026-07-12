# S06: GitHub pilot workflow

## Goal

Run one or two sequential artifact-only pilots with durable checkpoints and no upload path.

## Deliverables

- Dedicated manual workflow with `permissions: contents: read`.
- Inputs: `pilot_count=1|2`, `time_filter=month|year`, voice profile, and explicit provider-spend confirmation.
- Checkpoint artifacts upload with `if: always()`; pilots run sequentially with distinct post IDs.
- Static tests assert no uploader, YouTube secrets, history write, or model other than required `eleven_v3`.

## Done when

- A no-spend fixture run succeeds.
- A live run cannot start paid stages without the explicit confirmation input.
