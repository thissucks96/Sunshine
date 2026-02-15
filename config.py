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
    "available_models": [MODEL, "gpt-4o-mini"],
    "temperature": 0.0,
    "request_timeout": 25,
    "retries": 1,
    "max_output_tokens": 2200,

    # image guards
    "max_image_side": 2200,
    "max_image_pixels": 4_000_000,

    # classifier/ocr helper timeouts
    "classify_timeout": 8,
    "ocr_timeout": 12,

    # behavior
    "debug": False,
    "telemetry_file": "solver_telemetry.jsonl",

    # debounce
    "hotkey_debounce_ms": 250,

    # notifications
    "notify_on_complete": False,
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

    if normalized.get("available_models") != available_models:
        normalized["available_models"] = available_models
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

        with open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)

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
