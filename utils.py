import os
import time
import json
import re
import threading
import sys
from typing import Any, Dict, Optional, Tuple

import pyperclip
from PIL import Image, ImageGrab, ImageOps

from config import get_config, app_home_dir

_APP_ICON = None  # set from main.py
_STATUS_LOCK = threading.Lock()
_LAST_STATUS_MESSAGE = ""
_LAST_STATUS_TS = 0.0
_STATUS_DEDUPE_WINDOW_SEC = 0.3

_TRAY_STATE_LOCK = threading.Lock()
_IDLE_ICON = None
_IDLE_ICON_SOURCE = "generated:neutral"
_GENERATED_ICONS: Dict[str, Image.Image] = {}
_REFERENCE_ACTIVE = False
_PROMPT_SUCCESS_ACTIVE = False
_ERROR_ACTIVE = False
_PROMPT_SUCCESS_SEQ = 0
_LAST_RENDER_SIGNATURE = ""

_PROMPT_SUCCESS_PULSE_SEC = 0.8


def set_app_icon(icon) -> None:
    global _APP_ICON
    with _TRAY_STATE_LOCK:
        _APP_ICON = icon
        _load_idle_icon_locked()
    update_tray_icon()


def resource_path(rel_path: str) -> str:
    base = getattr(sys, "_MEIPASS", None) or app_home_dir()
    return os.path.join(base, rel_path)


def _make_generated_icon(color: str) -> Image.Image:
    return Image.new("RGBA", (64, 64), color)


def _generated_icon_locked(kind: str) -> Image.Image:
    if kind in _GENERATED_ICONS:
        return _GENERATED_ICONS[kind]
    palette = {
        "error": "#C0392B",      # red
        "success": "#1E9E5A",    # green
        "reference": "#D4A017",  # yellow
        "neutral": "#6A6A6A",    # fallback idle
    }
    color = palette.get(kind, palette["neutral"])
    img = _make_generated_icon(color)
    _GENERATED_ICONS[kind] = img
    return img


def _load_idle_icon_locked() -> None:
    global _IDLE_ICON, _IDLE_ICON_SOURCE
    icon_path = resource_path("icon.ico")
    exists = os.path.exists(icon_path)
    loaded = False
    warning = ""
    image = None
    if exists:
        try:
            with Image.open(icon_path) as im:
                image = im.convert("RGBA").copy()
            loaded = True
        except Exception as e:
            warning = f"Failed to load icon.ico: {e}"
    else:
        warning = "icon.ico not found; falling back to generated neutral icon."

    if image is None:
        image = _generated_icon_locked("neutral")
        _IDLE_ICON_SOURCE = "generated:neutral"
    else:
        _IDLE_ICON_SOURCE = "icon.ico"
    _IDLE_ICON = image
    log_telemetry(
        "tray_icon_startup",
        {
            "resolved_path": icon_path,
            "exists": exists,
            "loaded": loaded,
            "source": _IDLE_ICON_SOURCE,
            "warning": warning,
        },
    )


def _message_looks_error(message: str) -> bool:
    t = (message or "").strip().lower()
    return ("error" in t) or ("failed" in t)


def _render_tray_icon_locked() -> Tuple[Image.Image, str, str]:
    global _PROMPT_SUCCESS_ACTIVE
    if _ERROR_ACTIVE:
        return _generated_icon_locked("error"), "ERROR", "generated:red"
    if _PROMPT_SUCCESS_ACTIVE:
        return _generated_icon_locked("success"), "PROMPT_SUCCESS", "generated:green"
    if _REFERENCE_ACTIVE:
        return _generated_icon_locked("reference"), "REFERENCE_PRIMED", "generated:yellow"
    idle = _IDLE_ICON or _generated_icon_locked("neutral")
    source = _IDLE_ICON_SOURCE if _IDLE_ICON is not None else "generated:neutral"
    return idle, "IDLE", source


def update_tray_icon() -> None:
    global _LAST_RENDER_SIGNATURE
    with _TRAY_STATE_LOCK:
        if _APP_ICON is None:
            return
        img, rendered_state, source = _render_tray_icon_locked()
        signature = f"{rendered_state}|{source}"
        if signature == _LAST_RENDER_SIGNATURE:
            return
        _LAST_RENDER_SIGNATURE = signature
        try:
            _APP_ICON.icon = img
        except Exception as e:
            log_telemetry("tray_icon_render_error", {"error": str(e)})
            return
    log_telemetry("tray_icon_render", {"state": rendered_state, "source": source})


def set_reference_active(active: bool) -> None:
    global _REFERENCE_ACTIVE
    active = bool(active)
    changed = False
    with _TRAY_STATE_LOCK:
        if _REFERENCE_ACTIVE != active:
            _REFERENCE_ACTIVE = active
            changed = True
    if changed:
        update_tray_icon()


def set_error_active(active: bool) -> None:
    global _ERROR_ACTIVE
    active = bool(active)
    changed = False
    with _TRAY_STATE_LOCK:
        if _ERROR_ACTIVE != active:
            _ERROR_ACTIVE = active
            changed = True
    if changed:
        update_tray_icon()


def _clear_prompt_success_after(seq: int) -> None:
    time.sleep(_PROMPT_SUCCESS_PULSE_SEC)
    global _PROMPT_SUCCESS_ACTIVE
    changed = False
    with _TRAY_STATE_LOCK:
        if seq == _PROMPT_SUCCESS_SEQ and _PROMPT_SUCCESS_ACTIVE:
            _PROMPT_SUCCESS_ACTIVE = False
            changed = True
    if changed:
        update_tray_icon()


