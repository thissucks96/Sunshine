0 Latest Classifier Benchmark Checkpoint (2026-02-17)
- Sequential ground-truth run completed with `tests/verify_classifier.py` (`max_workers=1`, no exclusion scoring, 429 exponential backoff).
- Dataset: `tests/GRAPH_CHECKER` (103 images).
- Result: 103/103 correct (100.00%).
- Run artifact: `tests/GRAPH_CHECKER/classifier_results_20260216_185458.log`.
- Positive-only subset for targeted runs: `tests/GRAPH_CHECKER/graph_only/` (38 graph images).

0.1 Graph Extractor Model Comparison Checkpoint (2026-02-17)
- Extraction-only comparison completed on `tests/GRAPH_CHECKER/graph_only/` (38 images).
- Models tested: `gpt-5.2`, `gpt-5-mini`, `gpt-4o`.
- Result:
  - `gpt-5.2`: 38/38 valid extraction outputs
  - `gpt-5-mini`: 2/38 valid, 36/38 `INVALID_GRAPH`
  - `gpt-4o`: format-valid but structurally drifted from `gpt-5.2` baseline
- Run artifact: `tests/GRAPH_CHECKER/extract_compare_models_20260216_192631.log`.
- Decision: keep graph extraction runtime pinned to `gpt-5.2`.

0.2 Graph Extractor Prompt-Hardening Track (Planned)
- Next iteration will tighten graph extractor instructions to observation-first behavior.
- Emphasis areas:
  - lock axis scale before coordinate reporting
  - strict marker interpretation (open/closed/arrow)
  - explicit `unclear` for ambiguous or clipped evidence
- Follow-on validation will check parser/normalization tolerance needs without changing `WORK:` / `FINAL ANSWER:` or clipboard contract.

0.3 Synthetic Golden Dataset Track (Planned)
- Next QA module: `tests/generate_synthetic_graphs.py`.
- Data contract:
  - generate graph images from equation + domain/range seeds.
  - emit ground-truth labels from generation parameters for intercepts/asymptotes/key points/domain/range.
- Stress profile:
  - style-match production visuals and inject degradations (jitter, blur, compression, contrast variance).
- Goal:
  - scale beyond fixed fixture sets and detect regression on broader graph distributions without manual labeling.

1 Vision Data Flow
1. Image capture starts in `main.py:444` (`def worker`). The worker reads clipboard via `safe_clipboard_read()`.
   Anchor: `main.py:463`, search token `raw_clip, _ = safe_clipboard_read()`.
2. Clipboard image objects are accepted only when `isinstance(raw_clip, Image.Image)`.
   Anchor: `main.py:464`, search token `if isinstance(raw_clip, Image.Image):`.
3. The captured image is normalized before any model call.
   Anchor: `main.py:465`, search token `img = normalize_image_for_api(raw_clip, cfg)`.
4. `solve_pipeline()` is called with normalized image + cancellation context.
   Anchor: `main.py:466`, search token `solve_pipeline(client, img, cancel_event=cancel_event, request_id=solve_id)`.
5. In `solve_pipeline`, active reference metadata is loaded and validated (`STARRED_META.json`).
   Anchor: `llm_pipeline.py:886`, search token `meta = load_starred_meta()`.
6. If active REF image exists, it is opened, normalized, converted to base64 PNG.
   Anchor: `llm_pipeline.py:931`, search token `im = normalize_image_for_api(im.convert("RGB"), cfg)`.
   Anchor: `llm_pipeline.py:932`, search token `reference_img_b64 = image_to_base64_png(im)`.
7. Current input image is normalized again inside `solve_pipeline` (defensive normalization).
   Anchor: `llm_pipeline.py:948`, search token `input_obj = normalize_image_for_api(input_obj, cfg)`.
8. Request payload is constructed with system prompt + user parts.
   Anchor: `llm_pipeline.py:950`, search token `payload = _build_solve_payload(`.
9. `_build_solve_payload()` adds image blocks using `input_image` data URLs.
   Anchor: `llm_pipeline.py:459`, search token `"type": "input_image"`.
   Anchor: `llm_pipeline.py:461`, search token `OPTIONAL STARRED REFERENCE IMAGE`.
