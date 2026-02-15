import os
import io
import json
import base64
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
    "Output MUST be plain text only. No markdown. No LaTeX.\n"
    "Use this exact structure:\n"
    "<raw math only, no label>\n"
    "WORK:\n"
    "<minimal symbolic steps>\n"
    "FINAL ANSWER: <answer>\n"
    "Rules:\n"
    "- Do not include 'DETECTED_INPUT:' or 'Q:'.\n"
    "- First line must be only the detected expression/equation.\n"
    "- Keep WORK concise.\n"
    "- For inequalities, final should be interval notation.\n"
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

STARRED_CONTEXT_GUIDE = "Use the STARRED reference context below as high-priority background.\nThen solve only the current problem.\n"


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
    }


def _normalize_reference_meta(raw_meta: Dict[str, Any]) -> Dict[str, Any]:
    meta = dict(raw_meta or {})
    reference_active = bool(meta.get("reference_active", False))
    reference_type = meta.get("reference_type")
    reference_summary = str(meta.get("reference_summary", "") or "")

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

    return {
        "reference_active": reference_active,
        "reference_type": reference_type,
        "text_path": str(meta.get("text_path", "") or ""),
        "image_path": str(meta.get("image_path", "") or ""),
        "reference_summary": reference_summary,
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
    })
    return meta


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

    set_reference_active(False)
    log_telemetry("ref_clear", {"source": source})
    if status_message:
        set_status(status_message)


def preview_text(text: str, max_chars: int = 140) -> str:
    normalized = " ".join(str(text or "").split())
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


def _responses_text(
    client: OpenAI,
    model_name: str,
    input_payload: List[Dict[str, Any]],
    timeout: int,
    temperature: float,
    max_output_tokens: int,
) -> str:
    resp = client.responses.create(
        model=model_name,
        input=input_payload,
        temperature=temperature,
        max_output_tokens=max(16, int(max_output_tokens)),
        timeout=timeout,
    )
    text = getattr(resp, "output_text", None)
    if text:
        return text

    pieces = []
    try:
        for out_item in resp.output:
            if getattr(out_item, "type", "") == "message":
                for c in getattr(out_item, "content", []):
                    if getattr(c, "type", "") == "output_text":
                        pieces.append(c.text)
    except Exception:
        pass
    return "\n".join(pieces).strip()


def _build_solve_payload(
    input_obj: Union[str, Image.Image],
    reference_active: bool,
    reference_type: Optional[str],
    reference_text: str,
    reference_img_b64: str
) -> List[Dict[str, Any]]:
    sys_msg = {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]}
    user_parts = []

    if isinstance(input_obj, Image.Image):
        cur_b64 = image_to_base64_png(input_obj)
        if reference_active and reference_type == REFERENCE_TYPE_IMG and reference_img_b64:
            user_parts.append({"type": "input_text", "text": STARRED_CONTEXT_GUIDE + "Reference image first, current image second."})
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{reference_img_b64}"})
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{cur_b64}"})
        elif reference_active and reference_type == REFERENCE_TYPE_TEXT and reference_text:
            user_parts.append({"type": "input_text", "text": STARRED_CONTEXT_GUIDE + f"STARRED TEXT:\n{reference_text}\n\nNow solve current image."})
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{cur_b64}"})
        else:
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{cur_b64}"})
    else:
        cur_text = str(input_obj)
        if reference_active and reference_type == REFERENCE_TYPE_IMG and reference_img_b64:
            user_parts.append({"type": "input_text", "text": STARRED_CONTEXT_GUIDE + f"CURRENT PROBLEM:\n{cur_text}"})
            user_parts.append({"type": "input_image", "image_url": f"data:image/png;base64,{reference_img_b64}"})
        elif reference_active and reference_type == REFERENCE_TYPE_TEXT and reference_text:
            merged = STARRED_CONTEXT_GUIDE + f"STARRED TEXT:\n{reference_text}\n\nCURRENT PROBLEM:\n{cur_text}"
            user_parts.append({"type": "input_text", "text": merged})
        else:
            user_parts.append({"type": "input_text", "text": cur_text})

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


