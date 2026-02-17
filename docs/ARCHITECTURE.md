# Project State & Execution Context

# SunnyNotSummer Codebase Walkthrough

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
- Core output contract remains unchanged

## Branching Strategy
- Active stabilization branch: `feature/forced-visual-extraction`
- This branch supersedes `implement-auto-model-feature`
- Unified graph mode must remain fully stable before new feature work
- Auto-model will be implemented in a NEW branch created from this stabilized baseline
- No auto-model development should occur on this branch
- New branch creation requires explicit approval

---

Direction Update (Implemented):
- Graph support now uses a unified REF pipeline with a `graph_mode` toggle (`GRAPH MODE ON/OFF` in tray), replacing the prior dedicated graph-reference wiring.
- When graph mode is enabled, REF priming with an image performs graph-evidence extraction immediately and caches evidence metadata for reuse.
- Solve requests reuse cached graph evidence as secondary context when valid, while preserving output and clipboard contracts.

1 Executive Overview
SunnyNotSummer is a Windows tray-first clipboard solver that captures text or image input from the clipboard, optionally applies a STAR/REF reference context, sends a constrained prompt to the OpenAI Responses API, post-processes the model output into a deterministic math format, writes results back to clipboard (full result then final answer), and surfaces state through tray icon color, tray notifications, and telemetry. The core runtime is orchestrated in `main.py:733` (`main`), solve/reference logic lives in `llm_pipeline.py:846` (`solve_pipeline`) and `llm_pipeline.py:1074` (`toggle_star_worker`), configuration/state persistence is in `config.py`, and cross-cutting UI/clipboard/telemetry helpers are in `utils.py`.

2 High Level Architecture Diagram In Text
User hotkey or tray action
-> `main.py` hotkey/tray handlers (`setup_hotkeys` at `main.py:533`, menu actions at `main.py:585`)
-> worker dispatch (`worker` at `main.py:444` or `star_worker` at `main.py:491`)
-> clipboard capture (`safe_clipboard_read` at `utils.py:298`, `pyperclip.paste` call sites)
-> reference state read/validation (`load_starred_meta` at `llm_pipeline.py:186`)
-> payload build (`_build_solve_payload` at `llm_pipeline.py:444`)
-> OpenAI Responses call (`_responses_text` at `llm_pipeline.py:340`)
-> output normalization/extraction (`clean_output`, `_normalize_final_answer_block`, `_extract_final_answer_text`)
-> clipboard writes (`_clipboard_write_retry` at `llm_pipeline.py:592`)
-> user messaging (`set_status` at `utils.py:279`, `show_notification` at `utils.py:217`, tray icon updates)
-> telemetry file append (`log_telemetry` at `utils.py:267`, gated by `config.debug`)

3 Module Index
`main.py`: Entry point and runtime orchestration; single-instance guard, tray menu, hotkeys, solve/model-switch threading, startup/shutdown policy. Key entrypoint is `main.py:733`.
`llm_pipeline.py`: Solve and STAR pipelines; reference metadata management, request payload assembly, API call wrappers, post-processing, final clipboard output logic.
`utils.py`: Shared infrastructure; tray icon state machine, status dedupe, user notifications, structured notification clipboard mirroring, telemetry writer, clipboard/image helpers.
`config.py`: Configuration defaults, normalization/migration, atomic write/read, in-memory cache, API key resolution.
`config.json`: Live runtime config persisted by `config.py`; user-tunable model/timeouts/debug/notification settings.
`scripts/repro_model_switch.py`: Repro harness for model-switch call behavior and per-request telemetry-like output.
`tests/test_model5_and_clipboard.py`: Regression tests around GPT-5-family request shaping, cancel/write ordering, REF prefixing, and status clipboard mirroring.
`tests/test_model_switch_cancel_order.py`: Ensures active solve cancellation occurs before model probe during model change.
`tests/test_config_model_migration.py`: Ensures exact `gpt-5` is migrated/removed in normalized config.
`tests/verify_classifier.py`: Graph-presence classifier harness (supports sequential ground-truth validation mode with 429 backoff and no exclusion scoring).
`tests/GRAPH_CHECKER/`: Full graph/non-graph benchmark corpus for classifier validation.
`tests/GRAPH_CHECKER/graph_only/`: Positive-only benchmark subset (38 graph images).
`docs/`: Architecture, roadmap, and audit snapshots.
`REFERENCE_IMG/`, `STARRED.txt`, `STARRED_META.json`: Reference assets and metadata used by STAR/REF mode.