10. API call is executed in `_responses_text()` through `client.responses.create(**req)` with retries in caller.
    Anchor: `llm_pipeline.py:340`, search token `def _responses_text(`.
    Anchor: `llm_pipeline.py:380`, search token `resp = client.responses.create(**req)`.
11. Graph-specific retry path exists as helper logic but is disabled in `solve_pipeline`.
    Anchor: `llm_pipeline.py`, search token `# if _needs_graph_domain_range_retry(input_obj, candidate):`.
12. Output is cleaned and normalized through symbol cleanup + graph/domain post-processors.
    Anchor: `llm_pipeline.py:1021`, search token `out = _normalize_final_answer_block(out)`.
    Anchor: `llm_pipeline.py:1022`, search token `_maybe_enforce_points_to_plot`.
    Anchor: `llm_pipeline.py:1023`, search token `_maybe_enforce_domain_range_intervals`.
13. Final answer text is extracted and clipboard output is written (full output then final parsed output).
    Anchor: `llm_pipeline.py:1037`, search token `final_text = _extract_final_answer_text(out)`.
    Anchor: `llm_pipeline.py:1049`, search token `wrote_full = _clipboard_write_retry(out)`.
    Anchor: `llm_pipeline.py:1062`, search token `wrote_final = _clipboard_write_retry(final_text)`.
14. REF assignment flow (STAR) also uses image path: classify image, optional OCR, optional visual summary, then persists REF metadata.
    Anchor: `llm_pipeline.py:1075`, search token `def toggle_star_worker(client: OpenAI)`.
    Anchor: `llm_pipeline.py:1108`, search token `label_raw = _responses_text(`.
    Anchor: `llm_pipeline.py:1155`, search token `ocr_text_fallback = _responses_text(`.
    Anchor: `llm_pipeline.py:1209`, search token `img.save(img_path, format="PNG")`.

2 Accuracy Risk Points
1. Clipboard type ambiguity can bypass image handling.
   Risk: `ImageGrab.grabclipboard()` can return non-`Image.Image` types (for example file lists), but `worker` only branches on direct PIL image instances; this can route visual tasks into text path or no-input path.
   Anchor: `utils.py:302`, search token `return ImageGrab.grabclipboard(), None`.
   Anchor: `main.py:464`, search token `if isinstance(raw_clip, Image.Image):`.

2. Global image normalization may still lose small-scale detail for dense graphs.
   Risk: resizing by side/pixel thresholds and RGB conversion can blur thin strokes, faint endpoint markers, tiny tick labels, and subscript/superscript math symbols.
   Anchor: `utils.py:320`, search token `def normalize_image_for_api`.
   Anchor: `utils.py:340`, search token `img = img.resize((nw, nh), Image.LANCZOS)`.
   Anchor: `utils.py:343`, search token `if img.mode != "RGB":`.

3. OCR preprocessing is single-path (grayscale + autocontrast), which can over-amplify noise.
   Risk: one preprocessing recipe can mis-handle low-contrast worksheets, colored annotations, axis tick labels, or thin minus signs.
   Anchor: `utils.py:348`, search token `def preprocess_for_ocr`.
   Anchor: `utils.py:349`, search token `ImageOps.grayscale`.
   Anchor: `utils.py:350`, search token `ImageOps.autocontrast`.

4. REF image classifier relies on a single label with lightweight normalization.
   Risk: ambiguous visual+text problems may be misrouted between TEXTUAL and VISUAL paths, affecting downstream context fidelity.
   Anchor: `llm_pipeline.py:82`, search token `STAR_CLASSIFY_PROMPT`.
   Anchor: `llm_pipeline.py:108`, search token `def _normalize_star_label`.

5. OCR fallback chooses TEXTUAL when any OCR text is returned.
   Risk: graph-heavy images with incidental text can be classified as TEXTUAL, losing key visual structure context.
   Anchor: `llm_pipeline.py:1163`, search token `label = "TEXTUAL" if ocr_text_fallback else "VISUAL"`.

6. Visual summary is aggressively compressed for status context.
   Risk: summary truncation (`preview_text`) can remove discriminative details (endpoint openness, asymptote mention), reducing useful context cues.
   Anchor: `llm_pipeline.py:276`, search token `summary = preview_text(summary, 140)`.
   Anchor: `llm_pipeline.py:241`, search token `def preview_text`.

