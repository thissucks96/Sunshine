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