Classifier validation checkpoint:
- Sequential run on full `tests/GRAPH_CHECKER/` corpus recorded 103/103 correct (100.00%), artifact: `tests/GRAPH_CHECKER/classifier_results_20260216_185458.log`.

Graph runtime contract checkpoint:
- Graph identifier and graph evidence extraction are both pinned to `gpt-5.2`.
- Identifier returns JSON `YES/NO` + reasoning and is used only in REF-prime auto-detect flow.
- Graph mode ON bypasses identifier and runs extraction directly at REF prime.
- Extractor requires strict `GRAPH_EVIDENCE` schema; malformed outputs are treated as invalid and safely fall back.

4 Runtime Flow Walkthrough
Initialization
1. Process starts at `main.py:733` (`main`).
2. `ensure_single_instance` (`main.py:77`) creates a global Windows mutex and exits if already running.
3. Missing API key path uses `show_message_box_notification` (`utils.py:249`) to show popup and mirror structured error to clipboard.

Config loading
1. `get_config` (`config.py:223`) lazily loads cached config via `load_config` (`config.py:187`).
2. `load_config` ensures default keys exist, normalizes values via `_normalize_config` (`config.py:65`), and atomically rewrites if needed.
3. Model normalization migrates removed exact `gpt-5` values using `REMOVED_MODELS`/`REMOVED_MODEL_FALLBACK` (`config.py:9-10`).

Hotkey registration
1. `setup_hotkeys` (`main.py:533`) registers solve/quit/model-cycle hotkeys via `keyboard.add_hotkey`.
2. REF toggle uses combo-state tracking through keyboard hook (`_on_keyboard_event` at `main.py:411`) instead of direct hotkey callback.
3. Debounce is global-action based (`_debounced` at `main.py:86`) with `hotkey_debounce_ms`.

Tray setup
1. `pystray.Icon` is created in `main.py:747`.
2. `set_app_icon` (`utils.py:36`) loads idle icon and initializes tray state rendering.
3. `_build_tray_menu` (`main.py:640`) creates menu entries for Solve Now, REF ON/OFF, model selector, and refresh list.
4. `_install_tray_click_policy` (`main.py:687`) overrides Win32 notify behavior: middle click opens menu, left/right closes app.

Clipboard detection
1. Solve trigger starts `worker` (`main.py:444`) on a daemon thread.
2. `worker` enforces single solve with `_solve_lock` (`main.py:52`) and creates request-scoped cancel event.
3. Clipboard image is read via `safe_clipboard_read` (`utils.py:298`); text fallback uses `pyperclip.paste`.

Reference image handling
1. `solve_pipeline` (`llm_pipeline.py:846`) loads reference metadata via `load_starred_meta` (`llm_pipeline.py:186`).
2. If reference active, validates existence/readability of text/image assets; invalid state is cleared via `_clear_reference` and persisted.
3. For image references, image is normalized and base64 encoded; for text references, file content is loaded and summarized for prompt context.

Request assembly
1. `_build_solve_payload` (`llm_pipeline.py:444`) composes `[system, user]` message list.
2. System prompt enforces output contract (`SYSTEM_PROMPT` at `llm_pipeline.py:37`).
3. STAR context (`STARRED_CONTEXT_GUIDE` at `llm_pipeline.py:100`) is appended as secondary context only when active.

Model call
1. `_responses_text` (`llm_pipeline.py:340`) builds request dict (`model`, `input`, `max_output_tokens`, `timeout`, optional `temperature`).
2. GPT-5-family check (`_is_gpt5_family_model` at `llm_pipeline.py:311`) omits temperature and enforces token floor.
3. API lifecycle telemetry logs start, completion, and errors with request IDs.
4. `solve_pipeline` applies retries (`retries` from config), with optional graph-domain/range targeted requery (`_needs_graph_domain_range_retry` at `llm_pipeline.py:641`).

Response parsing
1. Raw output is normalized by `clean_output` (`llm_pipeline.py:489`) and `apply_safe_symbols` (`utils.py:355`).
2. FINAL ANSWER canonicalization runs in `_normalize_final_answer_block` (`llm_pipeline.py:600`) and `_extract_final_answer_text` (`llm_pipeline.py:504`).
3. Domain/range/graph formatting guards run through `_maybe_enforce_points_to_plot`, `_maybe_enforce_domain_range_intervals`, `_maybe_compact_discrete_domain_range`.

