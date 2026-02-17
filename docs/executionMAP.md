# System Execution Map & Developer Guide

> **CANONICAL REFERENCE**
> This document is the forensic source of truth for SunnyNotSummer execution flows.
> Any runtime code change MUST be reflected here immediately.
> **Last Verified:** 2026-02-17

---

## Part 1: Forensic System Execution Map

### I. ENTRY LAYER — How Execution Starts
**A. Hotkey / Tray → Worker Dispatch**

- **Functions:**
  - `main.py:86` → `_debounced`
  - `main.py:444` → `worker`
  - `main.py:550` / `586` (Hotkey registration/trigger)
- **Flow:** `keyboard.add_hotkey(...)` → `_debounced("run", worker)` → `worker()`
- **Operational Note:** External keyboard-hook tools (e.g., AutoHotkey v1 scripts with global remaps) can block `ctrl+shift+x` hotkey activation. Tray `Solve Now` remains functional because it dispatches directly to the same worker path.
- **Status Update:** Graph handling now runs through unified REF with tray toggle `GRAPH MODE ON/OFF` (no separate graph hotkey/store path).
- **Startup Reliability Check:** app startup probes both the selected solve model and `gpt-5.2` graph-extraction model; failures emit user-visible warnings.

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

- `llm_pipeline.py:1241`: `def solve_pipeline(...)`
- `llm_pipeline.py:1348`: `payload = _build_solve_payload(...)`
- **Critical:** Payload is built exactly ONCE before the retry loop.

### IV. PAYLOAD CONSTRUCTION LAYER

**A. Builder Function**

- `llm_pipeline.py:507`: `def _build_solve_payload(...)`
- `llm_pipeline.py:539`: System prompt assembled.
- `llm_pipeline.py:544`: User content assembled.
- **Injection Points:**
  - Reference Injection (`STARRED_CONTEXT_GUIDE`)
  - Image/Text Injection
  - Forced Visual Extraction Injection (`user_parts.insert(0, forced_extraction_msg)`)

### V. FORCED VISUAL EXTRACTION TRIGGERING (Pre-Solve)

**Location:** Inside `_build_solve_payload`

- `llm_pipeline.py:516`: reads feature flag `ENABLE_FORCED_VISUAL_EXTRACTION`
- `llm_pipeline.py:517`: trigger branch for primary image input (`isinstance(input_obj, Image.Image)`)
- `llm_pipeline.py:518`: trigger branch for active STARRED image reference (`reference_active` + `reference_type == "IMG"`)
- `llm_pipeline.py:520`: trigger branch for domain/range intent keywords in user text
- **Status:** Flag-gated and prompt-only; no extra model call added.

**Known Issues — Evidence Grounding Gap**
- Under STARRED graph reference, summary generation can hallucinate graph details (e.g., incorrect vertex coordinates) while a later direct domain solve may still be correct.
- Current graph retry is post-response and heuristic; it does not enforce strict evidence-first extraction before reasoning.
- Forced visual extraction now injects evidence-first instructions before user content when trigger conditions match.
- This scenario illustrated a descriptive summary hallucination, which did not affect domain/range correctness. It remains a grounding gap for reference descriptions, not a solve correctness bug.

### VI. FORCED VISUAL EXTRACTION STATUS

- **Config:** `config.py:37`: `"ENABLE_FORCED_VISUAL_EXTRACTION": False`
- **Hook:** `llm_pipeline.py:516-537`: computes `should_force_visual_extraction` from flag + input/reference/text triggers.
- **Placement:** `llm_pipeline.py:578-580` inserts mandatory instruction block at the beginning of `user_parts`.
- **Instruction Contract:** Numbered evidence-first extraction prompt requires scale, boundaries, arrows, asymptotes, and discontinuities before solving.
- **Logic:** Prompt-only evidence-first instruction injection; solve retry loop unchanged.

### VII. MODEL CALL LAYER

**A. API Wrapper**

