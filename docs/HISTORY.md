## 2026-02-17 — Tray Prompt Channel Toggles (Window/Clipboard) With Permanent Activity Log

- Runtime behavior update:
  - Added tray toggles for:
    - `WINDOW PROMPTS ON/OFF`
    - `CLIPBOARD PROMPTS ON/OFF`
  - Both toggles persist in `config.json` via:
    - `window_prompts_enabled`
    - `clipboard_prompts_enabled`
- Fanout behavior:
  - `app_activity.log` remains always-on (unchanged).
  - Window notifications/message boxes now respect `window_prompts_enabled`.
  - Clipboard prompt mirroring now respects `clipboard_prompts_enabled`.
- Scope safety:
  - Solve pipeline, output normalization, `WORK:`/`FINAL ANSWER:` headers, and graph retry status are unchanged.

## 2026-02-17 — Phase 2 Intent: Synthetic Graph Generation + Golden Dataset (Docs Only)

- Direction update for next module (staging, no runtime solve-path code changes yet):
  - build `tests/generate_synthetic_graphs.py` to generate synthetic graph images from equation + domain/range seeds.
  - emit per-sample ground truth keys at generation time (equation family, parameters, asymptotes/intercepts/key points/domain/range).
  - apply style matching (red curve, dashed brown guides, gray grid, labeled axes) plus intentional degradations (jitter/blur/compression/contrast) for stress coverage.
- Purpose:
  - create a reproducible "golden dataset" pipeline for long-term regression safety beyond current fixed fixtures.
  - remove manual-label bottlenecks by deriving labels directly from generation parameters.

## 2026-02-17 — Release Candidate Gate: Real-User Validation Next

- Current build status after system acceptance:
  - Light mode: `33/33` (`100.00%`)
  - Dark mode stress: `2/5` (`40.00%`, experimental)
- Decision:
  - This version is now marked as ready for real-user testing on live problem flows.
  - Next gate is production-like user validation (hotkey/tray solve, REF priming behavior, and output usability across real sessions).

## 2026-02-17 — Final System Acceptance Run (Full Pipeline)

- Added end-to-end validation harness:
  - `tests/validate_full_pipeline.py`
  - Flow per case: `has_graph` detector gate -> `extract_graph_evidence` -> strict tier verification.
- Added detector helper in runtime module:
  - `llm_pipeline.has_graph(image_path, client, timeout)` as a thin wrapper over `detect_graph_presence`.
- Acceptance artifacts:
  - `tests/GRAPH_CHECKER/system_acceptance_light_20260216.txt`
  - `tests/GRAPH_CHECKER/system_acceptance_dark_20260216.txt`
- Results:
  - Light-mode production set (dark-mode excluded): `33/33` (`100.00%`)
  - Dark-mode stress set only: `2/5` (`40.00%`)
- Notes:
  - Light-mode target met at 100%.
  - Dark-mode remains stress/best-effort and non-blocking for production acceptance.

## 2026-02-17 — Guide-Line Override Prompt + 33/33 Light-Mode Victory Run

- Runtime prompt update in `llm_pipeline.py`:
  - Added mandatory guide-line override wording to both:
    - `GRAPH_EVIDENCE_PROMPT_APPEND`
    - `GRAPH_EVIDENCE_EXTRACTION_PROMPT`
  - New rule requires extracting `KEY_POINTS` from vertical/horizontal guide-line intersections on the curve, even without a drawn dot.
- File (14) verification:
  - Standard extraction after patch produced `KEY_POINTS: (x=5, y=13)` in validation run.
- Final light-mode benchmark rerun (dark-mode excluded):
  - `tests/GRAPH_CHECKER/final_lightmode_tiered_accuracy_20260216_221723.json`
  - `tests/GRAPH_CHECKER/final_lightmode_tiered_accuracy_20260216_221723.txt`
  - Result: `33/33` (`100.00%`)
- Output contract status unchanged:
  - `WORK:` / `FINAL ANSWER:` unchanged
  - graph retry remains disabled
  - normalization and clipboard flow unchanged

## 2026-02-17 — File 14 Forensic Diagnostic (Raw Reasoning Trace)

- Added targeted diagnostic script: `tests/diagnose_file_14.py`.
- Captured 3-run raw-text forensic trace artifact:
  - `tests/GRAPH_CHECKER/diagnose_file_14_20260216_221349.txt`