Output formatting
1. If REF active, prefix `* REF IMG: ...` or `* REF TEXT: ...` is prepended before clipboard writes.
2. Two-phase clipboard write: full output first, then final answer only (`_clipboard_write_retry` at `llm_pipeline.py:592`) separated by `clipboard_history_settle_sec`.

Notification display
1. Status goes through `set_status` (`utils.py:279`) with dedupe window `_STATUS_DEDUPE_WINDOW_SEC` (`utils.py:20`).
2. `show_notification` (`utils.py:217`) sends tray notification and mirrors structured notification payload to clipboard only when shown.
3. Message boxes route through `show_message_box_notification` (`utils.py:249`) and mirror structured payload.

Telemetry logging
1. `log_telemetry` (`utils.py:267`) appends JSONL entries to `telemetry_file` only when `debug` is true.
2. All major lifecycle steps log events: model probe/change, solve start/retry/cancel/complete, ref toggles, tray/hotkey diagnostics, clipboard failures.

Shutdown flow
1. `on_quit` (`main.py:723`) clears reference state, sets `STOP_EVENT`, unregisters hotkeys, and stops tray icon.
2. Tray left/right click close path uses `_close_icon_only` (`main.py:677`), which exits without clearing REF metadata.

5 Key Abstractions and Data Structures
`DEFAULT_CONFIG` dict (`config.py:12`)
Created: module import in `config.py`.
Mutated: merged/normalized in `_normalize_config` (`config.py:65`) and persisted in `update_config_values` (`config.py:242`).
Consumed: everywhere via `get_config` (`config.py:223`), notably `main.py`, `llm_pipeline.py`, `utils.py`.
Common failure modes: malformed `config.json` resets to defaults in `load_config`; stale keys silently normalized.

Runtime config cache `_CONFIG_CACHE` (`config.py:51`)
Created: first `get_config` call.
Mutated: `reload_config` and `update_config_values`.
Consumed: all runtime reads.
Common failure modes: external manual edits are not seen until reload path is invoked.

Reference metadata dict (`_default_reference_meta` at `llm_pipeline.py:142`)
Fields: `reference_active`, `reference_type`, `text_path`, `image_path`, `reference_summary`.
Created: on first run or load fallback in `load_starred_meta`.
Mutated: `toggle_star_worker`, `_clear_reference`, invalid-reference guards inside `solve_pipeline`.
Consumed: solve payload construction and tray REF state checks.
Common failure modes: dangling paths after file deletion; normalized to inactive and user is notified.

Solve payload list (`_build_solve_payload` at `llm_pipeline.py:444`)
Created: each solve request.
Mutated: graph retry path appends extra hint via `_with_graph_domain_range_retry_hint`.
Consumed: `_responses_text` API call.
Common failure modes: oversized/ambiguous context can degrade model compliance; fallback normalization attempts to recover.

API request dict in `_responses_text` (`llm_pipeline.py:340`)
Created: per call attempt.
Mutated: unsupported-temperature error path removes `temperature` and retries.
Consumed: `client.responses.create`.
Common failure modes: timeout/network/API parameter errors; surfaced through telemetry and retry logic in caller.

Active solve runtime state globals (`main.py:55-59`)
Created: process start.
Mutated: `_register_active_solve`, `_cancel_active_solve`, `_clear_active_solve`.
Consumed: model-switch cancellation paths (`cycle_model_worker`, `_set_model_from_ui`).
Common failure modes: stale pointers if clear is skipped; mitigated by finally-block cleanup in `worker`.

Status dedupe state (`utils.py:17-20`)
Created: process start.
Mutated: `set_status` updates last message/timestamp.
Consumed: status suppression check in `set_status`.
Common failure modes: different messages bypass dedupe even if semantically equivalent; intentional behavior.

Structured notification clipboard payload (`utils.py:113`)
Created: `_build_notification_clipboard_payload` on notification emission.
Mutated: none after creation.
Consumed: `mirror_notification_to_clipboard` and downstream clipboard consumers/parsers.
Common failure modes: clipboard lock/write failures logged as `clipboard_write_error` or `notification_clipboard_mirror_failed`.

6 Critical Functions Deep Dive
`ensure_single_instance` (`main.py:77`)
Purpose: Prevent multiple running instances.
Inputs/outputs: no inputs; returns bool.
Side effects: creates global Windows mutex.
Threading assumptions: called on startup main thread.
Error paths: no explicit exception handling around Win32 calls.
Called from: `main` (`main.py:733`).
Invariants/contracts: false means process must exit immediately.