def solve_pipeline(client: OpenAI, input_obj: Union[str, Image.Image]) -> None:
    cfg = get_config()
    retries = int(cfg.get("retries", 1))
    timeout = int(cfg.get("request_timeout", 25))
    model_name = cfg.get("model", MODEL)
    temperature = float(cfg.get("temperature", 0.0))
    max_output_tokens = int(cfg.get("max_output_tokens", 2200))

    meta = load_starred_meta()
    reference_active = bool(meta.get("reference_active", False))
    reference_type = meta.get("reference_type")
    reference_summary = preview_text(str(meta.get("reference_summary", "") or ""), 140)
    set_reference_active(reference_active)
    reference_text = ""
    reference_img_b64 = ""

    if reference_active:
        if reference_type == REFERENCE_TYPE_TEXT:
            tp = str(meta.get("text_path", "") or "")
            if not tp or not os.path.exists(tp):
                _clear_reference(meta)
                save_starred_meta(meta)
                set_reference_active(False)
                set_status("REF invalid: missing TEXT source. REF CLEARED")
                return
            try:
                with open(tp, "r", encoding="utf-8") as f:
                    reference_text = f.read().strip()
            except Exception as e:
                log_telemetry("ref_text_read_error", {"error": str(e)})
                _clear_reference(meta)
                save_starred_meta(meta)
                set_reference_active(False)
                set_status(f"REF invalid: TEXT read failed. REF CLEARED. Error: {e}")
                return
            if not reference_text:
                _clear_reference(meta)
                save_starred_meta(meta)
                set_reference_active(False)
                set_status("REF invalid: empty TEXT source. REF CLEARED")
                return
            if not reference_summary:
                reference_summary = preview_text(reference_text, 140)
        elif reference_type == REFERENCE_TYPE_IMG:
            ip = str(meta.get("image_path", "") or "")
            if not ip or not os.path.exists(ip):
                _clear_reference(meta)
                save_starred_meta(meta)
                set_reference_active(False)
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
                set_reference_active(False)
                set_status(f"REF invalid: IMG read failed. REF CLEARED. Error: {e}")
                return
        else:
            _clear_reference(meta)
            save_starred_meta(meta)
            set_reference_active(False)
            set_status("REF invalid: unknown reference type. REF CLEARED")
            return

    if isinstance(input_obj, Image.Image):
        input_obj = normalize_image_for_api(input_obj, cfg)

    payload = _build_solve_payload(
        input_obj=input_obj,
        reference_active=reference_active,
        reference_type=reference_type,
        reference_text=reference_text,
        reference_img_b64=reference_img_b64,
    )

    raw_output = None
    for attempt in range(retries + 1):
        try:
            raw_output = _responses_text(
                client=client,
                model_name=model_name,
                input_payload=payload,
                timeout=timeout,
                temperature=temperature,
                max_output_tokens=max(16, int(max_output_tokens)),
            )
            break
        except Exception as e:
            log_telemetry("solve_retry", {"attempt": attempt + 1, "error": str(e)})
            if attempt == retries:
                set_status(f"Solve failed: {e}")
                return

    if not raw_output:
        set_status("Empty model response.")
        return

    out = clean_output(apply_safe_symbols(raw_output)).strip()
    if not out:
        set_status("Model returned empty output.")
        return

    if reference_active and reference_type in (REFERENCE_TYPE_IMG, REFERENCE_TYPE_TEXT):
        if reference_summary:
            out = f"* REF {reference_type}: {reference_summary}\n{out}"
        else:
            out = f"* REF {reference_type}\n{out}"

    ok = safe_clipboard_write(out)
    if ok:
        mark_prompt_success()
    notify_on_complete = bool(cfg.get("notify_on_complete", False))
    if ok and notify_on_complete:
        set_status("Solved → copied to clipboard")
    elif not ok:
        set_status("Solved, but failed to write clipboard")


def toggle_star_worker(client: OpenAI) -> None:
    cfg = get_config()
    model_name = str(cfg.get("model", MODEL) or MODEL).strip() or MODEL
    meta = load_starred_meta()

    # Strict toggle behavior: active -> clear only (no parse/overwrite in same action).
    if bool(meta.get("reference_active", False)):
        _clear_reference(meta)
        save_starred_meta(meta)
        set_reference_active(False)
        set_status("REF CLEARED")
        return

    # Explicit status check before assigning a new reference.
    if not _can_assign_reference(meta):
        return

    raw_clip, err = safe_clipboard_read()
    if err is not None:
        log_telemetry("star_clipboard_read_error", {"error": str(err)})

    # image case
    if isinstance(raw_clip, Image.Image):
        try:
            img = normalize_image_for_api(raw_clip, cfg)
            img_b64 = image_to_base64_png(img)

            classify_payload = [
                {"role": "system", "content": [{"type": "input_text", "text": STAR_CLASSIFY_PROMPT}]},
                {"role": "user", "content": [{"type": "input_image", "image_url": f"data:image/png;base64,{img_b64}"}]},
            ]
            label = _responses_text(
                client=client,
                model_name=model_name,
                input_payload=classify_payload,
                timeout=int(cfg.get("classify_timeout", 8)),
                temperature=0.0,
                max_output_tokens=16,
            ).strip().upper()

            if "TEXTUAL" in label:
                ocr_img = preprocess_for_ocr(img)
                ocr_b64 = image_to_base64_png(ocr_img)
                ocr_payload = [
                    {"role": "system", "content": [{"type": "input_text", "text": STAR_OCR_PROMPT}]},
                    {"role": "user", "content": [{"type": "input_image", "image_url": f"data:image/png;base64,{ocr_b64}"}]},
                ]
                ocr_text = _responses_text(
                    client=client,
                    model_name=model_name,
                    input_payload=ocr_payload,
                    timeout=int(cfg.get("ocr_timeout", 12)),
                    temperature=0.0,
                    max_output_tokens=1200,
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
                })
                save_starred_meta(meta)
                set_reference_active(True)
                log_telemetry("ref_set", {"type": REFERENCE_TYPE_TEXT, "summary_length": len(summary)})
                set_status(f"REF SET TEXT ASSUMED: {summary}")
            elif "VISUAL" in label:
                img_dir = _starred_base_dir()
                img_path = os.path.join(img_dir, STARRED_IMG_FILE)
                img.save(img_path, format="PNG")
                summary = _summarize_visual_reference(
                    client=client,
                    model_name=model_name,
                    img_b64=img_b64,
                    timeout=int(cfg.get("classify_timeout", 8)),
                ) or "visual reference"

                meta.update({
                    "reference_active": True,
                    "reference_type": REFERENCE_TYPE_IMG,
                    "text_path": "",
                    "image_path": img_path,
                    "reference_summary": summary,
                })
                save_starred_meta(meta)
                set_reference_active(True)
                log_telemetry("ref_set", {"type": REFERENCE_TYPE_IMG, "summary_length": len(summary)})
                set_status(f"REF SET IMG ASSUMED: {summary}")
            else:
                set_status(f"REF assign failed: classifier returned '{label or 'EMPTY'}'")
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
        })
        save_starred_meta(meta)
        set_reference_active(True)
        log_telemetry("ref_set", {"type": REFERENCE_TYPE_TEXT, "summary_length": len(summary)})
        set_status(f"REF SET TEXT ASSUMED: {summary}")
    else:
        set_status("REF assign failed: no image/text in clipboard")