- `llm_pipeline.py:399`: `def _responses_text(...)`
- `llm_pipeline.py:439`: `client.responses.create(**req)`
**B. Retry Guard**
- `llm_pipeline.py:481`: Internal retry for "unsupported parameter temperature".
**C. Graph Identifier Selector**
- Removed from runtime to avoid ghost model-routing paths.
**D. REF-Prime Scout Classifier**
- `detect_graph_presence(image_path, ...)` runs only in REF image priming flow.
- Scout call is pinned to `gpt-5.2` and returns binary `YES/NO`.
- `YES` routes to graph-evidence extraction; `NO` falls back to normal REF classification.
- Validation harness: `tests/verify_classifier.py` supports sequential ground-truth mode (`max_workers=1`) with 429 exponential backoff and no exclusion scoring.
- Latest benchmark: `tests/GRAPH_CHECKER` full set achieved 103/103 (100.00%) in sequential no-exclusion mode; positive-only subset is maintained at `tests/GRAPH_CHECKER/graph_only/` (38 images).
- Extraction A/B benchmark (`tests/GRAPH_CHECKER/extract_compare_models_20260216_192631.log`): `gpt-5.2` is the production winner; `gpt-5-mini` under-detected graphs and `gpt-4o` showed structural drift against 5.2 evidence.

### VII.1 Graph Identifier/Extractor Contract (Current Runtime)

**Identifier Prompt Contract**
- System prompt requires JSON-only output:
  - `{"is_graph":"YES/NO","reasoning":"..."}`
- Decision rule in prompt is explicit:
  - If coordinate grid + axes + curve/line are present, classify `YES` even when table/text is also present.
- Forensic hardening added:
  - binary-only response contract (no extra keys/fences/prose)
  - explicit guard rule that auxiliary UI/text/table content does not negate `YES`

**Extractor Prompt Contract**
- If image is not a coordinate-plane graph, extractor must return exactly `INVALID_GRAPH`.
- Otherwise extractor must return exactly one `GRAPH_EVIDENCE` block with these fields:
  - `LEFT_ENDPOINT` (`x`, `y`, `marker`)
  - `RIGHT_ENDPOINT` (`x`, `y`, `marker`)
  - `ASYMPTOTES`
  - `DISCONTINUITIES`
  - `SCALE` (`x_tick`, `y_tick`)
  - `CONFIDENCE` (`0.0-1.0`)
- Allowed ambiguity tokens are built into the schema (`unclear`, `none`), so uncertain visuals should degrade gracefully instead of forcing guesses.
- Optional usefulness fields are now supported for richer coordinate extraction without breaking required schema:
  - `INTERCEPTS`
  - `KEY_POINTS`
- Behavioral asymptote instruction now explicitly allows detection from curve behavior (approaches constant x/y) even when no dashed guide is drawn.
- Prompt tuning notes (current):
  - query-anchor wording added for `KEY_POINTS` extraction (for example f(2), g(-2), h(x)=13)
  - dark-mode wording added for low-contrast handling via axis calibration and high-contrast curve focus
  - inline comment markers were removed from block examples to prevent response contamination
  - conditional dark-mode forensic override is applied during extraction when dark-mode detection is triggered
  - guide-line intersection rule added: horizontal/vertical measurement lines define valid `KEY_POINTS` even without physical dots
  - exact-value rule added for labeled measurement lines (for example x=5, y=13 => key point `(5,13)`)
- Forensic hardening added:
  - observation-first visual witness rule (no algebraic inference from surrounding text)
  - scale-first calibration requirement before coordinate reporting
  - explicit unknown safety for blurry/cutoff/obstructed visuals
  - strict endpoint marker semantics (open/closed/arrow)
  - asymptote safety rule (do not label axes as asymptotes without visible curve behavior evidence)

**Gating Behavior**
- `graph_mode=ON` at REF prime:
  - Bypasses identifier and runs extraction directly on image REF.
- `graph_mode=OFF` + `ENABLE_AUTO_GRAPH_DETECT_REF_PRIME=true`:
  - Runs identifier first, then extraction only when identifier returns `YES`.