- Result:
  - all 3 runs explicitly identified the guide lines as `x=5` and `y=13`
  - all 3 runs reported intersection coordinate `(5, 13)` on the red curve
- Interpretation:
  - vision perception for file `(14)` is present; remaining benchmark miss is a structured extraction/format compliance issue, not a visibility limitation.

## 2026-02-17 — Final Light-Mode Tiered Validation Rerun (33 Files, Dark-Mode Excluded)

- Executed a fresh full extraction benchmark on tagged light-mode files only (Easy 10, Medium 15, Hard 8).
- Artifacts:
  - `tests/GRAPH_CHECKER/final_lightmode_tiered_accuracy_20260216_215522.json`
  - `tests/GRAPH_CHECKER/final_lightmode_tiered_accuracy_20260216_215522.txt`
- Result:
  - Easy: `10/10` (`100.00%`)
  - Medium: `14/15` (`93.33%`)
  - Hard: `8/8` (`100.00%`)
  - Overall: `32/33` (`96.97%`)
- Single remaining miss:
  - `graph is present (14).png` returned `KEY_POINTS` with unresolved y-value (`(x=5, y=unclear)`) in the benchmark run.
- Additional probe:
  - repeated isolated extraction for file `(14)` shows variable outputs across runs, including valid `(5,13)` and unresolved variants.
- Runtime contract status:
  - `WORK:` / `FINAL ANSWER:` format unchanged.
  - Graph retry remains disabled.
  - Clipboard/normalization behavior unchanged.

## 2026-02-17 — Precision Polish For Guide-Line Intersections (File 14 Fix)

- Runtime prompt refinement in `llm_pipeline.py`:
  - `KEY_POINTS` guidance now explicitly treats geometric intersections of horizontal/vertical guide lines as valid coordinates even without a physical dot.
  - Straight non-axis/non-curve lines are explicitly treated as measurement tools.
  - Added exact-value rule: when guide lines align to labeled values, use the labeled coordinate exactly (no nearby-value approximation).
- Runtime post-processor update in `llm_pipeline.py`:
  - Added `_normalize_graph_evidence_key_points(...)` to snap near-integer `KEY_POINTS` coordinates (`threshold=0.20`) and upsert parser-valid normalized output.
- Verification:
  - Isolator on `graph is present (14).png` now returns `KEY_POINTS: (x=5, y=13)`.
  - Medium 8-file benchmark artifact: `tests/GRAPH_CHECKER/medium_tier_8file_accuracy_20260216_214053.json`
  - Result: `8/8` (`100.00%`).

## 2026-02-17 — Light-Mode Final Acceptance Run (Dark-Mode Excluded Scope)

- Executed final tiered report on 33 files (full graph set excluding filenames containing `dark mode`).
- Artifact:
  - `tests/GRAPH_CHECKER/lightmode_tiered_accuracy_20260216_212033.json`
  - `tests/GRAPH_CHECKER/lightmode_tiered_accuracy_20260216_212033.txt`
- Results:
  - Easy: `100.00%` (endpoint/domain checks)
  - Medium: `87.50%` (remaining miss: `graph is present (14).png` key-point extraction)
  - Hard: `100.00%` (behavioral asymptote checks)
- Merge status:
  - `77a45e7` is already contained in `master` and requires no further merge action.

## 2026-02-17 — Strategic Pivot: Freeze Dark-Mode Tuning, Finalize Schema/Robustness Sprint

- Product decision:
  - Halt further dark-mode optimization work after stress validation pass.
  - Accept hard-tier dark-mode accuracy as resilience signal, not production gating criterion.
- Finalization:
  - Keep schema usefulness and parser robustness gains as production path.
  - Mark "Graph Extraction Schema & Robustness" sprint complete.
- Documentation:
  - Added `docs/LIMITATIONS.md` with best-effort dark/low-contrast support statement and expected coordinate drift note.

## 2026-02-17 — Integer Snapping + Grid-Bias Prompt For Dark-Mode Recovery

- Runtime update in `llm_pipeline.py`:
  - Added `_snap_value(val, threshold=0.15)` and applied snapping to candidate x/y values before dark-mode key-point reranking.
  - Preserved existing consensus/median rerank logic after snap preprocessing.
  - Added explicit grid-bias sentence to dark-mode key-point candidate prompt:
    - aggressively favor integer grid intersections unless point clearly lies between grid lines.
