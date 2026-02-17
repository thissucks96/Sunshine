import os
import io
import json
import base64
import re
import time
import uuid
from fractions import Fraction
from typing import Any, Dict, List, Optional, Union

import pyperclip
from PIL import Image
from openai import OpenAI

from config import get_config, MODEL, app_home_dir
from utils import (
    safe_clipboard_read,
    safe_clipboard_write,
    normalize_image_for_api,
    preprocess_for_ocr,
    set_status,
    set_reference_active,
    mark_prompt_success,
    log_telemetry,
    apply_safe_symbols,
)

# STAR storage
STARRED_META_FILE = "STARRED_META.json"
STARRED_TEXT_FILE = "STARRED.txt"
STARRED_IMG_DIR = "REFERENCE_IMG"
STARRED_IMG_FILE = "current_starred.png"

REFERENCE_TYPE_IMG = "IMG"
REFERENCE_TYPE_TEXT = "TEXT"

SYSTEM_PROMPT = (
    "You are solving a math problem.\n"
    "Output plain text only. No markdown. No LaTeX.\n"
    "Format contract:\n"
    "- Produce exactly one WORK block.\n"
    "- Produce exactly one FINAL ANSWER block.\n"
    "- Do not output DETECTED_INPUT or Q:.\n"
    "If exactly one value is requested, output:\n"
    "<raw problem text only, no label>\n"
    "WORK:\n"
    "<minimal symbolic/reading steps>\n"
    "FINAL ANSWER: <answer>\n"
    "If multiple values are requested, output:\n"
    "<raw problem text only, no label>\n"
    "WORK:\n"
    "<concise steps grouped by item, in original order>\n"
    "FINAL ANSWER:\n"
    "<one line per requested item in original order, format: <item label> = <value>>\n"
    "Graph-reading rules:\n"
    "- For graph-based values (for example f(2)), read from axes/grid and interpolate proportionally between gridlines.\n"
    "- Do not snap to nearest integer unless the plotted point is exactly on that integer level.\n"
    "- If read is approximate, use a concise decimal estimate.\n"
    "- For domain/range from graphs, determine endpoint inclusion strictly from markers: filled point = included, open circle = excluded.\n"
    "- Do not invent holes/discontinuities unless an explicit open circle or break is visible.\n"
    "- Use the plotted function extent, not the axis bounds, to determine domain/range.\n"
    "- In WORK for graph domain/range, explicitly state observed endpoint markers and inclusion/exclusion.\n"
    "Graphing-equation rules:\n"
    "- If asked to graph an equation by table, choose reasonable x-values (prefer integers, often around -5 to 5, and include x=0 when useful).\n"
    "- Compute corresponding y-values and provide points in coordinate form.\n"
    "- WORK must include a line formatted exactly as: Points to plot: (x1, y1), (x2, y2), ...\n"
    "- FINAL ANSWER must list only the coordinate set for the plotted points.\n"
    "- For linear equations, if domain/range is requested, both are All Real Numbers.\n"
    "Domain/range format rules:\n"
    "- When domain/range is requested, provide BOTH interval notation and words, concisely.\n"
    "- Prefer compact lines in FINAL ANSWER:\n"
    "Domain: <interval> (<words>)\n"
    "Range: <interval> (<words>)\n"
    "- For all real numbers, interval notation must be exactly: (-∞, ∞)\n"
    "Other rules:\n"
    "- Preserve original requested-item order exactly.\n"
    "- For inequalities, use interval notation.\n"
    "- If all reals: FINAL ANSWER: All Real Numbers\n"
    "- If none: FINAL ANSWER: No Solution\n"
)

STAR_CLASSIFY_PROMPT = (
    "Classify this image as one of exactly two labels:\n"
    "TEXTUAL or VISUAL.\n"
    "Return ONLY one word."
)

STAR_OCR_PROMPT = (
    "Transcribe all visible text, equations, labels, and instructions from this image.\n"
    "Do NOT solve.\n"
    "Return plain text only."
)

STAR_VISUAL_SUMMARY_PROMPT = (
    "Describe the image in one concise sentence for a reference badge.\n"
    "Focus on the main visual content only.\n"
    "No preface, no markdown."
)

STARRED_CONTEXT_GUIDE = (
    "Use STARRED reference as optional context only.\n"
    "CURRENT PROBLEM is primary and must control the answer.\n"
    "Do not answer prompts that appear only in STARRED reference.\n"
    "If reference conflicts with current input, trust current input.\n"
)

GRAPH_EVIDENCE_PROMPT_APPEND = (
    "For graph problems only, begin WORK with a structured GRAPH_EVIDENCE block:\n"
    "GRAPH_EVIDENCE:\n"
    "  LEFT_ENDPOINT: x=<value|unclear>, y=<value|unclear>, marker=<open|closed|arrow|unclear>\n"
    "  RIGHT_ENDPOINT: x=<value|unclear>, y=<value|unclear>, marker=<open|closed|arrow|unclear>\n"
    "  ASYMPTOTES: <none|x=<...>; y=<...>; ...>\n"
    "  DISCONTINUITIES: <none|hole at x=<...>; jump at x=<...>; ...>\n"
    "  SCALE: x_tick=<value|unclear>, y_tick=<value|unclear>\n"
    "  CONFIDENCE: <0.0-1.0>\n"
    "Inside GRAPH_EVIDENCE do not include the boundary markers WORK, FINAL ANSWER, or [FINAL].\n"
    "After GRAPH_EVIDENCE, continue normal WORK reasoning.\n"
)

GRAPH_EVIDENCE_EXTRACTION_PROMPT = (
    "You are extracting structured evidence from a graph image only.\n"
    "If the image is not a graph on coordinate axes, return exactly: INVALID_GRAPH\n"
    "Otherwise return exactly this block and nothing else:\n"
    "GRAPH_EVIDENCE:\n"
    "  LEFT_ENDPOINT: x=<value|unclear>, y=<value|unclear>, marker=<open|closed|arrow|unclear>\n"
    "  RIGHT_ENDPOINT: x=<value|unclear>, y=<value|unclear>, marker=<open|closed|arrow|unclear>\n"
    "  ASYMPTOTES: <none|x=<...>; y=<...>; ...>\n"
    "  DISCONTINUITIES: <none|hole at x=<...>; jump at x=<...>; ...>\n"
    "  SCALE: x_tick=<value|unclear>, y_tick=<value|unclear>\n"
    "  CONFIDENCE: <0.0-1.0>\n"
)

# Graph evidence extraction is intentionally pinned to the strongest visual model.
GRAPH_EVIDENCE_EXTRACTION_MODEL = "gpt-5.2"

FORCED_VISUAL_EXTRACTION_INSTRUCTION = (
    "MANDATORY VISUAL EXTRACTION STEP:\n"
    "Before computing any answer, explicitly extract ALL of the following in your WORK section:\n"
    "1. X-axis scale (units per tick)\n"
    "2. Left Boundary (coordinate + open/closed)\n"
    "3. Right Boundary (coordinate + open/closed)\n"
    "4. Arrows (direction of continuation)\n"
    "5. Asymptotes (vertical/horizontal lines)\n"
    "6. Discontinuities (holes/breaks)\n"
    "If a feature is absent, write 'None'. If ambiguous or blocked, write 'Unknown'.\n"
    "Do NOT guess coordinates. Derive your FINAL ANSWER strictly from evidence."
)

GRAPH_INTENT_CUES = (
    "domain",
    "range",
    "interval notation",
    "open circle",
    "closed circle",
    "hole",
    "asymptote",
    "arrow",
    "endpoint",
    "discontinuity",
)


def _normalize_star_label(raw: str) -> str:
    s = " ".join(str(raw or "").upper().split())
    if not s:
        return ""
    hits = []
    for token, label in (
        ("TEXTUAL", "TEXTUAL"),
        ("TEXT", "TEXTUAL"),
        ("VISUAL", "VISUAL"),
        ("IMAGE", "VISUAL"),
        ("GRAPH", "VISUAL"),
    ):
        for m in re.finditer(rf"\b{re.escape(token)}\b", s):
            prefix = s[max(0, m.start() - 10):m.start()]
            # Ignore explicitly negated labels like "NOT TEXTUAL".
            if re.search(r"\bNOT\s*$", prefix):
                continue
            hits.append((m.start(), label))
    if not hits:
        return ""
    hits.sort(key=lambda x: x[0])
    return hits[0][1]


def _starred_meta_path() -> str:
    return os.path.join(app_home_dir(), STARRED_META_FILE)


def _starred_base_dir() -> str:
    p = os.path.join(app_home_dir(), STARRED_IMG_DIR)
    os.makedirs(p, exist_ok=True)
    return p


def _default_reference_meta() -> Dict[str, Any]:
    return {
        "reference_active": False,
        "reference_type": None,
        "text_path": "",
        "image_path": "",
        "reference_summary": "",
        "graph_mode": False,
        "graph_evidence": None,
        "last_primed_ts": 0,
    }