- Otherwise:
  - Falls back to normal REF classification flow.

**Strict Parse Enforcement**
- Extractor output is accepted only if `_extract_graph_evidence_block(...)` validates required header + field formats.
- Invalid/malformed extraction is treated as `INVALID_GRAPH` and does not become active graph evidence.
- Parser is backward-compatible and tolerant:
  - required fields are still mandatory
  - unknown uppercase fields inside `GRAPH_EVIDENCE` are ignored
  - optional `INTERCEPTS`/`KEY_POINTS` are parsed when present
- Dark-mode recovery behavior:
  - when dark-mode is detected, extraction runs with additional forensic guidance
  - a second candidate pass requests `KEY_POINT_CANDIDATES` and reranks to a final `KEY_POINTS` coordinate
  - candidate coordinates are preprocessed with snap-to-integer threshold (`0.15`) before consensus/median rerank
  - final coordinate is upserted into the `GRAPH_EVIDENCE` block only if the updated block remains parser-valid
- General key-point normalization:
  - near-integer `KEY_POINTS` are normalized with a lightweight snap-to-grid post-processor (`threshold=0.20`)
  - normalized key-points are upserted only when resulting `GRAPH_EVIDENCE` remains parser-valid

**Solve-Time Usage**
- Cached graph evidence is injected only when:
  - `graph_mode` is `ON`, and
  - cached evidence passes parser validation.
- If cached evidence is absent/invalid, solve falls back to standard REF context behavior.
- Latest post-hardening validation artifacts:
  - Identifier benchmark: `tests/GRAPH_CHECKER/classifier_results_20260216_200749.log` (103/103).
  - Extractor smoke: `tests/GRAPH_CHECKER/extractor_smoke_20260216_201044.log` (38/38 parser-valid on `graph_only`).
  - Tiered benchmark baseline: `tests/GRAPH_CHECKER/tiered_accuracy_20260216_204619.json` (Easy 100.00%, Medium 75.00%, Hard 40.00%).
  - Tiered benchmark after polish: `tests/GRAPH_CHECKER/tiered_accuracy_20260216_205236.json` (Easy 100.00%, Medium 87.50%, Hard 60.00%).
  - Hard-tier-only run after conditional dark-mode recovery: `tests/GRAPH_CHECKER/hard_tier_accuracy_20260216_210654.json` (Hard 70.00%).
  - Hard-tier rerun after integer snapping/grid-bias patch: `tests/GRAPH_CHECKER/hard_tier_accuracy_20260216_211155.json` (Hard 70.00%; dark-mode `(2)/(3)/(5)` drift remains).
  - Medium 8-file rerun after guide-line precision polish: `tests/GRAPH_CHECKER/medium_tier_8file_accuracy_20260216_214053.json` (8/8, 100.00%).
- Limitation contract:
  - Dark/low-contrast graph extraction is best-effort only and may exhibit coordinate drift.
  - See `docs/LIMITATIONS.md` for explicit support boundary.

### VII.2 Graph Extractor Prompt-Hardening Track (Planned)

- Current status: investigation/planning only; runtime behavior is unchanged in this map section.
- Next prompt iteration will enforce stricter observation-first extraction:
  - read and lock scale before reporting coordinates
  - use strict marker semantics (open vs closed vs arrow continuation)
  - use ambiguity-safe values (`unclear`) instead of guessed coordinates
- Compatibility requirement:
  - if prompt wording changes introduce equivalent but varied field-value phrasing, update parser/format tolerance narrowly
  - do not alter `WORK:` / `FINAL ANSWER:` headers, solve loop contract, or clipboard write flow

### VIII. RETRY SYSTEM

**A. Base Retry Loop**

- `llm_pipeline.py:1392`: `for attempt in range(retries + 1):`
**B. Graph Retry Path (Disabled in solve loop)**
- `llm_pipeline.py:1036`: `def _needs_graph_domain_range_retry(...)` (helper retained)
- `llm_pipeline.py:1093`: `def _with_graph_domain_range_retry_hint(...)` (helper retained)
- `llm_pipeline.py:1527`: graph retry branch is commented out in `solve_pipeline`, so no graph-specific second API call is executed.

