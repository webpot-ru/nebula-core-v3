# S05: Audio, storyboard, render and QA

## Goal

Turn only an accepted script into resumable Eleven v3 audio and a scene-based 16:9 artifact.

## Deliverables

- Metadata derives from the accepted Russian script and its actual payoff.
- AI33 submits per scene, saves task IDs immediately, polls saved tasks on resume, and validates requested/reported `eleven_v3`.
- Deterministic audio assembly and scene storyboard replace the Reddit-card contract for this lane.
- QA checks editorial PASS, disclosure, manifests, scene/audio coverage, 30-50 minute runtime, 1920x1080 render, no placeholders, and audio/video alignment.

## Done when

- A fixture render passes without provider calls.
- A saved AI33 task/checksum cannot be submitted twice by retry.
