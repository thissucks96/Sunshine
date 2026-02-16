# SunnyNotSummer Roadmap

## Phase 1 (Current Stabilization)
- Keep solve output deterministic and concise.
- Preserve clipboard result integrity (full output + final answer flow).
- Harden REF assignment and summary generation fallbacks.
- Keep model selection reliability with pre-activation probe validation.
- Keep notification-to-clipboard mirroring deterministic for user-visible events.

## Phase 2 (Near-Term)
- Add optional auto model routing (`AUTO`) behind a disabled-by-default config flag.
- Introduce a metadata lock for `STARRED_META.json` read/modify/write paths.
- Add a critical telemetry allowlist that logs key failures even when `debug=false`.
- Add fallback behavior when tray notification backend fails.

## Phase 3 (Later)
- Expand routing policy with confidence-based escalation.
- Add targeted regression sets for graph domain/range edge cases.
- Add config recovery backup on malformed `config.json` reset.

## Non-Goals (Unless Explicitly Requested)
- Architecture rewrites.
- Dependency churn.
- Broad UI redesign.

## Feature Intake & Decision Gate
- New requests should be classified before implementation:
  - Recommended
  - Risky but doable
  - Not recommended now
- Each proposal should include:
  - Risk/impact summary
  - Better alternative (if any)
  - Smallest safe implementation slice
- Prefer reversible, low-risk increments.

## Documentation Pointer
- Full senior-engineer walkthrough and module/function map: `docs/ARCHITECTURE.md`.

## Last Updated
- 2026-02-16