### IX. OUTPUT NORMALIZATION LAYER

- `llm_pipeline.py:585`: `clean_output`
- `llm_pipeline.py:696`: `_normalize_final_answer_block`
- `llm_pipeline.py:1189`: `_maybe_enforce_domain_range_intervals`
- **Contract:** `WORK` / `FINAL ANSWER` format is preserved strictly.

### X. CLIPBOARD WRITE SYSTEM

- **Two-Stage Write:**
  1. `llm_pipeline.py:1499`: Write Full Output
  2. `llm_pipeline.py:1505`: Wait `clipboard_history_settle_sec`
  3. `llm_pipeline.py:1510`: Write Final Answer Only

### XI. STARRED REFERENCE SYSTEM

**A. Activation**
- `main.py:502`: `toggle_star_worker`
- Graph mode uses the same REF toggle flow and graph mode ON is controlled by tray entry `GRAPH MODE ON/OFF`.
**A1. Graph Extraction Model Pin**
- During graph-mode image REF priming, graph evidence extraction is pinned to `gpt-5.2` for strongest visual parsing before solve-time reasoning.
**A2. Auto Graph Identifier (Flag-Gated)**
- Image REF priming path can run `detect_graph_presence(...)` when `ENABLE_AUTO_GRAPH_DETECT_REF_PRIME` is enabled.
- Binary route: `YES` triggers graph-evidence extraction, `NO` falls back to standard REF classification.
**A3. Variance Handling**
- Extractor contract is strict on structure but tolerant on uncertain visuals:
  - strict required fields and formatting
  - tolerant value tokens (`unclear`, `none`) for partial/ambiguous graphs
- This means the pipeline is not limited to perfect linear graphs, but it does require coordinate-graph context and schema compliance.
**B. Persistence**
- `STARRED_META.json`, `STARRED.txt`, `REFERENCE_IMG/`
- Unified metadata fields: `graph_mode`, `graph_evidence`, `last_primed_ts`.
- `save_starred_meta` now uses atomic write (`.tmp` then replace).
**C. Injection**
- `llm_pipeline.py:1251`: Meta loaded per solve.
- `llm_pipeline.py:1348`: Injected into payload if active.
- If graph mode is ON and cached evidence is valid, graph evidence is prepended as secondary context; otherwise solve falls back to standard REF behavior.
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
   - *Code:* `payload = _build_solve_payload(...)` (llm_pipeline.py:1348)
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
   - *Code:* `should_force_visual_extraction = ...` (flag + image/reference/text cues in `_build_solve_payload`)
5. **Execution & Output:** Same as Route 1.

### Route 3: Starred Reference Priming

1. **User Action:** User hits `Win+Shift+A` (or configured hotkey).
2. **Dispatch:** `star_worker` runs.
   - *Code:* `toggle_star_worker(client)` (main.py:502)
3. **Graph Mode ON Path:** If graph mode is enabled and REF prime content is image, graph evidence extraction runs immediately.
   - *Code:* `extract_graph_evidence(...)` (llm_pipeline.py:391)
4. **Persistence:** REF metadata is saved with `graph_evidence` and `last_primed_ts`.
   - *Code:* `save_starred_meta(meta)` (llm_pipeline.py)

---

## Feature Status Matrix (Verified)

| Feature | Status | Location |
| :--- | :--- | :--- |
| **Graph Retry** | ⏸ Disabled In `solve_pipeline` | `llm_pipeline.py` (commented retry branch) |
| **Graph Validator** | ⚠️ Warning Only | `llm_pipeline.py:945` |
| **Forced Visual Extraction** | ✅ Flag-Gated Prompt Injection | `_build_solve_payload` in `llm_pipeline.py` |
| **Unified Graph Mode** | ✅ Implemented (`graph_mode` + evidence cache) | `main.py`, `llm_pipeline.py`, `config.py` |