def _normalize_reference_meta(raw_meta: Dict[str, Any]) -> Dict[str, Any]:
    meta = dict(raw_meta or {})
    reference_active = bool(meta.get("reference_active", False))
    reference_type = meta.get("reference_type")
    reference_summary = str(meta.get("reference_summary", "") or "")
    graph_mode = bool(meta.get("graph_mode", False))
    raw_graph_evidence = meta.get("graph_evidence")
    graph_evidence = str(raw_graph_evidence).strip() if isinstance(raw_graph_evidence, str) else None
    if graph_evidence == "":
        graph_evidence = None
    try:
        last_primed_ts = int(meta.get("last_primed_ts", 0) or 0)
    except Exception:
        last_primed_ts = 0

    # Backward compatibility for older STAR schema.
    if "enabled" in meta or "mode" in meta:
        legacy_active = bool(meta.get("enabled", False))
        legacy_mode = str(meta.get("mode", "")).strip().lower()
        reference_active = legacy_active
        if legacy_mode == "text":
            reference_type = REFERENCE_TYPE_TEXT
        elif legacy_mode == "visual":
            reference_type = REFERENCE_TYPE_IMG
        elif not legacy_active:
            reference_type = None

    if reference_type not in (REFERENCE_TYPE_IMG, REFERENCE_TYPE_TEXT):
        reference_type = None

    if not reference_active:
        reference_type = None
        reference_summary = ""
        if not graph_mode:
            graph_evidence = None

    return {
        "reference_active": reference_active,
        "reference_type": reference_type,
        "text_path": str(meta.get("text_path", "") or ""),
        "image_path": str(meta.get("image_path", "") or ""),
        "reference_summary": reference_summary,
        "graph_mode": graph_mode,
        "graph_evidence": graph_evidence,
        "last_primed_ts": last_primed_ts,
    }


