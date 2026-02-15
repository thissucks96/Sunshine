import os
import json
import sys
import threading
from typing import Dict, Any, Optional

APP_NAME = "SunnyNotSummer"
MODEL = "gpt-4o"

DEFAULT_CONFIG: Dict[str, Any] = {
    "api_key": "",
    "model": MODEL,
    "available_models": [MODEL, "gpt-4o-mini", "gpt-5-mini", "gpt-5", "gpt-5.2"],
    "temperature": 0.0,
    "request_timeout": 25,
    "retries": 1,
    "max_output_tokens": 2200,

    # image guards
    "max_image_side": 4096,
    "max_image_pixels": 16_000_000,

    # classifier/ocr helper timeouts
    "classify_timeout": 8,
    "ocr_timeout": 12,
    # Stable vision model for REF visual-summary fallback.
    "reference_summary_model": "gpt-4o-mini",

    # behavior
    "debug": False,
    "telemetry_file": "solver_telemetry.jsonl",

    # debounce
    "hotkey_debounce_ms": 250,

    # notifications
    "notify_on_complete": False,
    "status_notify_enabled": True,
    "status_notify_max_chars": 72,
    "status_notify_clear_sec": 1.1,
    "status_notify_title": "SNS",
    # Status-to-clipboard mirroring is opt-in; default off to avoid clobbering solve outputs.
    "status_copy_to_clipboard": False,

    # clipboard history timing (seconds between full and final-answer writes)
    "clipboard_history_settle_sec": 0.6,
}

_CONFIG_CACHE: Optional[Dict[str, Any]] = None
_CONFIG_LOCK = threading.RLock()


def app_home_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _config_path() -> str:
    return os.path.join(app_home_dir(), "config.json")


def _normalize_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(cfg or {})

    model_name = str(normalized.get("model", MODEL) or MODEL).strip() or MODEL
    if normalized.get("model") != model_name:
        normalized["model"] = model_name

    available_models_raw = normalized.get("available_models")
    available_models = []
    if isinstance(available_models_raw, list):
        for raw in available_models_raw:
            m = str(raw or "").strip()
            if m and m not in available_models:
                available_models.append(m)

    if not available_models:
        available_models = [MODEL]

    if model_name not in available_models:
        available_models.insert(0, model_name)

    # Ensure default selectable models are always present for tray/runtime switching.
    for default_model in DEFAULT_CONFIG.get("available_models", []):
        m = str(default_model or "").strip()
        if m and m not in available_models:
            available_models.append(m)

    if normalized.get("available_models") != available_models:
        normalized["available_models"] = available_models

    # Keep image constraints intentionally lax to preserve OCR/plot detail.
    try:
        max_side = int(normalized.get("max_image_side", DEFAULT_CONFIG["max_image_side"]))
    except Exception:
        max_side = int(DEFAULT_CONFIG["max_image_side"])
    try:
        max_pixels = int(normalized.get("max_image_pixels", DEFAULT_CONFIG["max_image_pixels"]))
    except Exception:
        max_pixels = int(DEFAULT_CONFIG["max_image_pixels"])

    max_side = max(max_side, int(DEFAULT_CONFIG["max_image_side"]))
    max_pixels = max(max_pixels, int(DEFAULT_CONFIG["max_image_pixels"]))

    if normalized.get("max_image_side") != max_side:
        normalized["max_image_side"] = max_side
    if normalized.get("max_image_pixels") != max_pixels:
        normalized["max_image_pixels"] = max_pixels

    # Keep enough delay for clipboard history apps to capture two writes.
    try:
        settle = float(normalized.get("clipboard_history_settle_sec", DEFAULT_CONFIG["clipboard_history_settle_sec"]))
    except Exception:
        settle = float(DEFAULT_CONFIG["clipboard_history_settle_sec"])
    settle = max(0.25, settle)
    if normalized.get("clipboard_history_settle_sec") != settle:
        normalized["clipboard_history_settle_sec"] = settle

    # Notification presentation tuning (kept small/short by default).
    try:
        notify_max_chars = int(normalized.get("status_notify_max_chars", DEFAULT_CONFIG["status_notify_max_chars"]))
    except Exception:
        notify_max_chars = int(DEFAULT_CONFIG["status_notify_max_chars"])
    notify_max_chars = max(24, min(120, notify_max_chars))
    if normalized.get("status_notify_max_chars") != notify_max_chars:
        normalized["status_notify_max_chars"] = notify_max_chars

    try:
        notify_clear_sec = float(normalized.get("status_notify_clear_sec", DEFAULT_CONFIG["status_notify_clear_sec"]))
    except Exception:
        notify_clear_sec = float(DEFAULT_CONFIG["status_notify_clear_sec"])
    notify_clear_sec = max(0.2, min(5.0, notify_clear_sec))
    if normalized.get("status_notify_clear_sec") != notify_clear_sec:
        normalized["status_notify_clear_sec"] = notify_clear_sec

    notify_title = str(normalized.get("status_notify_title", DEFAULT_CONFIG["status_notify_title"]) or "").strip()
    if not notify_title:
        notify_title = str(DEFAULT_CONFIG["status_notify_title"])
    if normalized.get("status_notify_title") != notify_title:
        normalized["status_notify_title"] = notify_title

    notify_enabled = bool(normalized.get("status_notify_enabled", DEFAULT_CONFIG["status_notify_enabled"]))
    if normalized.get("status_notify_enabled") != notify_enabled:
        normalized["status_notify_enabled"] = notify_enabled

    status_copy_to_clipboard = bool(
        normalized.get("status_copy_to_clipboard", DEFAULT_CONFIG["status_copy_to_clipboard"])
    )
    if normalized.get("status_copy_to_clipboard") != status_copy_to_clipboard:
        normalized["status_copy_to_clipboard"] = status_copy_to_clipboard

    reference_summary_model = str(
        normalized.get("reference_summary_model", DEFAULT_CONFIG["reference_summary_model"]) or ""
    ).strip()
    if not reference_summary_model:
        reference_summary_model = str(DEFAULT_CONFIG["reference_summary_model"])
    if normalized.get("reference_summary_model") != reference_summary_model:
        normalized["reference_summary_model"] = reference_summary_model
    return normalized


