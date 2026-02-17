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

Planned Behavior:
- If graph mode is ON and REF is not active, next REF capture is armed as graph context.
- REF-prime step runs graph evidence extraction and caches structured evidence.
- Graph-like solves reuse cached graph evidence as secondary context.

Constraints:
- Keep `WORK:` / `FINAL ANSWER:` headers unchanged.
- Keep output normalization and clipboard write flow unchanged.
- Keep graph retry disabled.
