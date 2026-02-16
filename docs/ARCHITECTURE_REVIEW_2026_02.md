# SunnyNotSummer Architecture Review - 2026_02

## Scope
Repository-level walkthrough refresh and runtime reliability audit aligned to current code in `main.py`, `llm_pipeline.py`, `utils.py`, and `config.py`.

## What Is Working
- End-to-end tray and hotkey solve workflows are stable.
- Model switching now cancels active solves before probing or activating new model.
- Exact `gpt-5` is normalized/migrated out of selectable config.
- REF assignment has classifier and OCR-based fallback paths.
- Status and popup notifications are centrally mirrored to structured clipboard payloads.
- Solve cancellation checks are present at key pre/post request and clipboard stages.

## Accuracy Notes
- `AUTO` model route in tray is still placeholder only (`main.py:616`).
- Telemetry remains fully gated by `debug` config (`utils.py:267`).
- `status_copy_to_clipboard` config key currently has no runtime effect.

## Key Risks Still Open
- Metadata file access for STAR state is not lock-protected across threads.
- Tray click behavior depends on pystray private internals.
- Config corruption recovery resets to defaults without backup.
- Regex-heavy output normalization can still over-correct edge-case math outputs.

## Recommended Next Steps
1. Add module-level lock around STAR metadata read/modify/write sequences.
2. Add always-on critical telemetry events for failures/cancellations independent of `debug`.
3. Add fallback notification path when tray notify backend fails.
4. Add targeted regression vectors for fragile output normalization cases.

## Notes
- This file remains an audit snapshot, not an operating contract.
- Full detailed walkthrough is in `docs/ARCHITECTURE.md`.

## Last Updated
- 2026-02-16