- Verification artifacts:
  - Failed-file rerun (`dark mode (2)/(3)/(5)`): `tests/GRAPH_CHECKER/darkmode_failedfiles_verify_20260216_211114.txt`
    - Result: `0/3` corrected in this pass.
  - Hard-tier rerun: `tests/GRAPH_CHECKER/hard_tier_accuracy_20260216_211155.json`
    - Result: `70.00%` (7/10), below 85% target.
    - Remaining failures are coordinate drift on dark-mode `(2)`, `(3)`, `(5)`.

## 2026-02-17 — Conditional Forensic Recovery For Dark-Mode Key-Points

- Runtime enhancement in `llm_pipeline.py` for dark-mode graph extraction recovery:
  - Added dark-mode detection using filename cues and luminance histogram checks.
  - Added conditional dark-mode forensic extraction prompt append (mental inversion + anchor mapping + noise filtering).
  - Added dark-mode key-point recovery pass that requests 3 coordinate candidates and reranks to a final coordinate using integer-consensus + median fallback.
  - Added `KEY_POINTS` upsert into `GRAPH_EVIDENCE` block after recovery.
- Added tests: `tests/test_dark_mode_recovery.py` (detection, candidate parsing/rerank, and graph-evidence key-point upsert behavior).
- Hard-tier-only validation artifact after this change:
  - `tests/GRAPH_CHECKER/hard_tier_accuracy_20260216_210654.json`
  - Result: `70.00%` (7/10), improved from prior `60.00%` tier run.
  - Remaining misses: dark-mode coordinate drift on files `(2)`, `(3)`, and `(5)` variants.

## 2026-02-17 — Tiered Accuracy Run + Final Prompt Polish (Dark-Mode/Key-Point Focus)

- Executed tiered extraction benchmark on `tests/GRAPH_CHECKER/graph_only_tagged_v1` with rule-based scoring.
- Baseline run artifact: `tests/GRAPH_CHECKER/tiered_accuracy_20260216_204619.json` (`.txt` companion)
  - Easy: `100.00%`
  - Medium: `75.00%`
  - Hard: `40.00%`
  - Hard failures clustered as missed behavioral asymptotes and dark-mode coordinate drift.
- Applied iterative prompt polish in `llm_pipeline.py`:
  - strengthened behavioral horizontal asymptote wording
  - reinforced query-anchor key-point extraction wording for low-contrast/dark-mode graphs
  - removed inline `# optional` markers from block examples to avoid output contamination
- Rerun artifact after polish: `tests/GRAPH_CHECKER/tiered_accuracy_20260216_205236.json` (`.txt` companion)
  - Easy: `100.00%`
  - Medium: `87.50%`
  - Hard: `60.00%`
  - Remaining hard misses are primarily dark-mode `KEY_POINTS` null/drift on files `(2)-(5)` dark mode variants.

## 2026-02-17 — Backward-Compatible Graph Evidence Usefulness Patch

- Runtime parser update in `llm_pipeline.py` for graph evidence compatibility:
  - `_extract_graph_evidence_block(...)` now tolerates unknown uppercase fields inside `GRAPH_EVIDENCE` blocks instead of failing early.
  - Added optional parsed fields:
    - `INTERCEPTS`
    - `KEY_POINTS`
  - Existing required fields and parse contract remain unchanged.
- Prompt update in `llm_pipeline.py`:
  - `GRAPH_EVIDENCE_EXTRACTION_PROMPT` and `GRAPH_EVIDENCE_PROMPT_APPEND` now define optional `INTERCEPTS`/`KEY_POINTS` lines.
  - Asymptote instructions now include behavioral detection (curve approaching constant x/y) even when no dashed guide is present, with axis safety retained.
- Output contract remains unchanged:
  - `WORK:` / `FINAL ANSWER:` headers unchanged.
  - Clipboard flow unchanged.
  - Graph retry policy remains disabled.

## 2026-02-17 — Forensic Prompt-Hardening for Graph Identifier/Extractor

- Runtime prompt update in `llm_pipeline.py`:
  - Hardened `GRAPH_IDENTIFIER_PROMPT` to strict JSON-only binary triage with explicit axes+plot guard rule.
  - Hardened `GRAPH_EVIDENCE_EXTRACTION_PROMPT` with observation-first, scale-first, unknown-safety, strict marker semantics, and asymptote safety instructions.
  - Synchronized `GRAPH_EVIDENCE_PROMPT_APPEND` with the same forensic extraction constraints for solve-time consistency.