7. Solve payload uses free-form prompt contracts, not structured visual extraction.
   Risk: model must infer all graph semantics in one generation pass; no intermediate explicit extraction of points/endpoints/ticks.
   Anchor: `llm_pipeline.py:37`, search token `SYSTEM_PROMPT`.
   Anchor: `llm_pipeline.py:444`, search token `def _build_solve_payload`.

8. Graph retry trigger is narrow and text-pattern dependent.
   Risk: wrong answers that do not match current trigger patterns (e.g., wrong openness without exclusion words, wrong axis calibration) will not retry.
   Anchor: `llm_pipeline.py:641`, search token `def _needs_graph_domain_range_retry`.
   Anchor: `llm_pipeline.py:649`, search token `if "graph" not in low and "graphed below" not in low:`.

9. Graph retry only adds one textual hint and reruns same broad solve flow.
   Risk: no deterministic evidence extraction; retry may repeat same failure mode.
   Anchor: `llm_pipeline.py:698`, search token `def _with_graph_domain_range_retry_hint`.

10. Domain/range post-processing can rewrite model outputs based on regex cues.
    Risk: canonicalization to all-real intervals may over-correct nuanced outputs if model prose is partially malformed.
    Anchor: `llm_pipeline.py:794`, search token `def _maybe_enforce_domain_range_intervals`.
    Anchor: `llm_pipeline.py:818`, search token `Domain: (-∞, ∞) (All Real Numbers)`.

11. Points-to-plot enforcement can synthesize points from parsed linear forms.
    Risk: if equation parsing is wrong or context is non-linear but regex matches partially, generated points may be incorrect.
    Anchor: `llm_pipeline.py:756`, search token `def _maybe_enforce_points_to_plot`.
    Anchor: `llm_pipeline.py:722`, search token `def _parse_linear_rhs`.

12. Symbol normalization may alter mathematical semantics in edge cases.
    Risk: text replacements in `apply_safe_symbols` can collapse distinct notation or alter OCR artifacts into valid-looking but wrong symbols.
    Anchor: `utils.py:355`, search token `def apply_safe_symbols`.

13. Output parsing prioritizes textual patterns over semantic consistency checks.
    Risk: extracted FINAL ANSWER may look syntactically valid but disagree with WORK or image evidence.
    Anchor: `llm_pipeline.py:504`, search token `def _extract_final_answer_text`.

14. Known vision model limitation manifestation: axis tick and tiny marker ambiguity.
    Risk: open vs filled endpoints, tiny circles, faint asymptotes, and grid interpolation are common model failure areas; current pipeline depends mainly on prompt instructions plus one retry gate.
    Anchor: `llm_pipeline.py:56`, search token `interpolate proportionally between gridlines`.
    Anchor: `llm_pipeline.py:59`, search token `filled point = included, open circle = excluded`.

15. No image-fixture regression tests for graph correctness.
    Risk: changes to prompts/post-processing may silently regress graph interpretation without test detection.
    Anchor: `tests/test_model5_and_clipboard.py:77`, search token `test_visual_ref_prefix_is_in_final_clipboard_entry`.
    Anchor: `tests/` search token `graph|domain|range` shows no graph-accuracy fixtures.

3 Graph Specific Weaknesses
1. Open/closed interval handling is instruction-led, not evidence-led.
   Current behavior: prompt asks model to infer marker inclusion; retry checks whether WORK mentions marker terms.
   Weakness: if model omits marker words but still gives wrong interval, retry may not fire.
   Anchor: `llm_pipeline.py:59`, search token `filled point = included, open circle = excluded`.
   Anchor: `llm_pipeline.py:662`, search token `marker_evidence = any(`.

2. Axis tick calibration has no explicit extraction stage.
   Current behavior: model is asked to interpolate from axes/grid directly in final solve pass.
   Weakness: misread scales (non-unit ticks, cropped axes, uneven image perspective) are not validated.
   Anchor: `llm_pipeline.py:56`, search token `read from axes/grid and interpolate proportionally`.

3. Asymptote and discontinuity recognition relies on natural-language compliance.
   Current behavior: prompt says do not invent holes/discontinuities unless visible.
   Weakness: no hard checks for vertical asymptote cues, breaks, or branch continuity.
   Anchor: `llm_pipeline.py:60`, search token `Do not invent holes/discontinuities`.

