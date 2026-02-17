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
