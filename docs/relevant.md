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