`setup_hotkeys` (`main.py:533`)
Purpose: Register all runtime hotkeys and REF combo hook.
Inputs/outputs: tray icon, announce flag; returns bool success.
Side effects: mutates `_HOTKEY_HANDLES`, keyboard hook globals, emits status/telemetry.
Threading assumptions: called on startup main thread.
Error paths: catches registration exceptions, unregisters partial binds.
Called from: `main`.
Invariants/contracts: run/quit/cycle hotkeys are fixed constants.

`_on_keyboard_event` (`main.py:411`)
Purpose: Maintain current key-down set and edge-detect REF combo activation.
Inputs/outputs: keyboard event; returns None.
Side effects: mutates `_keys_down`, `_prev_ref_combo_active`; logs diagnostics; may dispatch REF toggle.
Threading assumptions: invoked from keyboard hook thread.
Error paths: broad exception catch logs `ref_hotkey_event_error`.
Called from: keyboard hook installed in `setup_hotkeys`.
Invariants/contracts: only triggers toggle on rising edge (inactive->active).

`worker` (`main.py:444`)
Purpose: Primary solve dispatcher from clipboard to solve pipeline.
Inputs/outputs: no args; returns None.
Side effects: acquires `_solve_lock`, creates OpenAI client, reads clipboard, registers active solve state, updates status.
Threading assumptions: runs on daemon thread launched by `_debounced`.
Error paths: missing API key/no input/worker crash paths set status and telemetry.
Called from: solve hotkey/tray action.
Invariants/contracts: exactly one concurrent solve allowed.

`_register_active_solve` and `_cancel_active_solve` (`main.py:243`, `main.py:269`)
Purpose: Track/cancel in-flight solve on model switches.
Inputs/outputs: client, cancel event, metadata; cancel returns bool.
Side effects: shared global state mutation under `_active_solve_state_lock`; closes client on cancel.
Threading assumptions: called from worker thread and model-switch threads.
Error paths: close failures logged as `solve_cancel_close_error`.
Called from: `worker`, `cycle_model_worker`, `_set_model_from_ui`.
Invariants/contracts: cancel event set before client close attempt.

`cycle_model_worker` (`main.py:289`)
Purpose: Hotkey-driven model cycle with probe validation.
Inputs/outputs: tray icon; returns None.
Side effects: may cancel active solve, probe API, persist config, emit status, refresh tray.
Threading assumptions: runs on daemon thread via `_debounced`.
Error paths: probe/persist failures become status errors.
Called from: cycle hotkey callback.
Invariants/contracts: cancellation is attempted before probing a new model.

`_set_model_from_ui` (`main.py:330`)
Purpose: Tray-menu model selection path.
Inputs/outputs: icon, target model, source string.
Side effects: same as cycle path; also logs source-specific events.
Threading assumptions: called from tray callback thread context.
Error paths: rejects empty/unknown model, probe failures, persist failures.
Called from: `_on_tray_select_model`.
Invariants/contracts: target model must exist in normalized `available_models`.

`_probe_model_runtime` (`main.py:182`)
Purpose: Fast runtime probe to validate model reachability/identity before activation.
Inputs/outputs: model name, optional call model, require_match; returns `(ok, reason)`.
Side effects: network call, telemetry logging.
Threading assumptions: called from model-switch threads and UI actions.
Error paths: any API exception returns false with reason.
Called from: `cycle_model_worker`, `_set_model_from_ui`.
Invariants/contracts: strict-ish response model match via `_model_name_matches`.

`solve_pipeline` (`llm_pipeline.py:846`)
Purpose: End-to-end solve lifecycle (reference validation, request/retry, postprocess, clipboard output).
Inputs/outputs: OpenAI client, input object (text/image), optional cancel event/request ID; returns None.
Side effects: reads/writes reference metadata, writes clipboard, emits tray/status and telemetry.
Threading assumptions: runs in worker thread; cancellation is cooperative.
Error paths: per-attempt exception handling, empty response handling, invalid REF guards.
Called from: `main.worker`.
Invariants/contracts: output should preserve `WORK` + `FINAL ANSWER` contract; cancellation must short-circuit before final writes.

`_responses_text` (`llm_pipeline.py:340`)
Purpose: Thin API-call wrapper with telemetry and response text extraction.
Inputs/outputs: client/model/payload/timeout/temp/token budget/etc; returns text.
Side effects: API network call and telemetry entries.
Threading assumptions: invoked by solve and STAR paths.
Error paths: logs `api_request_error`, rethrows unless unsupported-temperature workaround applies.
Called from: `solve_pipeline`, `toggle_star_worker`, `_summarize_visual_reference`.
Invariants/contracts: returns concatenated message text when `output_text` is absent.