def _save_config_unlocked(cfg: Dict[str, Any]) -> None:
    p = _config_path()
    d = os.path.dirname(p) or "."
    tmp_path = os.path.join(d, f".{os.path.basename(p)}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp_path, p)


def save_config(cfg: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_config(cfg)
    with _CONFIG_LOCK:
        _save_config_unlocked(normalized)
    return normalized


def load_config() -> Dict[str, Any]:
    with _CONFIG_LOCK:
        p = _config_path()

        if not os.path.exists(p):
            cfg = _normalize_config(dict(DEFAULT_CONFIG))
            _save_config_unlocked(cfg)
            return cfg

        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                raise ValueError("config root must be an object")
        except Exception:
            # Recover from malformed/partial config writes by resetting to defaults.
            cfg = _normalize_config(dict(DEFAULT_CONFIG))
            _save_config_unlocked(cfg)
            return cfg

        changed = False
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
                changed = True

        normalized = _normalize_config(cfg)
        if normalized != cfg:
            changed = True

        if changed:
            _save_config_unlocked(normalized)

        return normalized


def get_config() -> Dict[str, Any]:
    global _CONFIG_CACHE
    with _CONFIG_LOCK:
        if _CONFIG_CACHE is None:
            _CONFIG_CACHE = load_config()
        return _CONFIG_CACHE


def reload_config() -> Dict[str, Any]:
    global _CONFIG_CACHE
    with _CONFIG_LOCK:
        _CONFIG_CACHE = load_config()
        return _CONFIG_CACHE


def update_config(key: str, value: Any) -> Dict[str, Any]:
    return update_config_values({key: value})


def update_config_values(changes: Dict[str, Any]) -> Dict[str, Any]:
    global _CONFIG_CACHE
    with _CONFIG_LOCK:
        base = dict(get_config())
        base.update(changes or {})
        normalized = _normalize_config(base)
        _save_config_unlocked(normalized)
        _CONFIG_CACHE = normalized
        return _CONFIG_CACHE


def resolve_api_key(cfg: Dict[str, Any]) -> str:
    return ((cfg.get("api_key") or "").strip() or os.getenv("OPENAI_API_KEY", "").strip())
