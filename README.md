# SunnyNotSummer

SunnyNotSummer is a Windows tray assistant that reads clipboard text/images, solves math with OpenAI Responses API, and writes deterministic results back to clipboard.

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

## Documentation
- Architecture walkthrough: `docs/ARCHITECTURE.md`
- Vision accuracy audit: `docs/VISION_ACCURACY_AUDIT_2026_02.md`
- Roadmap: `docs/ROADMAP.md`
- Audit snapshot: `docs/ARCHITECTURE_REVIEW_2026_02.md`

## Tests
- `python -m unittest tests.test_model5_and_clipboard`
- `python -m unittest tests.test_model_switch_cancel_order`
- `python -m unittest tests.test_config_model_migration`

## Last Updated
- 2026-02-16
