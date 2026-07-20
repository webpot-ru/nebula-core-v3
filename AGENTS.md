# AGENTS.md

Project-specific working rules for the ChonkerTalks / `nebula-core-v3` repository. Global Codex instructions and model routing still apply; this file adds only repository-specific source-of-truth, spend and publication boundaries.

## Read First

1. Read `docs/PROJECT_STATE.md` for the current verified state.
2. Read the relevant section of `docs/README.md` for architecture, commands and provider behavior.
3. Read `.agents/AGENTS.md` for the legacy GitHub orchestration constraint.
4. Treat `channels.json` as the current execution configuration for channel/account/language/topic mapping.

Do not infer current publication, OAuth, artifact or workflow state from chat memory when GitHub runs, local artifacts, `published_history.json`, `channels.json` or YouTube readback can be checked.

## Orchestration and Spend Boundaries

- Dispatch GitHub workflows from the local authenticated CLI with `gh workflow run ...`; do not build runner-to-runner dispatch around the lower-quota workflow `GITHUB_TOKEN`.
- Separate no-spend planning and deterministic checks from live Gemini, AI33, VectorEngine image, Reddit/provider and YouTube operations.
- Gemini/AI33/image generation, live GitHub dry-runs that call providers, YouTube upload/publish and retries require explicit approval of the exact scope because they can consume quota, credits or external state.
- A subagent or model choice never grants permission to spend, upload, publish, change OAuth/channel mapping or retry a failed external run.
- Keep `uploader.py` channel-token preflight and post-upload readback fail-closed.

## Safe Project Workflow

- Use `scripts/move-to-trash.sh` for approved removal of generated previews or scratch artifacts. Never delete them directly.
- Preserve the existing dirty worktree and keep edits narrowly scoped; do not revert or overwrite unrelated pipeline, workflow, channel or artifact changes.
- Use the existing deterministic storyboard, renderer and `pre_publish_qa.py` path before any upload claim.
- For UI/render changes, verify the actual browser or MP4 output, not only source code.
- Do not expose repository secrets, OAuth tokens, refresh tokens, provider keys, cookies or client data.

## Documentation

- Update `docs/PROJECT_STATE.md` when verified run, upload, artifact, channel or blocker state changes.
- Update `docs/README.md` when architecture, commands, providers, workflows or strategy rules change.
- Keep documentation explicit about local-only, GitHub-verified, artifact-verified and YouTube-verified states; do not compress them into one `done` state.
