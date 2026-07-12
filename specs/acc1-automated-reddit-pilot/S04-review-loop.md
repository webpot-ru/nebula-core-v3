# S04: Review loop

## Goal

Independently review and selectively repair the Russian script without an infinite rewrite cycle.

## Deliverables

- Deterministic review runs first, followed by an independent Gemini review when spend is confirmed.
- Review categories include viewer promise, continuity, repetition, unsupported invention, fictional-as-real framing, Russian naturalness, payoff, and renderability.
- Only failed scenes are revised; unchanged scene hashes remain stable.
- Maximum two revision rounds; unresolved issues produce `BLOCKED_EDITORIAL`.

## Done when

- Tests prove PASS at zero/one/two revisions and hard stop after two.