`_build_solve_payload` (`llm_pipeline.py:444`)
Purpose: Assemble model input message list based on text/image and optional reference context.
Inputs/outputs: input object + reference state; returns list of message dicts.
Side effects: none.
Threading assumptions: pure function used in solve thread.
Error paths: none directly.
Called from: `solve_pipeline`.
Invariants/contracts: current problem content always appears before optional reference content.

`toggle_star_worker` (`llm_pipeline.py:1074`)
Purpose: REF toggle implementation for assigning/clearing text or visual references.
Inputs/outputs: OpenAI client; returns None.
Side effects: clipboard reads, model classify/OCR/summarize calls, writes `STARRED.txt`/image/meta, status updates.
Threading assumptions: called in `main.star_worker` thread.
Error paths: classifier fallback, OCR fallback, and catch-all STAR failure status.
Called from: `main.star_worker`.
Invariants/contracts: active REF toggle first clears, not overwrite; assignment only when inactive.

`clear_reference_state` (`llm_pipeline.py:222`)
Purpose: Clear persisted reference state and reflect it in UI.
Inputs/outputs: source/status message; returns None.
Side effects: writes `STARRED_META.json`, toggles tray reference state, optional status.
Threading assumptions: called on startup/exit and error recovery paths.
Error paths: load/save failures logged as `ref_clear_error`.
Called from: `main.main`, `main.on_quit`, reference validation paths.
Invariants/contracts: resulting metadata must be inactive and empty.

`set_status` (`utils.py:279`)
Purpose: Centralized user status emission with dedupe and error-state signaling.
Inputs/outputs: message string; returns None.
Side effects: toggles error tray state, dedupe state mutation, telemetry event, tray notify + clipboard mirror.
Threading assumptions: called from multiple worker/UI threads; guarded by `_STATUS_LOCK`.
Error paths: notification/clipboard failures are non-fatal and logged.
Called from: most runtime flows.
Invariants/contracts: duplicate message inside dedupe window is suppressed (no user notification, no clipboard mirror).

`show_notification` (`utils.py:217`)
Purpose: Tray notification emission and automatic structured clipboard mirror when shown.
Inputs/outputs: message/title/level/source; returns bool shown.
Side effects: OS tray notification call, optional async clear thread, clipboard write.
Threading assumptions: thread-safe enough for concurrent calls; relies on pystray internals.
Error paths: exceptions swallowed to avoid UI crash.
Called from: `set_status`.
Invariants/contracts: clipboard mirror happens only if notification was actually shown.

`_normalize_config` (`config.py:65`)
Purpose: Enforce schema defaults, value bounds, and model migration rules.
Inputs/outputs: raw cfg dict -> normalized cfg dict.
Side effects: none directly; caller persists result.
Threading assumptions: called under config lock.
Error paths: coercion failures are converted to defaults.
Called from: save/load/update flows.
Invariants/contracts: output config always has valid model list, clamped notification values, and floor constraints for image/clipboard timing.

7 Concurrency and Threading Model
Main thread responsibilities
- Process bootstrap in `main`.
- Tray icon lifecycle `icon.run()` and menu callback dispatch.

Background thread responsibilities
- `_debounced` (`main.py:86`) launches solve and cycle-model workers as daemon threads.
- REF toggle dispatch launches `_launch_star_worker_atomic` thread (`main.py:408`).
- `mark_prompt_success` starts pulse-clear timer thread (`utils.py:206`).
- `show_notification` may start notification clear timer thread (`utils.py:217`).

Locks and coordination primitives
- `_solve_lock` (`main.py:52`): single active solve.
- `_star_lock` (`main.py:53`): single STAR toggle operation.
- `_model_lock` (`main.py:54`): serial model-switch operations.
- `_active_solve_state_lock` (`main.py:55`): protects active solve client/cancel metadata.
- `_debounce_lock` (`main.py:62`): per-action debounce timestamps.
- `_ref_dispatch_lock` (`main.py:73`): REF hotkey anti-spam state.
- `_STATUS_LOCK` (`utils.py:17`): status dedupe state.
- `_TRAY_STATE_LOCK` (`utils.py:22`): tray icon state transitions.
- `STOP_EVENT` (`main.py:51`): shutdown signal marker.

Potential race points
- Cancel while API call in progress: cancellation is cooperative; close+event may still wait for network timeout before returning from SDK call.
- Clipboard overwrite race: solve writes full output then final answer; other apps may interleave clipboard changes between writes.
- Tray click policy uses pystray private handlers; backend changes could alter threading/callback ordering.
- Status dedupe is message-string based, so semantically identical but text-different statuses can spam under load.

