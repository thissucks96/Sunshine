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