4. Curve-shape and endpoint extent verification is weakly constrained.
   Current behavior: retry checks some bounded cues and arrow mentions in WORK/FINAL text.
   Weakness: if model describes shape incorrectly but consistently, pipeline accepts it.
   Anchor: `llm_pipeline.py:685`, search token `bounded_cues = any(`.
   Anchor: `llm_pipeline.py:694`, search token `arrow_evidence = "arrow" in work_low`.

5. Graph retry condition is restricted to image inputs and domain/range outputs.
   Weakness: wrong graph-derived values (e.g., f(2), intercepts) are not covered by this retry logic.
   Anchor: `llm_pipeline.py:642`, search token `Only apply this guard to image graph problems with domain/range outputs.`

6. Post-processing may mask upstream graph reading errors.
   Current behavior: rewrite helpers enforce format and certain canonicalizations.
   Weakness: formatting can appear correct even when value selection from graph is wrong.
   Anchor: `llm_pipeline.py:794`, search token `_maybe_enforce_domain_range_intervals`.

7. Reference image summary generation is one sentence and can omit geometry-critical details.
   Weakness: downstream human/operator context may not notice missing graph features.
   Anchor: `llm_pipeline.py:94`, search token `STAR_VISUAL_SUMMARY_PROMPT`.
   Anchor: `llm_pipeline.py:276`, search token `preview_text(summary, 140)`.

8. Model limitations likely to surface here
   - OCR confusion: minus vs hyphen, 1 vs 7, 0 vs O, tiny superscripts.
   - Marker ambiguity: open circles mistaken for filled points under blur/compression.
   - Grid interpolation drift on low-contrast or skewed screenshots.
   - Discontinuity hallucination/omission where branches are close.
   Current pipeline mitigation is mostly prompt guidance plus one text-triggered retry, so these errors can pass through unchanged.
   Anchor: prompt and retry anchors above.

4 Concrete Accuracy Improvements
1. Implemented: dedicated graph evidence extraction at REF-prime time.
   Change: `toggle_star_worker` runs `extract_graph_evidence(...)` when graph mode is ON and image REF is primed, then caches evidence in metadata.
   Anchor: `llm_pipeline.py`, search token `def extract_graph_evidence(`.
   Justification: separates graph perception from solve-time reasoning and allows reuse across related prompts.
   Impact: improves consistency for repeated graph-question sets while keeping solve/output contract stable.
   Test coverage: `tests/test_graph_mode_behavior.py` validates extraction run and payload usage.

2. Add dual OCR path with reconciliation for visual math text.
   Change: run OCR on both raw normalized image and preprocessed image, then merge by confidence/consistency rules.
   Anchor: `utils.py:348` (`preprocess_for_ocr`), call sites at `llm_pipeline.py:1152` and `llm_pipeline.py:1174`.
   Justification: different transforms recover different characters; reduces symbol read errors.
   Expected impact: medium-high on equations/labels embedded in graphs.
   Test idea: tiny-font axis labels and sign-sensitive equations (`-5`, `x^2`, fractions).

3. Expand graph retry triggers beyond current phrase checks.
   Change: in `_needs_graph_domain_range_retry`, trigger retries when key required facts are missing (no explicit endpoint coordinates, no marker-type statement, mismatched interval bracket/marker evidence).
   Anchor: `llm_pipeline.py:641`, search token `def _needs_graph_domain_range_retry`.
   Justification: current trigger misses many wrong-but-fluent outputs.
   Expected impact: high on domain/range reliability.
   Test idea: adversarial outputs that omit marker evidence but still present confident final intervals.

4. Add consistency validator between WORK evidence and FINAL ANSWER intervals.
   Change: parse WORK lines for endpoint inclusion/exclusion terms and compare against FINAL interval bracket choices; if mismatch, trigger corrective retry.
   Anchor: post-process region around `llm_pipeline.py:1021-1038`.
   Justification: catches internal contradiction before clipboard commit.
   Expected impact: high on open/closed interval correctness.
   Test idea: generated outputs where WORK says open endpoint but FINAL uses closed bracket.