8 Error Handling and User Messaging
Error detection
- API/network and timeout errors are captured in `_responses_text` with `_exception_payload` (`llm_pipeline.py:330`).
- Missing API key and no clipboard input are explicitly handled in `main.worker`.
- REF invalid state paths in `solve_pipeline` clear metadata and surface reason.

Error categorization
- No formal enum class; categorization is string/event based (`solve_request_failed`, `solve_retry`, `status` text, timeout subtype fields).
- Timeout subtype is parsed textually by `_timeout_type_from_exception` (`llm_pipeline.py:315`).

User surfacing
- Central status surface is `set_status` (`utils.py:279`).
- Tray-level popup status via `show_notification` (`utils.py:217`).
- Blocking startup alerts via `show_message_box_notification` (`utils.py:249`).
- Tray icon color reflects error/reference/success state (`utils.py:139`, `utils.py:152`).

Status dedupe behavior
- Duplicate message suppression window is 0.3 seconds (`utils.py:20`).
- Suppressed duplicates log `status_suppressed` telemetry and do not trigger notification or clipboard mirror.

Notification emission path
- `set_status` -> `show_notification` -> `mirror_notification_to_clipboard` when shown.
- Message boxes call `show_message_box_notification` -> `mirror_notification_to_clipboard`.
- Clipboard mirror payload is structured and parseable (`utils.py:113`).

9 API Layer and Model Selection
API request formation
- API wrapper is `_responses_text` (`llm_pipeline.py:340`).
- Request fields: `model`, `input`, `max_output_tokens`, `timeout`, optional `temperature`.
- GPT-5-family (`startswith("gpt-5")`) omits temperature and enforces min token budget behavior.

Response parsing
- Primary read uses `resp.output_text`.
- Fallback iterates `resp.output` message/content items and concatenates text fragments.

Timeouts and retries
- Per-call timeout from config (`request_timeout`) with GPT-5-family floor adjustment in `solve_pipeline`.
- Solve-level retries are `retries + 1` attempts in `solve_pipeline`.
- Retries for unsupported temperature happen inside `_responses_text` by removing `temperature` and retrying same request.

Model choice and switching
- Active model source is config field `model` (`_active_model_name` at `main.py:144`).
- Available models come from config, normalized by `_normalize_available_models` (`main.py:125`) and `_normalize_config` (`config.py:65`).
- Model switch paths (`cycle_model_worker`, `_set_model_from_ui`) cancel in-flight solve before probe and persist.
- Probe path `_probe_model_runtime` does a lightweight real API call before model activation.

Where to hook dynamic routing
- Current `AUTO` item is placeholder (`_on_tray_auto_model_placeholder` at `main.py:616`).
- Lowest-risk hook: choose effective model inside `worker` before creating client and before calling `solve_pipeline`, while still leaving persisted config model unchanged.
- Secondary hook: pass selected model override into `solve_pipeline` rather than reading from config each call.

10 Observability
Current telemetry mechanism
- `log_telemetry` (`utils.py:267`) writes JSONL `{ts, event, data}` to `telemetry_file` when `debug=true`.
- No external logger dependency; failures are swallowed to avoid breaking runtime.

Event coverage (major groups)
- API lifecycle: `api_request_start`, `api_request_complete`, `api_request_error`.
- Solve lifecycle: `solve_request_start`, `solve_retry`, `solve_request_failed`, `solve_request_complete`, `solve_cancelled`, `solve_empty_response_retry`.
- Model management: `model_probe_ok`, `model_probe_failed`, `model_changed`, `model_selected_from_tray`, `startup_model`.
- Concurrency/cancel: `solve_active_registered`, `solve_cancel_requested`, `solve_active_cleared`, `solve_skip_busy`.
- REF lifecycle: `ref_set`, `ref_clear`, `ref_clear_error`, `ref_classifier_empty_fallback`, `summary_generation_error`.
- UX/hotkeys/tray: `status`, `status_suppressed`, `tray_icon_render`, `tray_click_policy_error`, `hotkey_register_error`, `ref_hotkey_diag`.
- Clipboard/notification failures: `clipboard_write_error`, `notification_clipboard_mirror_failed`, `message_box_error`.

Metadata captured
- Request IDs, model names, attempt counters, start/end timestamps, elapsed times, timeout type, exception payload, source tags.

