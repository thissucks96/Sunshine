## 2026-02-17 — Prompt-Hardening Investigation (Graph Extractor)

Description:
Starting focused prompt hardening for graph extraction quality, especially on non-linear/ambiguous graph visuals.

Current Finding:
- Runtime contracts and model pinning are stable (`gpt-5.2` for graph identifier/extractor paths), but endpoint/marker variance still motivates stricter extraction instructions.

Planned Work:
- Tighten extractor instructions to observation-first behavior (no coordinate guessing, scale-first interpretation, strict marker criteria).
- Validate parser compatibility against revised extractor wording and field output variance.
- If needed, apply narrow formatting-tolerance updates without changing solve output headers or clipboard contract.

## 2026-02-17 — Documentation Sync: Graph Runtime Contract

Description:
Canonical docs now explicitly describe how graph identifier and graph extractor cooperate at REF prime and solve-time injection.

Clarified Points:
- Identifier JSON contract and `YES/NO` routing behavior.
- Graph-mode bypass path (direct extraction).
- Extractor required field schema and strict parser acceptance.
- Ambiguity handling via `unclear`/`none`.
- Fallback behavior when extraction output is invalid.

## 2026-02-17 — Graph Extractor Model Comparison Outcome

Description:
Completed extraction-only model comparison on graph-only corpus to choose production graph extractor model.

Run:
- Dataset: `tests/GRAPH_CHECKER/graph_only/` (38 graph images)
- Log: `tests/GRAPH_CHECKER/extract_compare_models_20260216_192631.log`
- Models compared: `gpt-5.2`, `gpt-5-mini`, `gpt-4o`

Outcome:
- `gpt-5.2`: 38/38 valid extraction outputs
- `gpt-5-mini`: 2/38 valid, 36/38 `INVALID_GRAPH`
- `gpt-4o`: format-valid on 38/38 but only 8/38 exact structural matches vs `gpt-5.2` baseline

Decision:
- Treat `gpt-5.2` as the decisive winner for graph extraction.
- Continue with 5.2-only deep quality testing for endpoint/marker/scale fidelity.

## 2026-02-17 — Graph Runtime Model Contract Simplified

Description:
Graph runtime calls are now explicitly pinned to `gpt-5.2` only.

Changes:
- `detect_graph_presence(...)` model pin moved to `gpt-5.2`.
- Tray/config `Graph Identifier Model` selector path removed as unused ghost code.
- Legacy `graph_identifier_model` config key is cleaned during normalization.

Status:
Implemented and validated with targeted tests.

## 2026-02-17 — Graph Presence Classifier Ground-Truth Pass (Complete)

Description:
Executed full sequential validation for graph presence classification with no exclusion scoring.

Validation Mode:
- `tests/verify_classifier.py` in single-thread mode (`max_workers=1`)
- 429 retry handling with 10-second exponential backoff
- Every file counted in final accuracy math

Result:
- Dataset: `tests/GRAPH_CHECKER` (103 images)
- Outcome: 103 correct / 0 incorrect
- Accuracy: 100.00%
- Run artifact: `tests/GRAPH_CHECKER/classifier_results_20260216_185458.log`

Dataset Note:
- Positive-only subset is now available at `tests/GRAPH_CHECKER/graph_only/` (38 graph images).

## 2026-02-17 — Unified REF Graph Mode Runtime Implemented

Description:
Unified graph-mode behavior is now live in runtime using the existing REF pipeline.

Implemented Behavior:
- `graph_mode` is a shared boolean toggle in metadata/config.
- When graph mode is ON and REF is primed with an image, graph evidence extraction runs immediately and caches structured evidence.
- Solve payload prepends cached graph evidence when valid; otherwise falls back to normal REF path.

Constraints Preserved:
- `WORK:` / `FINAL ANSWER:` headers unchanged.
- Output normalization and clipboard write flow unchanged.
- Graph retry remains disabled.

Status:
Implemented and validated with targeted tests.

## 2026-02-16 — Vertex Hallucination Under STARRED Graph

Description:
When a graph image is set as STARRED reference, the system produced an incorrect visual description (vertex coordinates hallucinated), yet domain query returned correct interval.

Observed Behavior:
- Incorrect extracted vertex in status message.
- Correct domain interval computation afterward.

Hypothesis:
- Model may be generating a lightweight descriptive summary that is not evidence-grounded.
- Graph retry does not enforce structural evidence extraction.
- Forced Visual Extraction hook is currently a placeholder and not active.

Risk:
If future questions depend on vertex accuracy, hallucinated summary could propagate incorrect answers.

Status:
Resolved — False alarm for correctness; documented for architectural context.

## 2026-02-17 — Unified REF Graph Mode Direction

Description:
Direction shifted to a single REF pipeline with a `graph_mode` toggle.

Behavior (Implemented):
- If graph mode is ON and REF is not active, next REF capture is armed as graph context.
- REF-prime step runs graph evidence extraction and caches structured evidence.
- Graph-like solves reuse cached graph evidence as secondary context.

Constraints:
- Keep `WORK:` / `FINAL ANSWER:` headers unchanged.
- Keep output normalization and clipboard write flow unchanged.
- Keep graph retry disabled.