- Parser/output contract preserved:
  - `GRAPH_EVIDENCE` top-level keys unchanged.
  - `WORK:` / `FINAL ANSWER:` headers unchanged.
  - Clipboard flow and retry policy (graph retry disabled) unchanged.
- Verification after prompt hardening:
  - `python tests/verify_classifier.py` on `tests/GRAPH_CHECKER` returned 103/103 (100.00%), artifact `tests/GRAPH_CHECKER/classifier_results_20260216_200749.log`.
  - Graph extractor smoke run on `tests/GRAPH_CHECKER/graph_only` returned 38/38 parser-valid, artifact `tests/GRAPH_CHECKER/extractor_smoke_20260216_201044.log`.

## 2026-02-17 — Kick Off Graph Extractor Prompt-Hardening Track (Docs Only)

- Documentation-only direction update: next iteration will harden the graph extractor prompt with stricter observation-first rules.
- Planned prompt refinements include scale-first reading, strict marker semantics (open/closed/arrow), and explicit unknown handling for ambiguous visuals.
- Expected downstream impact: parser/normalization tolerance checks may need minor adjustments for richer evidence wording while preserving `WORK:` / `FINAL ANSWER:` headers and clipboard flow.
- No runtime code changes in this entry.

## 2026-02-17 — Clarify Graph Identifier/Extractor Runtime Contract In Docs

- Documentation update only: clarified end-to-end graph runtime behavior in canonical map docs.
- Added explicit contract details for:
  - identifier JSON schema and gating conditions
  - extractor required `GRAPH_EVIDENCE` field list
  - strict parser enforcement with tolerant value tokens (`unclear`, `none`)
  - solve-time evidence injection/fallback behavior
- No runtime code changes.

## 2026-02-17 — Graph Extractor A/B Result: gpt-5.2 Decisive Winner

- Ran extraction-only comparison on `tests/GRAPH_CHECKER/graph_only` (38 graph images) with:
  - `gpt-5.2`
  - `gpt-5-mini`
  - `gpt-4o`
- Run artifact: `tests/GRAPH_CHECKER/extract_compare_models_20260216_192631.log`.
- Result summary:
  - `gpt-5.2`: 38/38 valid graph-evidence outputs
  - `gpt-5-mini`: 2/38 valid, 36/38 `INVALID_GRAPH`
  - `gpt-4o`: 38/38 valid format, but only 8/38 exact structural matches vs `gpt-5.2` baseline
- Interpretation:
  - `gpt-5.2` is the decisive winner for graph extraction reliability.
  - `gpt-4o` remains structurally drift-prone for endpoints/markers/feature fields even when format-valid.
- Direction:
  - Keep graph runtime pinned to `gpt-5.2`.
  - Next validation phase will focus on deeper 5.2-only extraction quality checks.

## 2026-02-17 — Pin All Graph Runtime Calls To gpt-5.2 (Remove Selector Ghost Code)

- Runtime behavior change: graph presence detection (`detect_graph_presence`) is now pinned to `gpt-5.2` (same as graph evidence extraction).
- Removed unused graph-identifier model selector wiring from tray/runtime (`Graph Identifier Model` menu path).
- Removed legacy config key normalization for `graph_identifier_model`; legacy key is now cleaned from config on normalize.
- Goal: eliminate ghost model-selection paths and enforce a single graph-model contract for production graph flows.
- Core solve/output contract unchanged: `WORK:` / `FINAL ANSWER:` headers, normalization, retry policy (graph retry disabled), and clipboard flow remain unchanged.

## 2026-02-17 — Ground-Truth Classifier Validation (Sequential, No Exclusions)

- Updated `tests/verify_classifier.py` to support ground-truth validation mode:
  - single-threaded execution (`max_workers=1`)
  - aggressive 429 retry backoff (10s exponential)
  - no exclusion math; every image is counted in final accuracy
- Completed full dataset run on `tests/GRAPH_CHECKER`:
  - total images: 103
  - correct: 103
  - incorrect: 0
  - final accuracy: 100.00%
