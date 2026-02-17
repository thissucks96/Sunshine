# Project State & Execution Context

# SunnyNotSummer

SunnyNotSummer is a Windows tray assistant that reads clipboard text/images, solves math with OpenAI Responses API, and writes deterministic results back to clipboard.

## How To Use The App
1. Launch the app with `python main.py`.
2. Copy a problem to clipboard (text or image/screenshot).
3. Press `ctrl+shift+x` to solve (or use tray `Solve Now`).
4. Read status updates from tray notifications.
5. Paste result where needed:
   - the app writes full solve output first
   - then writes parsed final answer to clipboard

Optional context flow:
1. Copy reference content (text/image) to clipboard.
2. Press `ctrl+shift+s` to prime REF.
3. For graph-heavy sessions, enable tray `GRAPH MODE ON/OFF` before priming an image REF.
4. Press `ctrl+shift+s` again to clear REF when done.

Core controls:
- Solve: `ctrl+shift+x`
- REF toggle: `ctrl+shift+s`
- Cycle model: `ctrl+shift+m`
- Quit: `ctrl+shift+q`

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
- Graph-mode targeted test suite: passing (`tests/test_graph_mode_behavior.py`)
- Feature flags default: OFF
- Output contract stability preserved (`WORK:` / `FINAL ANSWER:` unchanged)
- Current docs-tracked next step: harden graph extractor prompt and run formatting-compat checks before any output-template changes.
- Current staging intent: build synthetic graph generation + golden dataset pipeline for long-term regression testing.

## Branching Strategy
- Active stabilization branch: `feature/forced-visual-extraction`
- This branch supersedes `implement-auto-model-feature`
- Unified graph mode must remain stable before new feature work
- Auto-model will be implemented in a NEW branch created from this stabilized baseline
- No auto-model development should occur on this branch
- New branch creation requires explicit approval

---

## Core Runtime Files
- `main.py`: process lifecycle, tray menu, hotkeys, model switching, startup/shutdown.
- `llm_pipeline.py`: solve + STAR/REF pipelines, prompt payloads, output normalization, clipboard write flow.
- `utils.py`: tray icon state, status/notifications, clipboard helpers, telemetry writer.
- `config.py`: defaults, normalization/migration, atomic persistence, runtime config cache.

## Quick Run
1. Install dependencies from `requirements.txt`.
2. Set `OPENAI_API_KEY` or add `api_key` in `config.json`.
3. Launch `python main.py`.

## Runtime Controls
- Solve hotkey: `ctrl+shift+x`
- REF toggle hotkey: `ctrl+shift+s`
- Cycle model hotkey: `ctrl+shift+m`
- Quit hotkey: `ctrl+shift+q`
- Graph mode toggle: tray menu `GRAPH MODE ON/OFF`

## Documentation
- Architecture walkthrough: `docs/ARCHITECTURE.md`
- Vision accuracy audit: `docs/VISION_ACCURACY_AUDIT_2026_02.md`
- Roadmap: `docs/ROADMAP.md`
- Audit snapshot: `docs/ARCHITECTURE_REVIEW_2026_02.md`

## Tests
- `python -m unittest tests.test_model5_and_clipboard`
- `python -m unittest tests.test_model_switch_cancel_order`
- `python -m unittest tests.test_config_model_migration`

## User Screenshot Assumptions and Future Scaling
- Current operating assumption: this tool is used by a single disciplined user who provides clean, high-quality screenshots.
- Current token-optimization direction (for example dynamic image resizing) assumes that screenshot quality is usually sufficient for reliable graph interpretation.
- For future public release or multi-user deployment, stronger guardrails and fallback logic are required to handle inconsistent screenshot quality and varied user behavior.
- Production planning should not rely on user discipline; implement adaptive resizing with validator-backed fallback before broad rollout.
- Auto-model work should remain sequenced after graph-accuracy stabilization on the current branch baseline.

## Last Updated
- 2026-02-17
