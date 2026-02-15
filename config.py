import os
import json
import sys
from typing import Dict, Any, Optional

APP_NAME = "SunnyNotSummer"
MODEL = "gpt-4o"

DEFAULT_CONFIG: Dict[str, Any] = {
    "api_key": "",
    "model": MODEL,
    "run_hotkey": "ctrl+shift+x",
    "star_hotkey": "ctrl+shift+s",
    "quit_hotkey": "ctrl+shift+q",
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


def app_home_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _config_path() -> str:
    return os.path.join(app_home_dir(), "config.json")


def load_config() -> Dict[str, Any]:
    p = _config_path()

    if not os.path.exists(p):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)

    with open(p, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    changed = False
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
            changed = True

    if changed:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    return cfg


def get_config() -> Dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = load_config()
    return _CONFIG_CACHE


def resolve_api_key(cfg: Dict[str, Any]) -> str:
    return ((cfg.get("api_key") or "").strip() or os.getenv("OPENAI_API_KEY", "").strip())
