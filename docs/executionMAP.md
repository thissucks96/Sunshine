# System Execution Map & Developer Guide

> **CANONICAL REFERENCE**
> This document is the forensic source of truth for SunnyNotSummer execution flows.
> Any runtime code change MUST be reflected here immediately.
> **Last Verified:** 2026-02-16

---

## Part 1: Forensic System Execution Map

### I. ENTRY LAYER — How Execution Starts
**A. Hotkey / Tray → Worker Dispatch**

- **Functions:**
  - `main.py:86` → `_debounced`
  - `main.py:444` → `worker`
  - `main.py:550` / `586` (Hotkey registration/trigger)
- **Flow:** `keyboard.add_hotkey(...)` → `_debounced("run", worker)` → `worker()`

### II. INPUT CLASSIFICATION LAYER

**A. Clipboard Read**

- **Image Priority:**
  - `utils.py:298`: `safe_clipboard_read()` calls `ImageGrab.grabclipboard()`.
- **Worker Classification:**
  - `main.py:463`: `raw_clip, _ = safe_clipboard_read()`
  - `main.py:464`: `if isinstance(raw_clip, Image.Image):` → **IMAGE SOLVE**
  - `main.py:470`: `else: text = pyperclip.paste()` → **TEXT SOLVE**
- **Rule:** No ML classifier; strict type check on clipboard object.

### III. SOLVE ORCHESTRATION LAYER

**A. Pipeline Entry**

- `llm_pipeline.py:1208`: `def solve_pipeline(...)`
- `llm_pipeline.py:1315`: `payload = _build_solve_payload(...)`
- **Critical:** Payload is built exactly ONCE before the retry loop.

### IV. PAYLOAD CONSTRUCTION LAYER

**A. Builder Function**

- `llm_pipeline.py:491`: `def _build_solve_payload(...)`
- `llm_pipeline.py:514`: System prompt assembled.
- `llm_pipeline.py:549`: User content assembled.
- **Injection Points:**
  - Reference Injection (`STARRED_CONTEXT_GUIDE`)
  - Image/Text Injection
  - **Forced Visual Extraction Hook** (Placeholder at `llm_pipeline.py:508`)

### V. GRAPH DETECTION (Pre-Solve Heuristic)

**Location:** Inside `_build_solve_payload`

- `llm_pipeline.py:501`: `is_graph_problem = False`
- `llm_pipeline.py:503`: `is_graph_problem = True` (if input is Image)
- `llm_pipeline.py:506`: `is_graph_problem = ("graph" in low) ...` (Text heuristic)
- **Status:** Purely heuristic. No pre-solve model call.

**Known Issues — Evidence Grounding Gap**
- Under STARRED graph reference, summary generation can hallucinate graph details (e.g., incorrect vertex coordinates) while a later direct domain solve may still be correct.
- Current graph retry is post-response and heuristic; it does not enforce strict evidence-first extraction before reasoning.
- Forced visual extraction hook remains placeholder-only and does not currently prevent this failure mode.
- This scenario illustrated a descriptive summary hallucination, which did not affect domain/range correctness. It remains a grounding gap for reference descriptions, not a solve correctness bug.

### VI. FORCED VISUAL EXTRACTION STATUS

- **Config:** `config.py:37`: `"ENABLE_FORCED_VISUAL_EXTRACTION": False`
- **Hook:** `llm_pipeline.py:507`: `if enable_forced_visual_extraction and is_graph_problem:`
- **Logic:** Currently a placeholder (`pass`).

### VII. MODEL CALL LAYER

**A. API Wrapper**

- `llm_pipeline.py:383`: `def _responses_text(...)`
- `llm_pipeline.py:423`: `client.responses.create(**req)`
**B. Retry Guard**
- `llm_pipeline.py:465`: Internal retry for "unsupported parameter temperature".

### VIII. RETRY SYSTEM

**A. Base Retry Loop**

