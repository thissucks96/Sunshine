# SunnyNotSummer Architecture

## Purpose
SunnyNotSummer is a Windows tray assistant that reads clipboard text/images, solves math with OpenAI Responses API, and writes results back to clipboard in a deterministic format.

## Core Modules
- `main.py`
  - Process lifecycle, tray menu, click policy, hotkeys, model selection/switching, startup/exit behaviors.
- `llm_pipeline.py`
  - Solve pipeline, STAR/REF assignment/clear, payload construction, output post-processing, final-answer extraction, clipboard dual-write behavior.
- `config.py`
  - Defaults, config normalization, atomic persistence, runtime cache, API key resolution.
- `utils.py`
  - Clipboard helpers, status notifications, telemetry, image normalization/OCR preprocessing, tray icon state.

## Runtime Flows
- Solve flow:
  - Read clipboard -> normalize input (image/text) -> call model -> clean/normalize output -> write full output + final-answer-only clipboard entries.
- REF flow:
  - Toggle STAR -> classify clipboard image as text/visual (with fallbacks) -> persist reference meta + summary -> inject reference context into solve calls when active.
- Model flow:
  - Tray selection and cycle hotkey use probe validation before persisting/announcing active model.
  - Startup and "Refresh Model List" announce active model from config without a probe call.
  - `AUTO` exists in the tray as a placeholder entry; dynamic routing is not active yet.

## State & Persistence
- Config: `config.json` managed by `config.py`.
- Reference metadata: `STARRED_META.json` with `reference_active`, `reference_type`, `text_path`, `image_path`, `reference_summary`.
- Reference assets: `STARRED.txt`, `REFERENCE_IMG/current_starred.png`.

## Output Contract
- Solver output targets deterministic plain-text blocks:
  - Problem text
  - `WORK:`
  - `FINAL ANSWER:`
- When REF is active, output is prefixed with:
  - `* REF IMG: <summary>` or `* REF TEXT: <summary>`

## Operational Constraints
- Reliability prioritized over speed.
- Keep formatting deterministic and concise.
- Avoid broad refactors without explicit approval.

## Last Updated
- 2026-02-15