How to add events safely
- Add a new `log_telemetry("event_name", {...})` near boundary transitions, not inside tight loops.
- Keep payloads bounded in size and redact clipboard/problem content unless required.
- Reuse existing `request_id`/`solve_id` fields for correlation.

11 Known Risks and High Impact Improvement List
1. `utils.py:267` telemetry is debug-gated, so production incidents can be silent when `debug=false`.
Minimal fix direction: add a small always-on critical-event allowlist (failures/cancellations only) while keeping verbose events debug-gated.

2. `config.py:41` includes `status_copy_to_clipboard`, but status clipboard behavior is now centralized in notifications and does not use this flag.
Minimal fix direction: either wire the flag into `set_status`/`show_notification` behavior or remove it from config normalization and defaults.

3. `main.py:149` clipboard verification for model announcement is best-effort and can race with other clipboard writers.
Minimal fix direction: downgrade verification to telemetry-only health signal and avoid treating mismatch as operational failure.

4. `main.py:182` model probe is synchronous and network-bound, which can make model switching feel stalled on poor connectivity.
Minimal fix direction: add explicit probe timeout status messaging and optional non-blocking fallback model reversion path.

5. `main.py:687` tray click policy depends on pystray private internals (`_on_notify`, `_message_handlers`).
Minimal fix direction: guard with backend version checks and fallback to default click behavior when patching fails.

6. `llm_pipeline.py:846` cancellation is cooperative; if SDK call blocks, cancel waits on network timeout.
Minimal fix direction: pass lower per-call timeouts for cancel-sensitive phases and keep close+event cancellation path as secondary signal.

7. `llm_pipeline.py:186` and `llm_pipeline.py:206` metadata file reads/writes are not locked across threads.
Minimal fix direction: add a module-level lock around starred meta read/modify/write sequences.

8. `utils.py:217` notification display failures are swallowed silently except indirect telemetry, so user may miss statuses if tray notifications stop working.
Minimal fix direction: add fallback direct clipboard mirror or fallback status sink when notify backend fails.

9. `config.py:187` malformed `config.json` resets to defaults, which can silently discard user customization.
Minimal fix direction: persist a timestamped backup of the bad config before reset for manual recovery.

10. `llm_pipeline.py:489`/post-processing heuristics are regex-heavy and may over-normalize edge-case math output.
Minimal fix direction: gate transformations with stricter preconditions and add test vectors for known fragile formats.

12 Glossary
Reference mode / REF: A toggleable context mode where prior text/image content is stored and optionally injected as secondary context into subsequent solve requests.
STAR: User action (hotkey/menu) that toggles REF state; if inactive it assigns a reference from clipboard, if active it clears.
Reference metadata: JSON object in `STARRED_META.json` with active flag, type (`TEXT` or `IMG`), file paths, and summary.
Dedupe window: Time window (`_STATUS_DEDUPE_WINDOW_SEC`, 0.3s) that suppresses repeated identical status messages.
Tray state: Internal icon state machine (`IDLE`, `REFERENCE_PRIMED`, `PROMPT_SUCCESS`, `ERROR`) rendered by tray icon color/icon.
Active solve state: Shared runtime record (`_active_solve_client`, cancel event, solve id/model) used to cancel in-flight requests when model changes.
Model probe: Lightweight API request executed before switching active model to verify reachability and model identity.
Graph-domain/range retry hint: Retained helper for targeted prompt guidance, but runtime solve loop path is intentionally disabled.
Two-phase clipboard write: Solve output strategy that writes full formatted output first, then writes final-answer-only payload after a short settle delay.
Structured notification payload: Clipboard block emitted for user-visible notifications with keys `NOTIFICATION_TYPE`, `TIMESTAMP`, `SOURCE`, `MESSAGE`.

Vision Accuracy Audit Reference
- Comprehensive graph and visual pipeline accuracy audit: `docs/VISION_ACCURACY_AUDIT_2026_02.md`.
- Primary focus: image ingress fidelity, OCR robustness, graph endpoint/tick/asymptote reliability, retry coverage, and accuracy regression test coverage.

## 13. Graph Evidence Validator

### 1) Why This Feature Is Required
- This feature protects against a specific graph-perception failure class: open/closed endpoint misreads, asymptote misclassification, and domain/range mismatch between interpreted graph evidence and final interval claims.
- Vision-driven math is higher risk than text-only math because the model must first perceive symbolic and geometric intent (points, holes, arrows, scales, discontinuities) before reasoning; a perception miss corrupts all downstream steps.
- Silent graph misinterpretation is unacceptable because the pipeline can return confidently formatted answers that appear valid while encoding incorrect interval truth.
- The validator is a perception integrity safeguard, not a reasoning engine: it checks consistency between extracted graph evidence and declared WORK/FINAL interval outputs, then signals retry/warning behavior.