- `llm_pipeline.py:1359`: `for attempt in range(retries + 1):`
**B. Graph Retry Escalation**
- `llm_pipeline.py:1003`: `def _needs_graph_domain_range_retry(...)` (Post-response check)
- `llm_pipeline.py:1378`: `retry_payload = _with_graph_domain_range_retry_hint(payload)`
- **Note:** Does not rebuild payload; appends hint to existing payload.

### IX. OUTPUT NORMALIZATION LAYER

- `llm_pipeline.py:552`: `clean_output`
- `llm_pipeline.py:663`: `_normalize_final_answer_block`
- `llm_pipeline.py:1156`: `_maybe_enforce_domain_range_intervals`
- **Contract:** `WORK` / `FINAL ANSWER` format is preserved strictly.

### X. CLIPBOARD WRITE SYSTEM

- **Two-Stage Write:**
  1. `llm_pipeline.py:1499`: Write Full Output
  2. `llm_pipeline.py:1505`: Wait `clipboard_history_settle_sec`
  3. `llm_pipeline.py:1510`: Write Final Answer Only

### XI. STARRED REFERENCE SYSTEM

**A. Activation**
- `main.py:502`: `toggle_star_worker`
**B. Persistence**
- `STARRED_META.json`, `STARRED.txt`, `REFERENCE_IMG/`
**C. Injection**
- `llm_pipeline.py:1251`: Meta loaded per solve.
- `llm_pipeline.py:1315`: Injected into payload if active.
**D. Edge Cases**
- Startup clears reference (`main.py:751`).
- Model switch preserves reference.

### XII. CANCELLATION SYSTEM

- `main.py:269`: `_cancel_active_solve`
- **Model Switch:** Cancels active solve, preserves reference state.

---

## Part 2: Developer Execution Guide (Narrative)

### Route 1: Default Text Solve

1. **User Action:** User copies text and hits hotkey.
2. **Ingest:** `worker` calls `safe_clipboard_read`.
   - *Code:* `raw_clip, _ = safe_clipboard_read()` (main.py:463)
3. **Classification:** Detected as text.
   - *Code:* `text = (pyperclip.paste() or "").strip()` (main.py:470)
4. **Payload:** `solve_pipeline` builds payload.
   - *Code:* `payload = _build_solve_payload(...)` (llm_pipeline.py:1315)
5. **Execution:** Model is called.
   - *Code:* `resp = client.responses.create(**req)` (llm_pipeline.py:423)
6. **Output:** Clipboard updated.
   - *Code:* `_clipboard_write_retry(out)` (llm_pipeline.py:1499)

### Route 2: Default Image Solve

1. **User Action:** User screenshots to clipboard and hits hotkey.
2. **Ingest:** `worker` detects Image object.
   - *Code:* `if isinstance(raw_clip, Image.Image):` (main.py:464)
3. **Normalization:** Image resized/converted.
   - *Code:* `img = normalize_image_for_api(raw_clip, cfg)` (main.py:465)
4. **Graph Heuristic:** `_build_solve_payload` flags it as graph problem.
   - *Code:* `is_graph_problem = True` (llm_pipeline.py:503)
5. **Execution & Output:** Same as Route 1.

### Route 3: Starred Reference Priming

1. **User Action:** User hits `Win+Shift+A` (or configured hotkey).
2. **Dispatch:** `star_worker` runs.
   - *Code:* `toggle_star_worker(client)` (main.py:502)
3. **Classification:** Model determines if reference is Text or Visual.
   - *Code:* `label_raw = _responses_text(...)` (llm_pipeline.py:1108)
4. **Persistence:** State saved to JSON.
   - *Code:* `save_starred_meta(meta)` (llm_pipeline.py:1209)

---

## Feature Status Matrix (Verified)

| Feature | Status | Location |
| :--- | :--- | :--- |
| **Graph Retry** | ✅ Active | `llm_pipeline.py:1003` |
| **Graph Validator** | ⚠️ Warning Only | `llm_pipeline.py:945` |
| **Forced Visual Extraction** | 🚧 Placeholder | `llm_pipeline.py:508` |
| **Pre-Solve Classifier** | ❌ Not Implemented | (Heuristic only) |
