# Project State & Execution Context

# SunnyNotSummer Architecture Review - 2026_02

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
- Unified graph mode runtime: implemented and tested
- Graph-mode targeted suite: passing
- Feature flags default: OFF
- Core solve output contract remains unchanged

## Branching Strategy
- Active stabilization branch: `feature/forced-visual-extraction`
- This branch supersedes `implement-auto-model-feature`
- Unified graph mode must remain fully stable before new feature work
- Auto-model will be implemented in a NEW branch created from this stabilized baseline
- No auto-model development should occur on this branch
- New branch creation requires explicit approval

---

## Scope
Repository-level walkthrough refresh and runtime reliability audit aligned to current code in `main.py`, `llm_pipeline.py`, `utils.py`, and `config.py`.

## What Is Working
- End-to-end tray and hotkey solve workflows are stable.
- Model switching now cancels active solves before probing or activating new model.
- Exact `gpt-5` is normalized/migrated out of selectable config.
- REF assignment has classifier and OCR-based fallback paths.
- Unified graph mode now uses the same REF flow and caches graph evidence at REF-prime time.
- Status and popup notifications are centrally mirrored to structured clipboard payloads.
- Solve cancellation checks are present at key pre/post request and clipboard stages.

## Accuracy Notes
- `AUTO` model route in tray is still placeholder only (`main.py:616`).
- Telemetry remains fully gated by `debug` config (`utils.py:267`).
- `status_copy_to_clipboard` config key currently has no runtime effect.
- Vision/graph accuracy deep-dive documented in `docs/VISION_ACCURACY_AUDIT_2026_02.md`.

## Key Risks Still Open
- Metadata file access for STAR state is not lock-protected across threads.
- Tray click behavior depends on pystray private internals.
- Config corruption recovery resets to defaults without backup.
- Regex-heavy output normalization can still over-correct edge-case math outputs.
- Graph correctness currently relies on prompt compliance plus narrow text-triggered retry logic (`_needs_graph_domain_range_retry`).
- No fixture-based graph image regression suite currently protects endpoint/tick/asymptote correctness.

## Recommended Next Steps
1. Add module-level lock around STAR metadata read/modify/write sequences.
2. Add always-on critical telemetry events for failures/cancellations independent of `debug`.
3. Add fallback notification path when tray notify backend fails.
4. Add targeted regression vectors for fragile output normalization cases.
5. Implement top vision accuracy actions from `docs/VISION_ACCURACY_AUDIT_2026_02.md`:
   - graph evidence extraction pass
   - WORK-vs-FINAL interval consistency checks
   - expanded graph retry triggers
   - dual OCR reconciliation path

## Notes
- This file remains an audit snapshot, not an operating contract.
- Full detailed walkthrough is in `docs/ARCHITECTURE.md`.

## Last Updated
- 2026-02-17
