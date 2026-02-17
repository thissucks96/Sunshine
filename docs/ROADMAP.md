# Project State & Execution Context

# SunnyNotSummer Roadmap

## Current Stable Anchor
- Branch: `feature/forced-visual-extraction`
- Stable Tag: `exam-ready-v1`
- Latest Commit: `4b113ac`
- Feature Flags Default: All new diagnostic flags OFF

## Session Start Protocol
- Always run `git status`.
- Never modify unrelated files.
- Show `git diff` before commit.
- No push without explicit approval.

## Rollback Anchors Reference
- `exam-ready-v1` (`edc730f`)
- `pre-validator-stable` (`31ece74`)
- `master-bedrock` (`77bc30b`)
- `first-graph-success` (`552a7ad`)

## Stabilization Status
- Current branch: `feature/forced-visual-extraction`
- Working tree: clean
- Unified graph mode runtime: implemented
- Graph-mode targeted suite: passing
- Feature flags default: OFF
- Core output contract remains unchanged

## Branching Strategy
- Active stabilization branch: `feature/forced-visual-extraction`
- This branch supersedes `implement-auto-model-feature`
- Unified graph mode must remain fully stable before new feature work
- Auto-model will be implemented in a NEW branch created from this stabilized baseline
- No auto-model development should occur on this branch
- New branch creation requires explicit approval

---

## Approved Rollback Anchors

### exam-ready-v1
- Identifier: Tag `exam-ready-v1` (Commit `edc730f`)
- Commit message: `feat: add graph evidence extraction and warning-only interval validator (flags default off)`
- Description: Stable diagnostic baseline with graph evidence extraction and warning-only interval validator (flags default off, tests passing)

### pre-validator-stable
- Identifier: Commit `31ece74`
- Commit message: `docs: add vision accuracy audit and align docs [scope: README/docs]`
- Description: Pre-validator pipeline peak — hardened auto-model logic, retry and clipboard stability

### master-bedrock
- Identifier: Commit `77bc30b`
- Commit message: `stable version before auto model feature`
- Description: Master bedrock before auto model feature — clean rollback to foundational app state

### first-graph-success
- Identifier: Commit `552a7ad`
- Commit message: `personal ui updates and the app can now solve that graph from hw`
- Description: First real-world graph solve success milestone

## Phase 1 (Current Stabilization)
- Keep solve output deterministic and concise.
- Preserve clipboard result integrity (full output + final answer flow).
- Harden REF assignment and summary generation fallbacks.
- Keep model selection reliability with pre-activation probe validation.
- Keep notification-to-clipboard mirroring deterministic for user-visible events.
- Prioritize graph/vision correctness per `docs/VISION_ACCURACY_AUDIT_2026_02.md`.

## Phase 2 (Near-Term)
- Keep unified REF graph mode (`graph_mode` ON/OFF) stable in production.
- Improve graph evidence extraction quality and confidence handling without changing solve output contract.
- Introduce auto graph-identification incrementally, starting with REF-prime-only detection using a dedicated `graph_identifier_model` selector.
- Keep graph toggle in place until classifier behavior is validated and telemetry confirms stable precision/recall.
- Keep `WORK:` / `FINAL ANSWER:` contract, normalization, retry policy (graph retry disabled), and clipboard flow unchanged.
- Add optional auto model routing (`AUTO`) behind a disabled-by-default config flag.
- Introduce a metadata lock for `STARRED_META.json` read/modify/write paths.
- Add a critical telemetry allowlist that logs key failures even when `debug=false`.
- Add fallback behavior when tray notification backend fails.
- Add WORK-vs-FINAL interval consistency validation.
- Expand graph retry triggers beyond current phrase matching.
- Add dual OCR path and reconciliation for sign/symbol-sensitive math text.

## Phase 3 (Later)
- Expand routing policy with confidence-based escalation.
- Add targeted regression sets for graph domain/range edge cases.
- Add config recovery backup on malformed `config.json` reset.
- Add fixture-based vision regression suite for endpoint markers, asymptotes, discontinuities, and tick-scale edge cases.

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
- Vision-specific accuracy audit report: `docs/VISION_ACCURACY_AUDIT_2026_02.md`.

## Last Updated
- 2026-02-17