- Logged run artifact: `tests/GRAPH_CHECKER/classifier_results_20260216_185458.log`.
- Added/confirmed positive-only benchmark subset: `tests/GRAPH_CHECKER/graph_only/` (38 graph images).
- Scope note: this validates graph-presence classification only; solve output contract (`WORK:` / `FINAL ANSWER:`), normalization, retry policy, and clipboard flow are unchanged.

## 2026-02-17 — Intelligent Pipeline Reliability Pass

- Added three-tier status/error fanout:
  - clipboard mirror
  - tray/window notification path
  - dated root activity log (`app_activity.log`)
- Added startup model health probes:
  - selected solve model is probed on startup
  - hardcoded graph-extraction model (`gpt-5.2`) is probed on startup
  - warning statuses are emitted when either probe fails
- Kept model-switch safety behavior: tray model changes are probe-gated and blocked on failure.
- Refined REF-prime scout classifier:
  - `detect_graph_presence(image_path, ...)` now performs binary `YES/NO` graph detection
  - classifier model for this call is pinned to `gpt-4o-mini`
  - integration remains restricted to `toggle_star_worker` (reference image priming path)
- Added standalone classifier verification script: `tests/verify_classifier.py` (logs YES/NO only; no extraction).
- Refactored `save_starred_meta` to atomic write (`.tmp` + `os.replace`) to reduce metadata corruption risk.

## 2026-02-17 — Add REF-Prime Graph Identifier Function (Flag-Gated)

- Added graph identifier function path in `toggle_star_worker` for image REF priming only, behind `ENABLE_AUTO_GRAPH_DETECT_REF_PRIME` (default `False`).
- Added `detect_graph_presence(...)` in `llm_pipeline.py` with confidence-threshold decisioning via `graph_identifier_min_confidence`.
- Added behavior wiring: when enabled and detector is confident, REF image prime routes directly to graph evidence extraction; otherwise flow falls back to normal REF classification.
- Added config defaults/normalization for:
  - `ENABLE_AUTO_GRAPH_DETECT_REF_PRIME`
  - `graph_identifier_min_confidence`
- Added tests for confident route and below-threshold fallback.
- Graph toggle behavior is unchanged in this step.

## 2026-02-17 — Document Graph Identifier Sample Fixture Set

- Added project note: `tests/GRAPH_CHECKER/` is the sample graph image set reserved for graph-identifier evaluation and tuning.
- This is documentation-only; no runtime behavior changes were introduced.

## 2026-02-17 — Add Graph Identifier Model Selector Scaffold

- Added config key `graph_identifier_model` with normalization and migration handling (including removed-model fallback).
- Added tray menu selector `Graph Identifier Model` that persists a dedicated model choice for upcoming graph-presence identification logic.
- Current runtime behavior is unchanged for solve/graph-toggle flows: this is selector scaffolding only, with no graph-toggle removal and no classifier execution yet.
- Output contract unchanged: `WORK:` / `FINAL ANSWER:` headers, normalization, retry policy (graph retry disabled), and clipboard flow remain unchanged.

## 2026-02-17 — Pin Graph-Mode Evidence Extraction To gpt-5.2

- Runtime behavior change in graph-mode REF priming: `extract_graph_evidence(...)` now always uses `gpt-5.2`.
- Scope is intentionally narrow: only graph-evidence extraction is pinned; normal REF visual summary and solve model selection still follow existing model/config behavior.
- Purpose: maximize visual extraction reliability for graph coordinates/features while keeping main solve model routing unchanged.
- Output contract unchanged: `WORK:` / `FINAL ANSWER:` headers, normalization, retry policy (graph retry disabled), and clipboard flow are unchanged.

## 2026-02-17 — Implement Unified REF Graph Mode Runtime

- Removed legacy dedicated graph-reference runtime wiring (separate graph hotkey/store path) from active execution.
- Added unified graph mode metadata in config/runtime: `graph_mode`, `graph_evidence`, and `last_primed_ts`.
- Added tray toggle `GRAPH MODE ON/OFF` to control graph-mode behavior without introducing a separate REF system.
- Updated REF priming behavior: when graph mode is ON and the next REF is primed as image, graph evidence is extracted immediately and cached for subsequent solves.
- Updated solve payload assembly: if graph mode is ON and cached graph evidence is valid, evidence is prepended before normal context; invalid or absent evidence safely falls back to normal REF behavior.
- Added graph-mode tests in `tests/test_graph_mode_behavior.py` (state toggle, priming extraction, payload injection, fallback).
- Preserved output and runtime contracts: `WORK:` / `FINAL ANSWER:` headers unchanged, normalization unchanged, clipboard flow unchanged, graph retry remains disabled.

