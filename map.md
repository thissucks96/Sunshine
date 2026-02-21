# AI Context Map: SunnyNotSummer

This document serves as a "literal breakdown" of how the entire `SunnyNotSummer` architecture works. Read this to understand the data flow, file responsibilities, and key mechanisms of the app before making modifications.

---

## 1. High-Level Concept
`SunnyNotSummer` is a headless (no primary UI window) system tray application for Windows. Its primary purpose is to capture context (either from the user's screen/clipboard or from a "starred" reference) and use the OpenAI API to "solve" mathematical or visual logic problems, then copy the result back to the user's clipboard.

The user triggers actions via global keyboard hooks. The app uses `pystray` to present a background tray icon that reflects the current state (Idle, Solving, Error, etc.).

## 2. Core Modules Breakdown

### `main.py`
**Responsibility:** The Entry Point and Event Orchestrator
*   **Startup & Instance Management:** Ensures only a single instance of the app runs at a time (`ensure_single_instance`).
*   **Tray Menu (UI):** Sets up the `pystray` icon with a right-click menu allowing users to toggle settings (Graph Mode, Models, Prompts).
*   **Hotkeys & Hooks:** Uses Windows `ctypes` (or similar low-level hooks) to register global keyboard shortcuts (`setup_hotkeys`, `_on_keyboard_event`). It debounces these inputs so rapid presses don't trigger multiple API calls.
*   **Workers:** Spawns threading workers (`worker`, `star_worker`, `cycle_model_worker`) when a hotkey is pressed. This ensures the main tray thread never blocks while the API or OCR is processing.

### `config.py`
**Responsibility:** State and Settings Management
*   **File I/O:** Loads/saves user preferences to `config.json` inside the application's root directory.
*   **Concurrency Safety:** Wraps configuration access in a threading `RLock` (`_CONFIG_LOCK`) so multiple workers can safely read/write settings like the currently selected LLM model, timeouts, or toggles.

### `llm_pipeline.py`
**Responsibility:** The Brains (OpenAI Integration & Logic)
This is the heaviest file. It receives requests from `main.py`'s workers and manages the AI problem-solving loop.
*   **`solve_pipeline()`:** The primary workhorse. It takes the target problem (text or image), builds the payload, calls `client.responses.create()`, handles API retries and timeouts, parses the result looking for `FINAL ANSWER:`, and formats the final clipboard string.
*   **The "Starred" reference system:** Users can "star" a text or image (like a formula sheet or a graph scale). This file contains logic (`_prime_graph_reference_with_evidence`, `load_starred_meta`) to summarize the reference image and inject it into the `user_parts` of the `solve_pipeline` payload so the AI has secondary context.
*   **Graph Mode Forensic Rules:** Implements specialized vision constraints for graphing problems. If `graph_mode` is enabled, it uses robust prompts (`GRAPH_EVIDENCE_EXTRACTION_PROMPT`) to forensically find key points, endpoints, and intercepts before solving algebraically so the AI doesn't hallucinate. It even has fallbacks for parsing "Dark Mode" screenshots.

### `utils.py`
**Responsibility:** Global Helpers and OS Interactions
*   **UI Status & Trays:** Functions like `update_tray_icon()`, `set_app_icon()`, and dynamic colored icon generation (`_make_generated_icon`) to reflect state visually.
*   **OS Notifications:** `show_notification` triggers Windows Toast notifications or `show_message_box_notification` for alerts/errors.
*   **Clipboard I/O:** `safe_clipboard_read` and `safe_clipboard_write` handle writing to `pyperclip` safely inside threads.
*   **Image Processing:** `normalize_image_for_api` standardizes Pillow (`Image`) inputs before they go to `llm_pipeline.py`.
*   **Telemetry:** `log_telemetry()` writes execution times, token usage, and errors to `app_activity.log` for debugging and scaling.

---

## 3. The Typical Execution Flow

1.  **User Presses "Solve" Hotkey:**
    *   `main.py` hook catches the physical keypress.
    *   It checks the `_debounce_lock` and fires off `_debounced("solve", worker)`.
2.  **Context Assembly:**
    *   The `worker` thread runs. It grabs the current context (e.g., reads the clipboard text or takes a screenshot).
3.  **Pipeline Invocation:**
    *   `llm_pipeline.py` -> `solve_pipeline(client, input_obj)` is invoked.
    *   It loads configs and checks if a `STARRED` reference is active.
    *   It bundles these into the highly structured `SYSTEM_PROMPT`.
4.  **Network Call (The Bottleneck):**
    *   `_responses_text()` shoots the payload to OpenAI. **This is synchronous and the tray icon spins (wait time).**
5.  **Parsing & Output:**
    *   The LLM replies with `WORK: [...]` and `FINAL ANSWER: [...]`.
    *   `llm_pipeline.py` strips out the WORK block and leaves just the clean answer (or formatted inequality).
6.  **User Feedback:**
    *   `utils.py` is called to run `safe_clipboard_write()`.
    *   A Toast notification flashes: *"Solved → copied to clipboard"*.
    *   The tray icon returns to idle.