def mark_prompt_success() -> None:
    global _PROMPT_SUCCESS_ACTIVE, _PROMPT_SUCCESS_SEQ
    set_error_active(False)
    with _TRAY_STATE_LOCK:
        _PROMPT_SUCCESS_SEQ += 1
        seq = _PROMPT_SUCCESS_SEQ
        _PROMPT_SUCCESS_ACTIVE = True
    update_tray_icon()
    threading.Thread(target=_clear_prompt_success_after, args=(seq,), daemon=True).start()


def show_notification(msg: str, title: str = "SunnyNotSummer") -> None:
    global _APP_ICON
    cfg = get_config()
    if not bool(cfg.get("status_notify_enabled", True)):
        return
    if _APP_ICON and getattr(_APP_ICON, "HAS_NOTIFICATION", False):
        try:
            max_chars = int(cfg.get("status_notify_max_chars", 72))
            compact_msg = " ".join(str(msg or "").split())
            if len(compact_msg) > max_chars:
                compact_msg = compact_msg[: max_chars - 3].rstrip() + "..."
            notify_title = str(cfg.get("status_notify_title", "SNS") or "SNS").strip()
            _APP_ICON.notify(compact_msg, title=notify_title)
            clear_sec = float(cfg.get("status_notify_clear_sec", 1.1))
            if clear_sec > 0 and hasattr(_APP_ICON, "remove_notification"):
                def _clear():
                    time.sleep(max(0.2, min(clear_sec, 5.0)))
                    try:
                        _APP_ICON.remove_notification()
                    except Exception:
                        pass

                threading.Thread(target=_clear, daemon=True).start()
        except Exception:
            pass


def log_telemetry(event: str, data: Dict[str, Any]) -> None:
    cfg = get_config()
    if not cfg.get("debug", False):
        return
    path = os.path.join(app_home_dir(), cfg.get("telemetry_file", "solver_telemetry.jsonl"))
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "event": event, "data": data}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def set_status(msg: str) -> None:
    global _LAST_STATUS_MESSAGE, _LAST_STATUS_TS
    message = str(msg)
    now = time.monotonic()
    set_error_active(_message_looks_error(message))

    with _STATUS_LOCK:
        if message == _LAST_STATUS_MESSAGE and (now - _LAST_STATUS_TS) < _STATUS_DEDUPE_WINDOW_SEC:
            log_telemetry("status_suppressed", {"message": message, "window_sec": _STATUS_DEDUPE_WINDOW_SEC})
            return
        _LAST_STATUS_MESSAGE = message
        _LAST_STATUS_TS = now

    log_telemetry("status", {"message": message})
    cfg = get_config()
    # Optional debug mirror only; default off so status updates do not overwrite solve results.
    if bool(cfg.get("status_copy_to_clipboard", False)):
        safe_clipboard_write(message)
    show_notification(message)


def safe_clipboard_read(max_attempts: int = 3, delay: float = 0.05) -> Tuple[Any, Optional[Exception]]:
    last_err = None
    for _ in range(max_attempts):
        try:
            return ImageGrab.grabclipboard(), None
        except Exception as e:
            last_err = e
            time.sleep(delay)
    return None, last_err


def safe_clipboard_write(text: str, max_attempts: int = 3, delay: float = 0.05) -> bool:
    for _ in range(max_attempts):
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            time.sleep(delay)
    log_telemetry("clipboard_write_error", {"text_sample": (text or "")[:80]})
    return False


def normalize_image_for_api(img: Image.Image, cfg: Dict[str, Any]) -> Image.Image:
    if not isinstance(img, Image.Image):
        return img

    max_side = int(cfg.get("max_image_side", 2200))
    max_pixels = int(cfg.get("max_image_pixels", 4_000_000))
    w, h = img.size
    if w <= 0 or h <= 0:
        return img

    scale = 1.0
    longest = max(w, h)
    if longest > max_side:
        scale = min(scale, max_side / float(longest))
    if (w * h) > max_pixels:
        scale = min(scale, (max_pixels / float(w * h)) ** 0.5)

    if scale < 1.0:
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
        img = img.resize((nw, nh), Image.LANCZOS)

    if img.mode != "RGB":
        img = img.convert("RGB")

    return img


def preprocess_for_ocr(img: Image.Image) -> Image.Image:
    gray = ImageOps.grayscale(img)
    enhanced = ImageOps.autocontrast(gray)
    return enhanced.convert("RGB")


# Optional light symbol cleanup so output stays readable/plain
def apply_safe_symbols(text: str) -> str:
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\\leq", "≤").replace("\\geq", "≥").replace("\\neq", "≠")
    t = t.replace("<=", "≤").replace(">=", "≥").replace("!=", "≠")
    t = t.replace("\\infty", "∞").replace("infty", "∞")
    t = t.replace("\\cup", "∪").replace("⋃", "∪")
    t = t.replace("\\in", "∈").replace("\\mathbb{R}", "ℝ")
    t = t.replace("\\pm", "±")
    t = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"√(\1)", t)
    t = re.sub(r"(?i)\bsqrt\s*\(\s*([^()]+?)\s*\)", r"√(\1)", t)
    t = re.sub(r"\^2\b", "²", t)
    t = re.sub(r"\^3\b", "³", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()