### 2) Relative Difficulty and Complexity
- This is a moderate-to-high complexity feature because it requires:
  - Parsing semi-structured model output
  - Extracting graph evidence blocks
  - Interval normalization and comparison
  - Handling edge cases (piecewise, asymptotes, holes, arrows)
- It also touches retry logic and solve pipeline orchestration, so mistakes can affect solve flow rather than only local formatting.
- The validator must remain warning-only until baseline confidence is high enough to avoid destabilizing production solves.

### 3) What It Could Potentially Break
- False positives that trigger unnecessary retries.
- Increased latency due to additional validation and retry passes.
- Increased token usage from retry escalation paths.
- Mis-parsing of WORK sections if output-format contract drifts.
- Interference with structured outputs if validator hooks are integrated incorrectly.

### 4) Code Scope Impact
- Directly affected:
  - `llm_pipeline.py` for graph evidence extraction, retry trigger decisions, and `solve_pipeline` orchestration wiring.
  - WORK/FINAL consistency validator logic (interval parsing, normalization, mismatch detection, warning signal decisions).
  - Telemetry logging paths for validator/mismatch/retry diagnostics (event coverage and payload fields).
  - Graph fixture and integration tests in:
    - `tests/test_graph_evidence_parser.py`
    - `tests/test_work_final_consistency_validator.py`
    - `tests/test_solve_pipeline_graph_evidence_integration.py`
    - `tests/fixtures/graph_outputs/*.txt`
- Indirectly affected:
  - Solve stability metrics (retry count, latency, token cost) and operations visibility through telemetry consumers.
  - Output contract durability when future prompt changes alter WORK formatting.

### 5) Current State
- Validator runs behind feature flags.
- Behavior is warning-only.
- No output mutation/enforcement is applied yet.
- Telemetry instrumentation is already in place for validator signal tracking.

### 6) What Comes Next
- Stabilize baseline validator accuracy first.
- Measure retry frequency and false positive rate in telemetry.
- Add structured-output compatibility so parser/validator remains robust as response formats evolve.
- Only after stabilization on this branch, move auto-model development to a new branch.
- After sufficient confidence, convert validator from warning-only to enforcement mode behind an explicit flag gate.

## 14. STARRED REFERENCE SYSTEM

### 1) Activation Flow
The STAR toggle originates in `main.py` through `star_worker`, which delegates reference assignment and clearing to `toggle_star_worker` in `llm_pipeline.py`. Reference persistence is handled in backend storage artifacts:
- `STARRED_META.json` for reference state and metadata
- `STARRED.txt` for text reference content
- `REFERENCE_IMG/current_starred.png` for image reference content

### 2) Active State Semantics
`reference_active` is loaded in `solve_pipeline` as a per-solve snapshot before payload construction. The solve execution uses that snapshot for the full solve lifecycle, including request attempts and post-processing stages.
This snapshot is derived from persisted reference metadata loaded from disk at solve start.

### 3) Payload Injection Guarantee
When `reference_active` is true and metadata validation succeeds, reference content is injected into the model payload inside `_build_solve_payload`. This applies to both image problems and text problems, with type-specific injection paths for image and text references.

### 4) Retry Behavior
Retry attempts reuse the solve payload prepared from the initial snapshot. The graph retry path appends retry guidance while preserving existing payload content, including injected reference data. No retry path removes reference content.

### 5) Model Switch & Cancellation
Model switching cancels only the active solve request and does not clear persisted reference metadata. Solve cancellation checks terminate execution but do not mutate reference storage or active reference metadata.

### 6) Startup Behavior
Application startup explicitly clears reference state. As a result, references are session-scoped and do not persist across application restarts.

### 7) Edge Cases
If metadata loading fails, solve flow receives an inactive default reference state. Metadata file operations are not atomic, so a concurrent STAR toggle and solve read can theoretically produce a transient read failure. Under valid metadata loading, there is no execution branch where `reference_active` is true and payload construction proceeds without reference injection.

### 8) Baseline Snapshot
- Baseline snapshot tag `baseline_pre_visual_extraction` exists.
- It captures solve pipeline, reference injection, and telemetry state before forced visual extraction work.

**Guarantee Statement**
The system guarantees reference inclusion for any solve that reaches payload construction with a valid active reference snapshot within a running session.