5. Harden axis/tick interpretation instructions with explicit mandatory reporting fields.
   Change: require WORK to include explicit tick scale assumptions (`x tick = ?`, `y tick = ?`) and observed axis intersections for graph tasks.
   Anchor: `llm_pipeline.py:37`, search token `SYSTEM_PROMPT`.
   Justification: forces model to externalize scale assumptions; easier to validate and retry.
   Expected impact: medium-high on graph value interpolation.
   Test idea: graphs with non-unit tick spacing and cropped axes.

6. Add multi-hypothesis verification pass for graph tasks.
   Change: second pass asks model to verify endpoint inclusions and interval boundaries against extracted evidence before final answer extraction.
   Anchor for insertion: after `candidate` generation in `llm_pipeline.py:965`.
   Justification: reduces single-pass visual reasoning brittleness.
   Expected impact: medium-high.
   Test idea: near-boundary ambiguity cases with small endpoint markers.

7. Preserve and validate discontinuity/asymptote evidence explicitly.
   Change: add required WORK checklist items: asymptote seen/not seen, break seen/not seen, arrows seen/not seen.
   Anchor: `llm_pipeline.py:60`, search token `Do not invent holes/discontinuities`.
   Justification: converts implicit compliance into explicit evidence.
   Expected impact: medium.
   Test idea: rational-function graphs with vertical asymptote vs continuous cubic lookalikes.

8. Reduce unsafe post-processing rewrites for graph answers unless evidence present.
   Change: in `_maybe_enforce_domain_range_intervals`, only rewrite to all-real when explicit graph extension evidence exists in WORK.
   Anchor: `llm_pipeline.py:794`, search token `_maybe_enforce_domain_range_intervals`.
   Justification: avoids format cleanup masking perception errors.
   Expected impact: medium.
   Test idea: bounded parabola segment outputs that currently could be over-normalized.

9. Add graph-focused telemetry fields for auditability.
   Change: log extracted marker evidence presence, retry trigger reason, and validator mismatch types per solve.
   Anchor: telemetry calls around `llm_pipeline.py:975-1011`.
   Justification: measurable failure signatures accelerate targeted fixes.
   Expected impact: medium (diagnostic leverage).
   Test idea: integration tests asserting telemetry event shape for known failure fixtures.

10. Build image-fixture regression suite for graph tasks.
    Change: add test fixtures and expected outputs for domain/range, open/closed endpoints, asymptotes, and axis interpolation.
    Anchor gap: current tests in `tests/` are mainly pipeline/clipboard behavior, not graph image correctness.
    Justification: prevents silent regressions from prompt/post-processing changes.
    Expected impact: very high long-term correctness stability.
    Test idea: 20-40 curated graph screenshots with deterministic expected outputs.

5 Top 5 Highest Impact Accuracy Wins
1. Dedicated graph evidence extraction pass (highest).
   Anchor: insertion near `llm_pipeline.py:950`, search token `payload = _build_solve_payload(`.
   Why highest: directly addresses perception errors (endpoint markers, scales, asymptotes) before reasoning/output formatting.
   Sample case: open-circle right endpoint misread as closed in domain interval.

2. WORK-vs-FINAL consistency validator for interval bracket correctness.
   Anchor: post-process zone `llm_pipeline.py:1021-1038`.
   Why high: catches contradictions in outputs that are otherwise fluent and formatted.
   Sample case: WORK states open endpoint at x=3, FINAL returns `[... ,3]`.

3. Expanded graph retry trigger logic with required evidence checks.
   Anchor: `llm_pipeline.py:641`, search token `def _needs_graph_domain_range_retry`.
   Why high: materially increases correction opportunity for wrong graph interpretations currently not retried.
   Sample case: FINAL excludes endpoint but WORK lacks any marker observation.

4. Dual OCR path and reconciliation for equation/label extraction.
   Anchor: `utils.py:348`, OCR call sites `llm_pipeline.py:1152`, `llm_pipeline.py:1174`.
   Why high: reduces symbol and label misreads that propagate into incorrect graph reasoning.
   Sample case: `-5` read as `5`, flipping range bound sign.

5. Graph image regression fixture suite with explicit expected interval semantics.
   Anchor: test gap evidenced by `tests/` search token `graph|domain|range` with minimal coverage.
   Why high: sustained correctness over time; prevents prompt or post-process drift regressions.
   Sample case: asymptote vs endpoint confusion introduced by future prompt changes.
