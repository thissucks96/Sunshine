# SunnyNotSummer Roadmap

## Phase 1 (Current Stabilization)
- Keep solve output deterministic and concise.
- Preserve clipboard result integrity.
- Harden REF assignment and summary generation fallbacks.
- Maintain model selection reliability and probe validation.

## Phase 2 (Near-Term)
- Add optional auto model routing (`AUTO`) for graph/vision-heavy tasks.
- Keep routing behind a config flag and preserve current default behavior.
- Add focused regression tests for:
  - no-ref solve
  - REF IMG solve
  - REF TEXT solve
  - graph domain/range edge cases

## Phase 3 (Later)
- Expand routing policy with confidence-based escalation.
- Add clearer runtime diagnostics for routing decisions.
- Improve performance only where low-risk and measurable.

## Non-Goals (Unless Explicitly Requested)
- Architecture rewrites.
- Dependency churn.
- Broad UI redesign.

## Last Updated
- 2026-02-15