## 2026-02-17 — Direction Update: Unified REF Graph Mode

- Product direction update: adopt a single REF pipeline plus a `graph_mode` toggle (`ON/OFF`).
- New intended behavior: when `graph_mode` is enabled and no REF is active, the app arms the next REF capture as graph context and runs graph-evidence extraction at REF-prime time.
- Solve behavior target: graph-mode evidence is reused as supporting context while normal solve flow, output headers (`WORK:` / `FINAL ANSWER:`), normalization, retry policy, and clipboard flow stay stable.
- This update records direction and implementation intent; the next runtime commit is expected to apply the unified graph-mode wiring.

## 2026-02-16 — Document External AHK Hotkey Conflict With Solve Trigger

- Operational finding: solve hotkey (`ctrl+shift+x`) can fail when an AutoHotkey v1 script is running with global keyboard interception/remaps.
- Confirmed behavior: tray `Solve Now` continues to work because it bypasses the global hotkey matcher path.
- Root cause observed in user environment: AHK global hook/remap conflict (including a backtick remap) interfered with combo detection.
- Resolution in user environment: disabling/removing the conflicting AHK binding restored solve hotkey behavior.
- Runtime code and output contract unchanged.

## 2026-02-16 — Standardize Forced Visual Extraction Instruction Contract

- Runtime behavior change in payload guidance only: `FORCED_VISUAL_EXTRACTION_INSTRUCTION` wording was standardized to require a numbered evidence checklist (scale, boundaries, arrows, asymptotes, discontinuities) before reasoning.
- Existing insertion point remains unchanged (`user_parts.insert(0, forced_extraction_msg)`).
- Output headers (`WORK:` / `FINAL ANSWER:`), normalization logic, retry loop, and clipboard flow remain unchanged.

## 2026-02-16 — Implement Forced Visual Extraction Trigger Clarifications

- Runtime behavior change in payload construction: `should_force_visual_extraction` now activates only when `ENABLE_FORCED_VISUAL_EXTRACTION` is true and at least one condition is true:
  - primary input is image
  - STARRED reference is active and image-based
  - user text contains domain/range intent keywords
- Forced visual extraction instruction block is now inserted at the start of user content via `user_parts.insert(0, forced_extraction_msg)`.
- System prompt, output contract, and solve retry loop behavior remain unchanged.

## 2026-02-16 — Disable Graph Domain/Range Retry Requery In solve_pipeline

- Runtime behavior change: graph domain/range retry trigger path in `solve_pipeline` is now disabled.
- The graph retry payload hint modifier (`_with_graph_domain_range_retry_hint`) remains in code but is no longer invoked by solve orchestration.
- Result: no graph-specific additional API call (`solve_graph_retry`) is made during solve attempts.

## 2026-02-16 — Graph Evidence Grounding Investigation Resolved

- Investigation concluded that the STARRED summary hallucinated a vertex description but did not corrupt domain/range solve results.
- The domain solve path independently re-read the image and produced the correct interval.
- This was a false alarm for correctness. No runtime bug found.
- Documentation reflects this finding and ongoing architectural improvement planning.

## 2026-02-16 — Investigating Graph Evidence Grounding

- Discovered vertex hallucination under STARRED graph reference.
- No runtime changes.
- Beginning investigation and architectural reinforcement planning.

## 2026-02-16 — Execution Map Governance Formalized

- Formalized repository governance to treat `docs/executionMAP.md` as the canonical execution reference.
- Added mandatory pre-change execution-layer review requirement in `AGENTS.md`.
- Added synchronization rule requiring runtime changes to be reflected in both `docs/executionMAP.md` and `docs/HISTORY.md`.
- Added canonical execution map document structure and developer execution guide in `docs/executionMAP.md`.
- Runtime code unchanged.

## 2026-02 — Baseline Before Forced Visual Extraction

- Created baseline snapshot tag `baseline_pre_visual_extraction`.
- This tag captures state before implementing mandatory visual extraction in graph solves.
- Used to compare future accuracy experiments.
- No code changes were made.
