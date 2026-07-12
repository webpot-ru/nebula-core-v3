# S05: Audio, storyboard, render and QA

## Goal

Turn only an accepted compilation into resumable Eleven v3 audio and a 16:9 artifact.

## Deliverables

- Metadata derives from the accepted Russian script and its actual payoff.
- AI33 submits intro/story/transition/outro chunks, saves task IDs immediately, polls saved tasks on resume, and validates requested/reported `eleven_v3`.
- Source URLs are omitted from speech; simple Russian integers, `%`, and `+` are normalized, while years/dates/times/decimals/currency fail preflight until an explicit spoken form exists.
- Reddit-hosted static images may be used only after bounded download, MIME/dimension/checksum validation, and conversion to a local render asset.
- QA checks editorial PASS, disclosure, manifests, story/audio coverage, 40-70 hard runtime with 45-60 target, 1920x1080 render, no placeholders, and audio/video alignment.

## Done when

- A fixture render passes without provider calls.
- A saved AI33 task/checksum cannot be submitted twice by retry.