def load_starred_meta() -> Dict[str, Any]:
    p = _starred_meta_path()
    default_meta = _default_reference_meta()
    if not os.path.exists(p):
        meta = default_meta
        with open(p, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        return meta
    try:
        with open(p, "r", encoding="utf-8") as f:
            raw_meta = json.load(f)
    except Exception:
        return default_meta

    normalized = _normalize_reference_meta(raw_meta)
    if normalized != raw_meta:
        save_starred_meta(normalized)
    return normalized


def save_starred_meta(meta: Dict[str, Any]) -> None:
    with open(_starred_meta_path(), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def _clear_reference(meta: Dict[str, Any]) -> Dict[str, Any]:
    meta.update({
        "reference_active": False,
        "reference_type": None,
        "text_path": "",
        "image_path": "",
        "reference_summary": "",
        "graph_evidence": None,
        "last_primed_ts": 0,
    })
    return meta


def _set_reference_indicator_from_meta(meta: Dict[str, Any]) -> None:
    set_reference_active(bool(meta.get("reference_active", False)))


def clear_reference_state(source: str, status_message: Optional[str] = None) -> None:
    try:
        meta = load_starred_meta()
    except Exception as e:
        log_telemetry("ref_clear_error", {"source": source, "error": str(e)})
        meta = _default_reference_meta()

    _clear_reference(meta)
    try:
        save_starred_meta(meta)
    except Exception as e:
        log_telemetry("ref_clear_error", {"source": source, "error": str(e)})

    _set_reference_indicator_from_meta(meta)
    log_telemetry("ref_clear", {"source": source})
    if status_message:
        set_status(status_message)


def preview_text(text: str, max_chars: int = 140) -> str:
    # Keep badge/status summaries compact and plain.
    normalized = " ".join(str(text or "").replace("`", "").split())
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 3:
        return normalized[:max_chars]
    return normalized[: max_chars - 3].rstrip() + "..."


def _can_assign_reference(meta: Dict[str, Any]) -> bool:
    if bool(meta.get("reference_active", False)):
        set_status("REF is active. Press STAR again to clear first.")
        return False
    return True


def image_to_base64_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _summarize_visual_reference(client: OpenAI, model_name: str, img_b64: str, timeout: int) -> str:
    payload = [
        {"role": "system", "content": [{"type": "input_text", "text": STAR_VISUAL_SUMMARY_PROMPT}]},
        {"role": "user", "content": [{"type": "input_image", "image_url": f"data:image/png;base64,{img_b64}"}]},
    ]
    try:
        summary = _responses_text(
            client=client,
            model_name=model_name,
            input_payload=payload,
            timeout=timeout,
            temperature=0.0,
            max_output_tokens=64,
        ).strip()
        summary = preview_text(summary, 140)
        if not summary:
            log_telemetry("summary_generation_error", {"type": REFERENCE_TYPE_IMG, "error": "empty_summary"})
            return ""

        cut_idx = -1
        for mark in (".", "!", "?"):
            idx = summary.find(mark)
            if idx != -1 and (cut_idx == -1 or idx < cut_idx):
                cut_idx = idx
        if cut_idx != -1 and cut_idx + 1 < len(summary):
            summary = summary[: cut_idx + 1].strip()
        return summary
    except Exception as e:
        log_telemetry("summary_generation_error", {"type": REFERENCE_TYPE_IMG, "error": str(e)})
        return ""


def _is_valid_graph_evidence_text(graph_evidence: Optional[str]) -> bool:
    t = str(graph_evidence or "").strip()
    if not t:
        return False
    if t.upper().startswith("INVALID_GRAPH"):
        return False
    return bool(_extract_graph_evidence_block(t))


def set_graph_mode(enabled: bool) -> bool:
    meta = load_starred_meta()
    target = bool(enabled)
    meta["graph_mode"] = target
    if not target:
        meta["graph_evidence"] = None
        meta["last_primed_ts"] = 0
    save_starred_meta(meta)
    return bool(meta.get("graph_mode", False))


def extract_graph_evidence(
    image_path: str,
    client: OpenAI,
    model_name: str,
    timeout: int,
) -> str:
    try:
        with Image.open(str(image_path or "")) as im:
            graph_img = normalize_image_for_api(im.convert("RGB"), get_config())
        graph_b64 = image_to_base64_png(graph_img)
    except Exception as e:
        log_telemetry("graph_evidence_extract_error", {"stage": "image_load", "error": str(e)})
        return "INVALID_GRAPH"

    payload = [
        {"role": "system", "content": [{"type": "input_text", "text": GRAPH_EVIDENCE_EXTRACTION_PROMPT}]},
        {"role": "user", "content": [{"type": "input_image", "image_url": f"data:image/png;base64,{graph_b64}"}]},
    ]
    try:
        extracted = _responses_text(
            client=client,
            model_name=model_name,
            input_payload=payload,
            timeout=max(8, int(timeout)),
            temperature=0.0,
            max_output_tokens=500,
            flow_name="graph_evidence_extract",
        ).strip()
    except Exception as e:
        log_telemetry("graph_evidence_extract_error", {"stage": "api", "error": str(e)})
        return "INVALID_GRAPH"

    if not extracted:
        return "INVALID_GRAPH"
    if extracted.upper().startswith("INVALID_GRAPH"):
        return "INVALID_GRAPH"
    if _extract_graph_evidence_block(extracted) is None:
        log_telemetry("graph_evidence_extract_error", {"stage": "parse", "error": "invalid_format"})
        return "INVALID_GRAPH"
    return extracted


def _guess_visual_summary_from_ocr_text(ocr_text: str) -> str:
    t = " ".join(str(ocr_text or "").split())
    low = t.lower()
    if not low:
        return ""

    if any(k in low for k in ("domain", "range", "graphed", "graph", "coordinate plane", "x-axis", "y-axis")):
        return "graph on a coordinate plane"
    if any(k in low for k in ("| x |", "f(x)", "k(x)", "table below", "table of values", "x:", "y:")):
        return "table of function values"
    if any(k in low for k in ("solve", "equation", "inequality", "function")):
        return "math problem screenshot"
    return preview_text(t, 140)


def _is_gpt5_family_model(model_name: str) -> bool:
    return str(model_name or "").strip().lower().startswith("gpt-5")


def _timeout_type_from_exception(exc: Exception) -> str:
    msg = str(exc or "").lower()
    if "connect timeout" in msg:
        return "connect"
    if "read timeout" in msg:
        return "read"
    if "write timeout" in msg:
        return "write"
    if "pool timeout" in msg:
        return "pool"
    if "request timed out" in msg or "timed out" in msg or "timeout" in msg:
        return "request"
    return ""


def _exception_payload(exc: Exception) -> Dict[str, Any]:
    timeout_type = _timeout_type_from_exception(exc)
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "is_timeout": bool(timeout_type),
        "timeout_type": timeout_type,
    }


def _usage_value(container: Any, key: str) -> Any:
    if container is None:
        return None
    if isinstance(container, dict):
        return container.get(key)
    return getattr(container, key, None)


def _safe_int_or_none(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _extract_usage_fields(resp: Any) -> Dict[str, Optional[int]]:
    usage = _usage_value(resp, "usage")
    prompt_tokens = _safe_int_or_none(_usage_value(usage, "prompt_tokens"))
    completion_tokens = _safe_int_or_none(_usage_value(usage, "completion_tokens"))
    prompt_details = _usage_value(usage, "prompt_tokens_details")
    cached_tokens = _safe_int_or_none(_usage_value(prompt_details, "cached_tokens"))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "cached_prompt_tokens": cached_tokens,
    }


def _responses_text(
    client: OpenAI,
    model_name: str,
    input_payload: List[Dict[str, Any]],
    timeout: int,
    temperature: float,
    max_output_tokens: int,
    flow_name: str = "responses",
    request_id: Optional[str] = None,
) -> str:
    rid = str(request_id or f"{flow_name}-{uuid.uuid4().hex[:10]}")
    req_started_unix = time.time()
    api_attempt = 0
    is_gpt5_family = _is_gpt5_family_model(str(model_name))
    req_max_output_tokens = max(128, int(max_output_tokens)) if is_gpt5_family else max(16, int(max_output_tokens))
    req = {
        "model": model_name,
        "input": input_payload,
        "max_output_tokens": req_max_output_tokens,
        "timeout": timeout,
    }
    if not is_gpt5_family:
        req["temperature"] = temperature
    while True:
        api_attempt += 1
        call_started_mono = time.monotonic()
        log_telemetry(
            "api_request_start",
            {
                "request_id": rid,
                "flow": flow_name,
                "model": str(model_name),
                "time_started_unix": req_started_unix,
                "logical_attempt": 1,
                "api_attempt": api_attempt,
                "timeout_sec": timeout,
                "temperature_included": "temperature" in req,
            },
        )
        try:
            resp = client.responses.create(**req)
            call_elapsed_ms = int((time.monotonic() - call_started_mono) * 1000)
            usage_fields = _extract_usage_fields(resp)
            log_telemetry(
                "api_request_complete",
                {
                    "request_id": rid,
                    "flow": flow_name,
                    "model": str(model_name),
                    "time_started_unix": req_started_unix,
                    "time_completed_unix": time.time(),
                    "time_to_first_byte_ms": None,
                    "time_completed_ms": call_elapsed_ms,
                    "retries": max(0, api_attempt - 1),
                    "timeout_type": "",
                    "exception_payload": None,
                    "prompt_tokens": usage_fields.get("prompt_tokens"),
                    "completion_tokens": usage_fields.get("completion_tokens"),
                    "cached_prompt_tokens": usage_fields.get("cached_prompt_tokens"),
                },
            )
            break
        except Exception as e:
            call_elapsed_ms = int((time.monotonic() - call_started_mono) * 1000)
            payload = _exception_payload(e)
            log_telemetry(
                "api_request_error",
                {
                    "request_id": rid,
                    "flow": flow_name,
                    "model": str(model_name),
                    "time_started_unix": req_started_unix,
                    "time_completed_unix": time.time(),
                    "time_to_first_byte_ms": None,
                    "time_completed_ms": call_elapsed_ms,
                    "retries": max(0, api_attempt - 1),
                    "timeout_type": payload.get("timeout_type", ""),
                    "exception_payload": payload,
                },
            )
            # Some models (for example certain GPT-5 variants) reject temperature.
            msg = str(e).lower()
            if "unsupported parameter" in msg and "temperature" in msg and "temperature" in req:
                req.pop("temperature", None)
                continue
            raise
    text = getattr(resp, "output_text", None)
    if text:
        return text

    pieces = []
    try:
        for out_item in resp.output:
            if getattr(out_item, "type", "") == "message":
                for c in getattr(out_item, "content", []):
                    ctype = str(getattr(c, "type", "") or "").lower()
                    ctext = getattr(c, "text", None)
                    if isinstance(ctext, str) and ctext.strip():
                        # Handle both output_text and text-like content variants.
                        pieces.append(ctext)
                    elif ctype == "output_text":
                        # Keep legacy path for SDK objects exposing output_text content.
                        pieces.append(str(getattr(c, "text", "") or ""))
    except Exception:
        pass
    return "\n".join(pieces).strip()


def _build_solve_payload(
    input_obj: Union[str, Image.Image],
    reference_active: bool,
    reference_type: Optional[str],
    reference_text: str,
    reference_img_b64: str,
    graph_mode: bool = False,
    graph_evidence_text: Optional[str] = None,
    enable_graph_evidence_parsing: bool = False,
) -> List[Dict[str, Any]]:
    cfg = get_config()
    enable_forced_visual_extraction = bool(cfg.get("ENABLE_FORCED_VISUAL_EXTRACTION", False))
    has_primary_image_input = isinstance(input_obj, Image.Image)
    # Use string literal "IMG" to prevent NameError if constant is missing
    has_active_starred_image = bool(reference_active and reference_type == "IMG")
    user_text = str(input_obj or "").lower() if isinstance(input_obj, str) else ""
    has_domain_range_intent = any(
        cue in user_text
        for cue in GRAPH_INTENT_CUES
    )
    should_force_visual_extraction = bool(
        enable_forced_visual_extraction
        and (has_primary_image_input or has_active_starred_image or has_domain_range_intent)
    )

    sys_prompt = SYSTEM_PROMPT
    if enable_graph_evidence_parsing:
        sys_prompt = SYSTEM_PROMPT + "\n" + GRAPH_EVIDENCE_PROMPT_APPEND
    sys_msg = {"role": "system", "content": [{"type": "input_text", "text": sys_prompt}]}
    user_parts = []

    if isinstance(input_obj, Image.Image):
        cur_b64 = image_to_base64_png(input_obj)
        if reference_active and reference_type == REFERENCE_TYPE_IMG and reference_img_b64:
            # Keep current problem first so vision attention anchors on the task to solve.
            user_parts.append({"type": "input_text", "text": STARRED_CONTEXT_GUIDE + "CURRENT PROBLEM IMAGE (solve this):"})
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{cur_b64}"})
            user_parts.append({"type": "input_text", "text": "OPTIONAL STARRED REFERENCE IMAGE (secondary context only):"})
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{reference_img_b64}"})
        elif reference_active and reference_type == REFERENCE_TYPE_TEXT and reference_text:
            ref_text_context = preview_text(reference_text, 1200)
            user_parts.append({"type": "input_text", "text": STARRED_CONTEXT_GUIDE + "CURRENT PROBLEM IMAGE (solve this):"})
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{cur_b64}"})
            user_parts.append({"type": "input_text", "text": f"OPTIONAL STARRED TEXT (secondary context only):\n{ref_text_context}"})
        else:
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{cur_b64}"})
    else:
        cur_text = str(input_obj)
        if reference_active and reference_type == REFERENCE_TYPE_IMG and reference_img_b64:
            user_parts.append({"type": "input_text", "text": STARRED_CONTEXT_GUIDE + f"CURRENT PROBLEM (solve this):\n{cur_text}"})
            user_parts.append({"type": "input_text", "text": "OPTIONAL STARRED REFERENCE IMAGE (secondary context only):"})
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{reference_img_b64}"})
        elif reference_active and reference_type == REFERENCE_TYPE_TEXT and reference_text:
            ref_text_context = preview_text(reference_text, 1200)
            merged = (
                STARRED_CONTEXT_GUIDE
                + f"CURRENT PROBLEM (solve this):\n{cur_text}\n\n"
                + f"OPTIONAL STARRED TEXT (secondary context only):\n{ref_text_context}"
            )
            user_parts.append({"type": "input_text", "text": merged})
        else:
            user_parts.append({"type": "input_text", "text": cur_text})

    if should_force_visual_extraction:
        forced_extraction_msg = {"type": "input_text", "text": FORCED_VISUAL_EXTRACTION_INSTRUCTION}
        user_parts.insert(0, forced_extraction_msg)
    if graph_mode and _is_valid_graph_evidence_text(graph_evidence_text):
        graph_ctx = (
            "GRAPH MODE CACHED EVIDENCE (secondary context only; use for cross-checking graph features):\n"
            + str(graph_evidence_text).strip()
        )
        user_parts.insert(0, {"type": "input_text", "text": graph_ctx})

    return [sys_msg, {"role": "user", "content": user_parts}]


def clean_output(text: str) -> str:
    cleaned = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("DETECTED_INPUT:"):
            value = stripped.replace("DETECTED_INPUT:", "", 1).strip()
            if value:
                cleaned.append(value)
            continue
        if stripped.startswith("Q:"):
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def _extract_final_answer_text(out: str) -> str:
    lines = (out or "").splitlines()
    start_idx = -1
    inline_text = ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.upper().startswith("FINAL ANSWER:"):
            start_idx = i
            inline_text = stripped[len("FINAL ANSWER:"):].strip()
            break

    if start_idx == -1:
        return ""

    parts = []
    if inline_text:
        parts.append(inline_text)
    for line in lines[start_idx + 1:]:
        s = line.strip()
        if s:
            parts.append(s)

    # De-duplicate repeated final-answer lines while preserving order.
    unique_parts: List[str] = []
    seen = set()
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique_parts.append(p)

    def _is_bare_answer_line(s: str) -> bool:
        t = s.strip()
        if re.fullmatch(r"\{[^{}]+\}", t):
            return True
        if re.fullmatch(r"[\(\[][^\[\]\(\)]+[\)\]]", t):
            return True
        if re.fullmatch(r"-?\d+(?:\.\d+)?(?:/\d+)?", t):
            return True
        if re.fullmatch(r"\([^)]+\)(?:\s*,\s*\([^)]+\))*", t):
            return True
        return False

    # If both a verbose labeled line and the same bare value are present, keep the bare value only.
    bare_lines = [p for p in unique_parts if _is_bare_answer_line(p)]
    if len(bare_lines) == 1 and len(unique_parts) > 1:
        bare = bare_lines[0]
        if any(bare in p and p != bare for p in unique_parts):
            return bare

    result = "\n".join(unique_parts).strip()
    # Keep final-only payload concise for common domain/range answer lines.
    m = re.fullmatch(r"(?:domain|range)\s*[:=]\s*(.+)", result, flags=re.IGNORECASE)
    if m:
        value = m.group(1).strip()
        value = re.sub(r"\s*\((?:specific|discrete|finite)\s+values?\)\s*$", "", value, flags=re.IGNORECASE)
        return value.strip()
    return result


def _extract_final_answer_block(out: str) -> str:
    text = str(out or "").strip()
    if not text:
        return ""

    lines = text.splitlines()
    start_idx = -1
    inline_text = ""
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.upper().startswith("FINAL ANSWER:"):
            start_idx = i
            inline_text = stripped[len("FINAL ANSWER:"):].strip()
            break
    if start_idx == -1:
        return ""

    parts = []
    if inline_text:
        parts.append(inline_text)
    for line in lines[start_idx + 1:]:
        s = line.strip()
        if s:
            parts.append(s)
    if not parts:
        return "FINAL ANSWER:"
    return "FINAL ANSWER:\n" + "\n".join(parts).strip()


def _clipboard_write_retry(text: str, attempts: int = 4, delay_sec: float = 0.08) -> bool:
    for _ in range(max(1, attempts)):
        if safe_clipboard_write(text):
            return True
        time.sleep(max(0.01, delay_sec))
    return False


def _normalize_final_answer_block(out: str) -> str:
    text = str(out or "").strip()
    if not text:
        return text

    lines = text.splitlines()
    normalized: List[str] = []
    found_final = False

    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("FINAL ANSWER:"):
            found_final = True
            inline = stripped[len("FINAL ANSWER:"):].strip()
            normalized.append("FINAL ANSWER:")
            if inline:
                normalized.append(inline)
            continue
        normalized.append(line)

    # Do not synthesize FINAL ANSWER when model omitted it; avoid duplicate/conflicting tails.
    if not found_final:
        return text

    return "\n".join(normalized).strip()


def _section_between(text: str, start_label: str, end_label: Optional[str] = None) -> str:
    s = str(text or "")
    m_start = re.search(rf"(?im)^\s*{re.escape(start_label)}\s*:?\s*$", s)
    if not m_start:
        return ""
    rest = s[m_start.end():]
    if not end_label:
        return rest.strip()
    m_end = re.search(rf"(?im)^\s*{re.escape(end_label)}\s*:?\s*$", rest)
    if not m_end:
        return rest.strip()
    return rest[: m_end.start()].strip()


def _looks_like_graph_text(text: str) -> bool:
    low = str(text or "").lower()
    return any(
        cue in low
        for cue in (
            "graph",
            "graphed",
            "domain",
            "range",
            "endpoint",
            "asymptote",
            "x-axis",
            "y-axis",
        )
    )


def _split_semicolon_values(value: str) -> List[str]:
    s = str(value or "").strip()
    if not s:
        return []
    low = s.lower()
    if low in ("none", "n/a", "na", "no", "no asymptotes", "no discontinuities"):
        return []
    if ";" in s:
        return [part.strip() for part in s.split(";") if part.strip()]
    return [s]


def _parse_graph_endpoint(raw_value: str) -> Optional[Dict[str, str]]:
    m = re.match(
        r"(?i)^\s*x\s*=\s*([^,]{1,120}?)\s*,\s*y\s*=\s*([^,]{1,120}?)\s*,\s*marker\s*=\s*(open|closed|arrow|unclear)\s*$",
        str(raw_value or ""),
    )
    if not m:
        return None
    return {
        "x": m.group(1).strip(),
        "y": m.group(2).strip(),
        "marker": m.group(3).strip().lower(),
    }


def _parse_graph_scale(raw_value: str) -> Optional[Dict[str, str]]:
    m = re.match(
        r"(?i)^\s*x_tick\s*=\s*([^,]{1,120}?)\s*,\s*y_tick\s*=\s*([^,]{1,120}?)\s*$",
        str(raw_value or ""),
    )
    if not m:
        return None
    return {
        "x_tick": m.group(1).strip(),
        "y_tick": m.group(2).strip(),
    }


def _extract_graph_evidence_block(text: str) -> Optional[Dict[str, Any]]:
    source = str(text or "")
    m_header = re.search(r"(?im)^\s*GRAPH_EVIDENCE\s*:\s*$", source)
    if not m_header:
        if _looks_like_graph_text(source):
            log_telemetry("graph_evidence_parse_fail", {"reason": "header_missing"})
        return None

    bounded_slice = source[m_header.end(): m_header.end() + 2000]
    required = ("LEFT_ENDPOINT", "RIGHT_ENDPOINT", "ASYMPTOTES", "DISCONTINUITIES", "SCALE", "CONFIDENCE")
    fields: Dict[str, str] = {}
    seen_any = False

    for raw_line in bounded_slice.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if seen_any:
                break
            continue
        if re.search(r"(?i)\b(WORK|FINAL ANSWER|\[FINAL\])\b", stripped):
            log_telemetry("graph_evidence_parse_fail", {"reason": "boundary_marker_in_block"})
            return None
        m_field = re.match(r"^\s*([A-Z_]+)\s*:\s*(.+?)\s*$", raw_line)
        if not m_field:
            if seen_any:
                break
            continue
        key = m_field.group(1).strip().upper()
        value = m_field.group(2).strip()
        if key in required:
            fields[key] = value
            seen_any = True
            if len(fields) == len(required):
                break
        elif seen_any:
            break

    missing = [k for k in required if k not in fields]
    if missing:
        log_telemetry("graph_evidence_parse_fail", {"reason": "missing_fields", "missing_fields": missing})
        return None

    left = _parse_graph_endpoint(fields["LEFT_ENDPOINT"])
    right = _parse_graph_endpoint(fields["RIGHT_ENDPOINT"])
    scale = _parse_graph_scale(fields["SCALE"])
    if left is None or right is None:
        log_telemetry("graph_evidence_parse_fail", {"reason": "invalid_endpoint_format"})
        return None
    if scale is None:
        log_telemetry("graph_evidence_parse_fail", {"reason": "invalid_scale_format"})
        return None

    try:
        confidence = float(fields["CONFIDENCE"])
    except Exception:
        log_telemetry("graph_evidence_parse_fail", {"reason": "invalid_confidence"})
        return None
    if confidence < 0.0 or confidence > 1.0:
        log_telemetry("graph_evidence_parse_fail", {"reason": "invalid_confidence"})
        return None

    return {
        "left_endpoint": left,
        "right_endpoint": right,
        "asymptotes": _split_semicolon_values(fields["ASYMPTOTES"]),
        "discontinuities": _split_semicolon_values(fields["DISCONTINUITIES"]),
        "scale": scale,
        "confidence": confidence,
    }


def _extract_interval_notation(value: str) -> Optional[Dict[str, Any]]:
    m = re.search(r"([\(\[])\s*([^,\[\]\(\)]+?)\s*,\s*([^,\[\]\(\)]+?)\s*([\)\]])", str(value or ""))
    if not m:
        return None
    lower = m.group(2).strip()
    upper = m.group(3).strip()
    return {
        "raw": m.group(0).strip(),
        "lower": lower,
        "upper": upper,
        "left_inclusive": m.group(1) == "[",
        "right_inclusive": m.group(4) == "]",
    }


def _extract_interval_for_label(text: str, label: str) -> Optional[Dict[str, Any]]:
    pattern = rf"(?im)^\s*{re.escape(label)}(?:\s*\([^)]+\))?\s*[:=]\s*([^\n\r]+)"
    m = re.search(pattern, str(text or ""))
    if not m:
        return None
    return _extract_interval_notation(m.group(1))


def _normalize_bound_token(token: str) -> str:
    return (
        str(token or "")
        .strip()
        .lower()
        .replace(" ", "")
        .replace("−", "-")
        .replace("âˆ’", "-")
        .replace("∞", "inf")
        .replace("âˆž", "inf")
    )


def _is_negative_infinity_token(token: str) -> bool:
    t = _normalize_bound_token(token)
    return t in ("-inf", "-infinity")


def _is_positive_infinity_token(token: str) -> bool:
    t = _normalize_bound_token(token)
    return t in ("inf", "+inf", "infinity", "+infinity")


def _token_to_float(token: str) -> Optional[float]:
    t = _normalize_bound_token(token)
    if not t or _is_negative_infinity_token(t) or _is_positive_infinity_token(t):
        return None
    try:
        if "/" in t:
            return float(Fraction(t))
        return float(t)
    except Exception:
        return None


def _interval_is_bounded(interval_obj: Dict[str, Any], side: str) -> bool:
    if side == "left":
        return not _is_negative_infinity_token(str(interval_obj.get("lower", "")))
    return not _is_positive_infinity_token(str(interval_obj.get("upper", "")))


def _interval_includes_value(interval_obj: Dict[str, Any], value_token: str) -> bool:
    value = _token_to_float(value_token)
    if value is None:
        return False

    lower_token = str(interval_obj.get("lower", ""))
    upper_token = str(interval_obj.get("upper", ""))
    lower = _token_to_float(lower_token)
    upper = _token_to_float(upper_token)
    eps = 1e-9

    if _interval_is_bounded(interval_obj, "left") and lower is not None:
        if value < lower - eps:
            return False
        if abs(value - lower) <= eps and not bool(interval_obj.get("left_inclusive", False)):
            return False

    if _interval_is_bounded(interval_obj, "right") and upper is not None:
        if value > upper + eps:
            return False
        if abs(value - upper) <= eps and not bool(interval_obj.get("right_inclusive", False)):
            return False

    return True


def _extract_domain_range_intervals(text: str) -> Dict[str, Optional[Dict[str, Any]]]:
    return {
        "domain": _extract_interval_for_label(text, "Domain"),
        "range": _extract_interval_for_label(text, "Range"),
    }


def _interval_signature(interval_obj: Dict[str, Any]) -> tuple[str, str, bool, bool]:
    return (
        _normalize_bound_token(str(interval_obj.get("lower", ""))),
        _normalize_bound_token(str(interval_obj.get("upper", ""))),
        bool(interval_obj.get("left_inclusive", False)),
        bool(interval_obj.get("right_inclusive", False)),
    )


def _collect_x_values(items: List[str]) -> List[str]:
    values: List[str] = []
    for item in items:
        for m in re.finditer(r"(?i)\bx\s*=\s*([+-]?(?:(?:\d+/\d+)|\d+(?:\.\d+)?))", str(item or "")):
            values.append(m.group(1).strip())
    return values


def _validate_work_final_consistency(
    parsed_evidence: Optional[Dict[str, Any]],
    work_text: str,
    final_text: str,
) -> List[Dict[str, Any]]:
    if not parsed_evidence:
        return []

    mismatches: List[Dict[str, Any]] = []
    work_intervals = _extract_domain_range_intervals(work_text)
    final_intervals = _extract_domain_range_intervals(final_text)
    final_domain = final_intervals.get("domain")
    work_domain = work_intervals.get("domain")
    work_range = work_intervals.get("range")
    final_range = final_intervals.get("range")

    left = parsed_evidence.get("left_endpoint", {}) or {}
    right = parsed_evidence.get("right_endpoint", {}) or {}
    left_marker = str(left.get("marker", "")).lower()
    right_marker = str(right.get("marker", "")).lower()

    if final_domain:
        if left_marker == "open" and bool(final_domain.get("left_inclusive", False)):
            mismatches.append({"mismatch_type": "endpoint_inclusion_conflict", "side": "left", "marker": "open"})
        if left_marker == "closed" and not bool(final_domain.get("left_inclusive", False)):
            mismatches.append({"mismatch_type": "endpoint_inclusion_conflict", "side": "left", "marker": "closed"})
        if right_marker == "open" and bool(final_domain.get("right_inclusive", False)):
            mismatches.append({"mismatch_type": "endpoint_inclusion_conflict", "side": "right", "marker": "open"})
        if right_marker == "closed" and not bool(final_domain.get("right_inclusive", False)):
            mismatches.append({"mismatch_type": "endpoint_inclusion_conflict", "side": "right", "marker": "closed"})
        if left_marker == "arrow" and _interval_is_bounded(final_domain, "left"):
            mismatches.append({"mismatch_type": "arrow_bound_conflict", "side": "left", "marker": "arrow"})
        if right_marker == "arrow" and _interval_is_bounded(final_domain, "right"):
            mismatches.append({"mismatch_type": "arrow_bound_conflict", "side": "right", "marker": "arrow"})

    for asym_x in _collect_x_values(list(parsed_evidence.get("asymptotes", []) or [])):
        if final_domain and _interval_includes_value(final_domain, asym_x):
            mismatches.append({"mismatch_type": "asymptote_inclusion_conflict", "x": asym_x})

    if work_domain and final_domain and _interval_signature(work_domain) != _interval_signature(final_domain):
        mismatches.append(
            {
                "mismatch_type": "interval_disagreement_domain",
                "work_interval": str(work_domain.get("raw", "")),
                "final_interval": str(final_domain.get("raw", "")),
            }
        )
    if work_range and final_range and _interval_signature(work_range) != _interval_signature(final_range):
        mismatches.append(
            {
                "mismatch_type": "interval_disagreement_range",
                "work_interval": str(work_range.get("raw", "")),
                "final_interval": str(final_range.get("raw", "")),
            }
        )
    return mismatches


def _needs_graph_domain_range_retry(input_obj: Union[str, Image.Image], model_text: str) -> bool:
    # Only apply this guard to image graph problems with domain/range outputs.
    if not isinstance(input_obj, Image.Image):
        return False
    t = str(model_text or "")
    low = t.lower()
    if "domain" not in low or "range" not in low:
        return False
    if "graph" not in low and "graphed below" not in low:
        return False

    final_text = _section_between(t, "FINAL ANSWER")
    work_text = _section_between(t, "WORK", "FINAL ANSWER")
    final_low = final_text.lower()
    work_low = work_text.lower()

    mentions_exclusion = any(k in final_low for k in ("excluding", "not included", "open", "hole"))
    if not mentions_exclusion:
        return False

    marker_evidence = any(
        k in work_low
        for k in (
            "open circle",
            "open endpoint",
            "hollow",
            "filled point",
            "closed point",
            "solid point",
        )
    )
    if mentions_exclusion and not marker_evidence:
        return True

    # Retry when final claims all-reals but WORK describes bounded graph features.
    final_all_reals = (
        bool(re.search(r"domain[^\n\r]*(all real numbers|\(-∞,\s*∞\)|\(-inf,\s*inf\))", final_low))
        or bool(re.search(r"range[^\n\r]*(all real numbers|\(-∞,\s*∞\)|\(-inf,\s*inf\))", final_low))
    )
    bounded_cues = any(
        k in work_low
        for k in (
            "starts at x",
            "ends at x",
            "from x",
            "to x",
            "maximum",
            "minimum",
            "open circle",
            "closed circle",
            "endpoint",
        )
    )
    arrow_evidence = "arrow" in work_low or "arrow" in final_low
    return final_all_reals and bounded_cues and not arrow_evidence


def _with_graph_domain_range_retry_hint(payload: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hint = (
        "Re-check graph domain/range carefully. "
        "List visible endpoints and marker types first (filled/open), "
        "then compute intervals from the plotted curve extent only. "
        "Do not use axis bounds unless the graph actually reaches them."
    )
    retry_payload = list(payload)
    if len(retry_payload) < 2:
        return retry_payload
    user_msg = dict(retry_payload[1])
    content = list(user_msg.get("content", []))
    content.append({"type": "input_text", "text": hint})
    user_msg["content"] = content
    retry_payload[1] = user_msg
    return retry_payload


def _format_fraction(fr: Fraction) -> str:
    if fr.denominator == 1:
        return str(fr.numerator)
    return f"{fr.numerator}/{fr.denominator}"


def _parse_linear_rhs(rhs: str) -> Optional[tuple[Fraction, Fraction]]:
    expr = str(rhs or "").strip().lower().replace(" ", "")
    expr = expr.rstrip(".")
    if not expr:
        return None

    # y = x / y = -x
    if expr == "x":
        return Fraction(1), Fraction(0)
    if expr == "-x":
        return Fraction(-1), Fraction(0)

    # y = mx + b, with optional b and optional explicit m (e.g., x, -x, 3x, -1/3x+3)
    m = re.fullmatch(r"([+-]?(?:(?:\d+/\d+)|\d+)?)x(?:([+-](?:(?:\d+/\d+)|\d+)))?", expr)
    if m:
        m_raw = m.group(1)
        b_raw = m.group(2)
        if m_raw in ("", "+"):
            slope = Fraction(1)
        elif m_raw == "-":
            slope = Fraction(-1)
        else:
            slope = Fraction(m_raw)
        intercept = Fraction(b_raw) if b_raw else Fraction(0)
        return slope, intercept

    # Horizontal line y = c
    c = re.fullmatch(r"([+-]?(?:(?:\d+/\d+)|\d+))", expr)
    if c:
        return Fraction(0), Fraction(c.group(1))

    return None


def _maybe_enforce_points_to_plot(out: str) -> str:
    lower = out.lower()
    graph_cues = (
        "graph the equation",
        "table of values",
        "graph k(x)",
        "graph f(x)",
        "graph y",
    )
    if not any(cue in lower for cue in graph_cues):
        return out
    if "points to plot:" in lower:
        return out

    eq_match = re.search(r"(?:\b[a-z]\s*\(\s*x\s*\)|\by)\s*=\s*([^\n\r]+)", out, flags=re.IGNORECASE)
    if not eq_match:
        return out
    parsed = _parse_linear_rhs(eq_match.group(1))
    if parsed is None:
        return out
    slope, intercept = parsed

    x_vals = [Fraction(-3), Fraction(0), Fraction(3)]
    points = []
    for x in x_vals:
        y = slope * x + intercept
        points.append(f"({_format_fraction(x)}, {_format_fraction(y)})")
    points_line = f"Points to plot: {', '.join(points)}"

    if "FINAL ANSWER:" in out:
        head, _sep, _tail = out.partition("FINAL ANSWER:")
        if "WORK:" in head and "Points to plot:" not in head:
            head = head.rstrip() + "\n" + points_line + "\n"
        return head + "FINAL ANSWER:\n" + ", ".join(points)

    return out.rstrip() + "\nWORK:\n" + points_line + "\nFINAL ANSWER:\n" + ", ".join(points)


def _maybe_enforce_domain_range_intervals(out: str) -> str:
    lower = out.lower()
    if "domain" not in lower and "range" not in lower:
        return out

    # Only canonicalize from FINAL ANSWER content, not WORK, to avoid false rewrites.
    final_text = _section_between(out, "FINAL ANSWER")
    if not final_text:
        return out
    final_lines = [ln.strip() for ln in final_text.splitlines() if ln.strip()]
    if not final_lines:
        return out

    any_rewrite = False
    rewritten_lines: List[str] = []
    for line in final_lines:
        low = line.lower()
        domain_all_reals = bool(
            re.search(r"domain[^\n\r]*(all real numbers|\(-∞,\s*∞\)|\(-inf,\s*inf\))", low, flags=re.IGNORECASE)
        )
        range_all_reals = bool(
            re.search(r"range[^\n\r]*(all real numbers|\(-∞,\s*∞\)|\(-inf,\s*inf\))", low, flags=re.IGNORECASE)
        )
        if domain_all_reals:
            rewritten_lines.append("Domain: (-∞, ∞) (All Real Numbers)")
            any_rewrite = True
            continue
        if range_all_reals:
            rewritten_lines.append("Range: (-∞, ∞) (All Real Numbers)")
            any_rewrite = True
            continue
        rewritten_lines.append(line)

    if not any_rewrite:
        return out

    rebuilt_final = "\n".join(rewritten_lines)
    if "FINAL ANSWER:" in out:
        head, _sep, _tail = out.partition("FINAL ANSWER:")
        return head.rstrip() + "\nFINAL ANSWER:\n" + rebuilt_final
    return out.rstrip() + "\nFINAL ANSWER:\n" + rebuilt_final


def _maybe_compact_discrete_domain_range(out: str) -> str:
    # For finite-set table answers, keep FINAL ANSWER concise (no extra qualifiers).
    return re.sub(
        r"(?im)^(\s*(?:domain|range)\s*:\s*\{[^{}\n]+\})\s*\((?:specific|discrete|finite)\s+values?\)\s*$",
        r"\1",
        out,
    )


def solve_pipeline(
    client: OpenAI,
    input_obj: Union[str, Image.Image],
    cancel_event: Optional[Any] = None,
    request_id: Optional[str] = None,
) -> None:
    solve_request_id = str(request_id or f"solve-{uuid.uuid4().hex[:10]}")

    def _is_cancelled() -> bool:
        return bool(cancel_event is not None and getattr(cancel_event, "is_set", lambda: False)())

    if _is_cancelled():
        log_telemetry("solve_cancelled", {"request_id": solve_request_id, "stage": "start"})
        return

    cfg = get_config()
    retries = int(cfg.get("retries", 1))
    timeout = int(cfg.get("request_timeout", 25))
    model_name = str(cfg.get("model", MODEL) or MODEL).strip() or MODEL
    if _is_gpt5_family_model(model_name):
        adjusted_timeout = max(timeout, 35)
        if adjusted_timeout != timeout:
            log_telemetry(
                "model_timeout_adjusted",
                {"request_id": solve_request_id, "model": model_name, "configured": timeout, "effective": adjusted_timeout},
            )
        timeout = adjusted_timeout
    temperature = float(cfg.get("temperature", 0.0))
    max_output_tokens = int(cfg.get("max_output_tokens", 2200))
    enable_graph_evidence_parsing = bool(cfg.get("ENABLE_GRAPH_EVIDENCE_PARSING", False))
    enable_consistency_warnings = bool(cfg.get("ENABLE_CONSISTENCY_WARNINGS", False))
    enable_consistency_blocking = bool(cfg.get("ENABLE_CONSISTENCY_BLOCKING", False))
    log_telemetry(
        "solve_request_start",
        {
            "request_id": solve_request_id,
            "model": model_name,
            "timeout_sec": timeout,
            "retries": retries,
            "max_output_tokens": max_output_tokens,
        },
    )

    meta = load_starred_meta()
    reference_active = bool(meta.get("reference_active", False))
    reference_type = meta.get("reference_type")
    reference_summary = preview_text(str(meta.get("reference_summary", "") or ""), 140)
    graph_mode = bool(meta.get("graph_mode", False))
    graph_evidence_text = str(meta.get("graph_evidence") or "").strip()
    _set_reference_indicator_from_meta(meta)
    reference_text = ""
    reference_img_b64 = ""

    if reference_active:
        if reference_type == REFERENCE_TYPE_TEXT:
            tp = str(meta.get("text_path", "") or "")
            if not tp or not os.path.exists(tp):
                _clear_reference(meta)
                save_starred_meta(meta)
                _set_reference_indicator_from_meta(meta)
                set_status("REF invalid: missing TEXT source. REF CLEARED")
                return
            try:
                with open(tp, "r", encoding="utf-8") as f:
                    reference_text = f.read().strip()
            except Exception as e:
                log_telemetry("ref_text_read_error", {"error": str(e)})
                _clear_reference(meta)
                save_starred_meta(meta)
                _set_reference_indicator_from_meta(meta)
                set_status(f"REF invalid: TEXT read failed. REF CLEARED. Error: {e}")
                return
            if not reference_text:
                _clear_reference(meta)
                save_starred_meta(meta)
                _set_reference_indicator_from_meta(meta)
                set_status("REF invalid: empty TEXT source. REF CLEARED")
                return
            if not reference_summary:
                reference_summary = preview_text(reference_text, 140)
        elif reference_type == REFERENCE_TYPE_IMG:
            ip = str(meta.get("image_path", "") or "")
            if not ip or not os.path.exists(ip):
                _clear_reference(meta)
                save_starred_meta(meta)
                _set_reference_indicator_from_meta(meta)
                set_status("REF invalid: missing IMG source. REF CLEARED")
                return
            try:
                with Image.open(ip) as im:
                    im = normalize_image_for_api(im.convert("RGB"), cfg)
                    reference_img_b64 = image_to_base64_png(im)
            except Exception as e:
                log_telemetry("ref_image_read_error", {"error": str(e)})
                _clear_reference(meta)
                save_starred_meta(meta)
                _set_reference_indicator_from_meta(meta)
                set_status(f"REF invalid: IMG read failed. REF CLEARED. Error: {e}")
                return
        else:
            _clear_reference(meta)
            save_starred_meta(meta)
            _set_reference_indicator_from_meta(meta)
            set_status("REF invalid: unknown reference type. REF CLEARED")
            return

    if isinstance(input_obj, Image.Image):
        input_obj = normalize_image_for_api(input_obj, cfg)

    graph_evidence_active = bool(graph_mode and _is_valid_graph_evidence_text(graph_evidence_text))
    if graph_mode and graph_evidence_text and not graph_evidence_active:
        log_telemetry("graph_evidence_inactive", {"request_id": solve_request_id, "reason": "invalid_or_absent"})

    payload = _build_solve_payload(
        input_obj=input_obj,
        reference_active=reference_active,
        reference_type=reference_type,
        reference_text=reference_text,
        reference_img_b64=reference_img_b64,
        graph_mode=graph_mode,
        graph_evidence_text=graph_evidence_text if graph_evidence_active else None,
        enable_graph_evidence_parsing=enable_graph_evidence_parsing,
    )
    payload_has_image = False
    try:
        user_content = payload[1].get("content", []) if len(payload) > 1 and isinstance(payload[1], dict) else []
        payload_has_image = any(
            isinstance(part, dict) and str(part.get("type", "")).strip().lower() == "input_image"
            for part in user_content
        )
    except Exception:
        payload_has_image = False

    image_width: Optional[int] = None
    image_height: Optional[int] = None
    image_pixel_count: Optional[int] = None
    if isinstance(input_obj, Image.Image):
        try:
            image_width, image_height = input_obj.size
            image_pixel_count = int(image_width) * int(image_height)
        except Exception:
            image_width = None
            image_height = None
            image_pixel_count = None
    log_telemetry(
        "solve_image_metadata",
        {
            "request_id": solve_request_id,
            "model": model_name,
            "input_is_image": isinstance(input_obj, Image.Image),
            "width": image_width,
            "height": image_height,
            "pixel_count": image_pixel_count,
            "reference_image_included": bool(reference_active and reference_type == REFERENCE_TYPE_IMG and reference_img_b64),
            "graph_mode": graph_mode,
            "graph_evidence_included": graph_evidence_active,
        },
    )

    raw_output = ""
    parsed_graph_evidence: Optional[Dict[str, Any]] = None
    for attempt in range(retries + 1):
        if _is_cancelled():
            log_telemetry("solve_cancelled", {"request_id": solve_request_id, "stage": "pre_request", "attempt": attempt + 1})
            set_status("Solve canceled: model switched.")
            return
        try:
            candidate = _responses_text(
                client=client,
                model_name=model_name,
                input_payload=payload,
                timeout=timeout,
                temperature=temperature,
                max_output_tokens=max(16, int(max_output_tokens)),
                flow_name="solve_main",
                request_id=f"{solve_request_id}-main-{attempt + 1}",
            )
            if enable_graph_evidence_parsing:
                parsed_graph_evidence = _extract_graph_evidence_block(candidate)
            # Graph retry is intentionally disabled:
            # if _needs_graph_domain_range_retry(input_obj, candidate):
            #     retry_payload = _with_graph_domain_range_retry_hint(payload)
            #     log_telemetry(
            #         "solve_retry_metadata",
            #         {
            #             "request_id": solve_request_id,
            #             "attempt": attempt + 1,
            #             "retry_mode": "with_image",
            #             "retry_reason": "graph_domain_range_weak_marker_evidence",
            #         },
            #     )
            #     log_telemetry("graph_domain_range_retry", {"attempt": attempt + 1, "reason": "weak_marker_evidence"})
            #     retry_output = _responses_text(
            #         client=client,
            #         model_name=model_name,
            #         input_payload=retry_payload,
            #         timeout=timeout,
            #         temperature=temperature,
            #         max_output_tokens=max(16, int(max_output_tokens)),
            #         flow_name="solve_graph_retry",
            #         request_id=f"{solve_request_id}-graph-{attempt + 1}",
            #     )
            #     if retry_output:
            #         candidate = retry_output
            #         if enable_graph_evidence_parsing:
            #             parsed_graph_evidence = _extract_graph_evidence_block(candidate)

            if candidate and candidate.strip():
                raw_output = candidate
                break

            log_telemetry("solve_empty_response_retry", {"attempt": attempt + 1, "model": str(model_name)})
            if attempt == retries:
                log_telemetry("solve_request_failed", {"request_id": solve_request_id, "reason": "empty_response"})
                set_status("Empty model response.")
                return
            log_telemetry(
                "solve_retry_metadata",
                {
                    "request_id": solve_request_id,
                    "attempt": attempt + 1,
                    "retry_mode": "with_image" if payload_has_image else "text_only",
                    "retry_reason": "empty_response",
                },
            )
        except Exception as e:
            if _is_cancelled():
                log_telemetry(
                    "solve_cancelled",
                    {"request_id": solve_request_id, "stage": "exception", "attempt": attempt + 1, "error": str(e)},
                )
                set_status("Solve canceled: model switched.")
                return
            log_telemetry("solve_retry", {"attempt": attempt + 1, "error": str(e)})
            if attempt == retries:
                log_telemetry("solve_request_failed", {"request_id": solve_request_id, "reason": "exception", "error": str(e)})
                set_status(f"Solve failed: {e}")
                return
            log_telemetry(
                "solve_retry_metadata",
                {
                    "request_id": solve_request_id,
                    "attempt": attempt + 1,
                    "retry_mode": "with_image" if payload_has_image else "text_only",
                    "retry_reason": "exception",
                },
            )

    if _is_cancelled():
        log_telemetry("solve_cancelled", {"request_id": solve_request_id, "stage": "post_request"})
        set_status("Solve canceled: model switched.")
        return

    out = clean_output(apply_safe_symbols(raw_output)).strip()
    # Normalize inline FINAL ANSWER first so downstream section checks are stable.
    out = _normalize_final_answer_block(out)
    out = _maybe_enforce_points_to_plot(out)
    out = _maybe_enforce_domain_range_intervals(out)
    out = _maybe_compact_discrete_domain_range(out)
    if not out:
        set_status("Model returned empty output.")
        return

    ref_prefix = ""
    if reference_active and reference_type in (REFERENCE_TYPE_IMG, REFERENCE_TYPE_TEXT):
        effective_summary = reference_summary
        if not effective_summary:
            effective_summary = "visual reference" if reference_type == REFERENCE_TYPE_IMG else "text reference"
        ref_prefix = f"* REF {reference_type}: {effective_summary}"
        out = f"{ref_prefix}\n{out}"

    final_text = _extract_final_answer_text(out)
    if enable_consistency_warnings and parsed_graph_evidence is not None:
        work_text = _section_between(out, "WORK", "FINAL ANSWER")
        final_section = _section_between(out, "FINAL ANSWER")
        mismatches = _validate_work_final_consistency(parsed_graph_evidence, work_text, final_section)
        for mismatch in mismatches:
            payload = {
                "request_id": solve_request_id,
                "model": model_name,
                "confidence": parsed_graph_evidence.get("confidence"),
            }
            payload.update(mismatch)
            log_telemetry("validator_mismatch_warning", payload)
        if mismatches and enable_consistency_blocking:
            # Phase 1 is warning-only even when the future blocking flag is set.
            log_telemetry(
                "validator_blocking_phase1_noop",
                {"request_id": solve_request_id, "model": model_name, "mismatch_count": len(mismatches)},
            )
    if final_text and ref_prefix:
        # Keep parsed answer first so users see result immediately; append REF context at the bottom.
        final_text = f"{final_text}\n{ref_prefix}"

    if _is_cancelled():
        log_telemetry("solve_cancelled", {"request_id": solve_request_id, "stage": "pre_clipboard"})
        set_status("Solve canceled: model switched.")
        return

    if final_text:
        # Entry 1: original full result. Entry 2: parsed final-answer text (no header).
        settle_sec = float(cfg.get("clipboard_history_settle_sec", 0.6))
        wrote_full = _clipboard_write_retry(out)
        if _is_cancelled():
            log_telemetry("solve_cancelled", {"request_id": solve_request_id, "stage": "between_clipboard_writes"})
            set_status("Solve canceled: model switched.")
            return
        if wrote_full:
            time.sleep(max(0.25, settle_sec))
        if _is_cancelled():
            log_telemetry("solve_cancelled", {"request_id": solve_request_id, "stage": "pre_final_clipboard"})
            set_status("Solve canceled: model switched.")
            return
        wrote_final = _clipboard_write_retry(final_text)
        ok = wrote_full and wrote_final
    else:
        ok = _clipboard_write_retry(out)
    if ok:
        mark_prompt_success()
        log_telemetry("solve_request_complete", {"request_id": solve_request_id, "model": model_name})
    notify_on_complete = bool(cfg.get("notify_on_complete", False))
    if ok and notify_on_complete:
        set_status("Solved → copied to clipboard")
    elif not ok:
        set_status("Solved, but failed to write clipboard")


def toggle_star_worker(client: OpenAI) -> None:
    cfg = get_config()
    model_name = str(cfg.get("model", MODEL) or MODEL).strip() or MODEL
    reference_helper_model = str(cfg.get("reference_summary_model", "gpt-4o-mini") or "").strip() or "gpt-4o-mini"
    ref_model = reference_helper_model if _is_gpt5_family_model(model_name) else model_name
    meta = load_starred_meta()
    graph_mode = bool(meta.get("graph_mode", False))

    # Strict toggle behavior: active -> clear only (no parse/overwrite in same action).
    if bool(meta.get("reference_active", False)):
        _clear_reference(meta)
        save_starred_meta(meta)
        _set_reference_indicator_from_meta(meta)
        set_status("REF CLEARED")
        return

    # Explicit status check before assigning a new reference.
    if not _can_assign_reference(meta):
        return

    raw_clip, err = safe_clipboard_read()
    if err is not None:
        log_telemetry("star_clipboard_read_error", {"error": str(err)})

    # Graph mode path: next REF prime must be treated as graph image.
    if graph_mode:
        if not isinstance(raw_clip, Image.Image):
            set_status("Graph Mode ON: copy a graph image before priming REF.")
            return
        try:
            img = normalize_image_for_api(raw_clip, cfg)
            img_b64 = image_to_base64_png(img)
            img_dir = _starred_base_dir()
            img_path = os.path.join(img_dir, STARRED_IMG_FILE)
            img.save(img_path, format="PNG")
            summary = _summarize_visual_reference(
                client=client,
                model_name=ref_model,
                img_b64=img_b64,
                timeout=int(cfg.get("classify_timeout", 8)),
            ) or "graph reference"

            meta.update({
                "reference_active": True,
                "reference_type": REFERENCE_TYPE_IMG,
                "text_path": "",
                "image_path": img_path,
                "reference_summary": summary,
            })
            set_status("Graph Mode ON: extracting graph evidence...")
            graph_evidence = extract_graph_evidence(
                image_path=img_path,
                client=client,
                model_name=GRAPH_EVIDENCE_EXTRACTION_MODEL,
                timeout=int(cfg.get("ocr_timeout", 12)),
            )
            meta["graph_evidence"] = graph_evidence
            meta["last_primed_ts"] = int(time.time())
            save_starred_meta(meta)
            _set_reference_indicator_from_meta(meta)
            log_telemetry(
                "graph_mode_ref_primed",
                {
                    "evidence_valid": _is_valid_graph_evidence_text(graph_evidence),
                    "summary_length": len(summary),
                    "extraction_model": GRAPH_EVIDENCE_EXTRACTION_MODEL,
                },
            )
            if _is_valid_graph_evidence_text(graph_evidence):
                set_status(f"* REF {REFERENCE_TYPE_IMG}: {summary} | GRAPH EVIDENCE READY")
            else:
                set_status(f"* REF {REFERENCE_TYPE_IMG}: {summary} | GRAPH EVIDENCE INVALID (fallback enabled)")
            return
        except Exception as e:
            log_telemetry("graph_mode_prime_error", {"error": str(e)})
            set_status(f"Graph mode prime failed: {e}")
            return

    # image case
    if isinstance(raw_clip, Image.Image):
        try:
            img = normalize_image_for_api(raw_clip, cfg)
            img_b64 = image_to_base64_png(img)

            classify_payload = [
                {"role": "system", "content": [{"type": "input_text", "text": STAR_CLASSIFY_PROMPT}]},
                {"role": "user", "content": [{"type": "input_image", "image_url": f"data:image/png;base64,{img_b64}"}]},
            ]
            label_raw = _responses_text(
                client=client,
                model_name=ref_model,
                input_payload=classify_payload,
                timeout=int(cfg.get("classify_timeout", 8)),
                temperature=0.0,
                max_output_tokens=32,
                flow_name="ref_classify",
            ).strip()
            label = _normalize_star_label(label_raw)

            # Fallback 1: retry classifier with a stable vision model if primary label is empty/ambiguous.
            if not label:
                fallback_model = str(cfg.get("reference_classifier_model", "gpt-4o-mini") or "").strip()
                if fallback_model and fallback_model != ref_model:
                    try:
                        fallback_raw = _responses_text(
                            client=client,
                            model_name=fallback_model,
                            input_payload=classify_payload,
                            timeout=int(cfg.get("classify_timeout", 8)),
                            temperature=0.0,
                            max_output_tokens=32,
                            flow_name="ref_classify_fallback",
                        ).strip()
                        label = _normalize_star_label(fallback_raw)
                        if label:
                            log_telemetry(
                                "ref_classifier_fallback_model",
                                {"primary_model": model_name, "fallback_model": fallback_model, "label": label},
                            )
                    except Exception as e:
                        # Continue to OCR fallback instead of aborting REF assignment.
                        log_telemetry(
                            "ref_classifier_fallback_error",
                            {"primary_model": model_name, "fallback_model": fallback_model, "error": str(e)},
                        )

            # Fallback 2: never fail as EMPTY; infer from OCR availability.
            ocr_text_fallback = ""
            if not label:
                ocr_probe_img = preprocess_for_ocr(img)
                ocr_probe_b64 = image_to_base64_png(ocr_probe_img)
                ocr_probe_payload = [
                    {"role": "system", "content": [{"type": "input_text", "text": STAR_OCR_PROMPT}]},
                    {"role": "user", "content": [{"type": "input_image", "image_url": f"data:image/png;base64,{ocr_probe_b64}"}]},
                ]
                ocr_text_fallback = _responses_text(
                    client=client,
                    model_name=ref_model,
                    input_payload=ocr_probe_payload,
                    timeout=int(cfg.get("ocr_timeout", 12)),
                    temperature=0.0,
                    max_output_tokens=1200,
                    flow_name="ref_ocr_probe",
                ).strip()
                label = "TEXTUAL" if ocr_text_fallback else "VISUAL"
                log_telemetry("ref_classifier_empty_fallback", {"resolved_label": label, "model": model_name})

            if label == "TEXTUAL":
                if ocr_text_fallback:
                    ocr_text = ocr_text_fallback
                else:
                    ocr_img = preprocess_for_ocr(img)
                    ocr_b64 = image_to_base64_png(ocr_img)
                    ocr_payload = [
                        {"role": "system", "content": [{"type": "input_text", "text": STAR_OCR_PROMPT}]},
                        {"role": "user", "content": [{"type": "input_image", "image_url": f"data:image/png;base64,{ocr_b64}"}]},
                    ]
                    ocr_text = _responses_text(
                        client=client,
                        model_name=ref_model,
                        input_payload=ocr_payload,
                        timeout=int(cfg.get("ocr_timeout", 12)),
                        temperature=0.0,
                        max_output_tokens=1200,
                        flow_name="ref_ocr",
                    ).strip()
                if not ocr_text:
                    set_status("REF assign failed: OCR returned empty text")
                    return

                text_path = os.path.join(app_home_dir(), STARRED_TEXT_FILE)
                with open(text_path, "w", encoding="utf-8") as f:
                    f.write(ocr_text)
                summary = preview_text(ocr_text, 140) or "text reference"

                meta.update({
                    "reference_active": True,
                    "reference_type": REFERENCE_TYPE_TEXT,
                    "text_path": text_path,
                    "image_path": "",
                    "reference_summary": summary,
                    "graph_evidence": None,
                    "last_primed_ts": 0,
                })
                save_starred_meta(meta)
                _set_reference_indicator_from_meta(meta)
                log_telemetry("ref_set", {"type": REFERENCE_TYPE_TEXT, "summary_length": len(summary)})
                set_status(f"* REF {REFERENCE_TYPE_TEXT}: {summary}")
            elif label == "VISUAL":
                img_dir = _starred_base_dir()
                img_path = os.path.join(img_dir, STARRED_IMG_FILE)
                img.save(img_path, format="PNG")
                summary = _summarize_visual_reference(
                    client=client,
                    model_name=ref_model,
                    img_b64=img_b64,
                    timeout=int(cfg.get("classify_timeout", 8)),
                )

                if not summary:
                    fallback_summary_model = str(cfg.get("reference_summary_model", "gpt-4o-mini") or "").strip()
                    if fallback_summary_model and fallback_summary_model != model_name:
                        summary = _summarize_visual_reference(
                            client=client,
                            model_name=fallback_summary_model,
                            img_b64=img_b64,
                            timeout=int(cfg.get("classify_timeout", 8)),
                        )
                        if summary:
                            log_telemetry(
                                "ref_summary_fallback_model",
                                {"primary_model": model_name, "fallback_model": fallback_summary_model},
                            )

                if not summary:
                    ocr_probe_img = preprocess_for_ocr(img)
                    ocr_probe_b64 = image_to_base64_png(ocr_probe_img)
                    ocr_probe_payload = [
                        {"role": "system", "content": [{"type": "input_text", "text": STAR_OCR_PROMPT}]},
                        {"role": "user", "content": [{"type": "input_image", "image_url": f"data:image/png;base64,{ocr_probe_b64}"}]},
                    ]
                    try:
                        ocr_probe_text = _responses_text(
                            client=client,
                            model_name=model_name,
                            input_payload=ocr_probe_payload,
                            timeout=int(cfg.get("ocr_timeout", 12)),
                            temperature=0.0,
                            max_output_tokens=600,
                        ).strip()
                    except Exception as e:
                        log_telemetry("ref_summary_ocr_probe_error", {"error": str(e)})
                        ocr_probe_text = ""
                    summary = _guess_visual_summary_from_ocr_text(ocr_probe_text)

                summary = summary or "visual reference"

                meta.update({
                    "reference_active": True,
                    "reference_type": REFERENCE_TYPE_IMG,
                    "text_path": "",
                    "image_path": img_path,
                    "reference_summary": summary,
                    "graph_evidence": None,
                    "last_primed_ts": 0,
                })
                save_starred_meta(meta)
                _set_reference_indicator_from_meta(meta)
                log_telemetry("ref_set", {"type": REFERENCE_TYPE_IMG, "summary_length": len(summary)})
                set_status(f"* REF {REFERENCE_TYPE_IMG}: {summary}")
            else:
                # Guard path should be unreachable due fallback logic above.
                set_status(f"REF assign failed: classifier returned '{label_raw or 'EMPTY'}'")
            return
        except Exception as e:
            log_telemetry("star_image_error", {"error": str(e)})
            set_status(f"STAR failed: {e}")
            return

    # text case
    try:
        text = (pyperclip.paste() or "").strip()
    except Exception:
        text = ""

    if text:
        text_path = os.path.join(app_home_dir(), STARRED_TEXT_FILE)
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text)
        summary = preview_text(text, 140) or "text reference"
        meta.update({
            "reference_active": True,
            "reference_type": REFERENCE_TYPE_TEXT,
            "text_path": text_path,
            "image_path": "",
            "reference_summary": summary,
            "graph_evidence": None,
            "last_primed_ts": 0,
        })
        save_starred_meta(meta)
        _set_reference_indicator_from_meta(meta)
        log_telemetry("ref_set", {"type": REFERENCE_TYPE_TEXT, "summary_length": len(summary)})
        set_status(f"* REF {REFERENCE_TYPE_TEXT}: {summary}")
    else:
        set_status("REF assign failed: no image/text in clipboard")
