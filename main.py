import sys
import time
import threading
import ctypes
from typing import Optional, Set

import pyperclip
import pystray
from PIL import Image
from pystray import MenuItem as item
from openai import OpenAI

from config import get_config, resolve_api_key, APP_NAME
from utils import (
    safe_clipboard_read,
    normalize_image_for_api,
    set_status,
    set_app_icon,
    set_reference_active,
    log_telemetry,
)
from llm_pipeline import solve_pipeline, toggle_star_worker, load_starred_meta

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False


_SINGLE_INSTANCE_MUTEX = None
_HOTKEY_HANDLES = []
STOP_EVENT = threading.Event()
_solve_lock = threading.Lock()
_star_lock = threading.Lock()
_last_run_ts = 0.0
_debounce_lock = threading.Lock()
_KEYBOARD_HOOK_HANDLE = None
_keys_down: Set[str] = set()
_ref_combo_keys: Set[str] = set()
_prev_ref_combo_active = False
_app_start_ts = time.monotonic()
_last_ref_toggle_ts = 0.0
_ref_toggle_in_progress = False
_ref_dispatch_lock = threading.Lock()

_STARTUP_INPUT_LOCKOUT_SEC = 0.75
_REF_TOGGLE_DEBOUNCE_SEC = 0.3


def ensure_single_instance() -> bool:
    global _SINGLE_INSTANCE_MUTEX
    mutex_name = "Global\\SunnyNotSummerSingleInstanceMutex"
    _SINGLE_INSTANCE_MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    last_error = ctypes.windll.kernel32.GetLastError()
    ERROR_ALREADY_EXISTS = 183
    return last_error != ERROR_ALREADY_EXISTS


def _debounced(launch_fn):
    cfg = get_config()
    debounce_ms = int(cfg.get("hotkey_debounce_ms", 250))
    now = time.time() * 1000.0
    global _last_run_ts
    with _debounce_lock:
        if now - _last_run_ts < debounce_ms:
            return
        _last_run_ts = now
    threading.Thread(target=launch_fn, daemon=True).start()


def _canonical_key_name(name: Optional[str]) -> str:
    if not name:
        return ""
    n = str(name).strip().lower()
    if n in ("ctrl", "control", "left ctrl", "right ctrl"):
        return "ctrl"
    if n in ("shift", "left shift", "right shift"):
        return "shift"
    if n in ("alt", "left alt", "right alt", "alt gr"):
        return "alt"
    if n in ("windows", "left windows", "right windows", "win", "cmd", "command"):
        return "windows"
    return n


def _parse_combo_keys(hotkey: str) -> Set[str]:
    keys: Set[str] = set()
    for raw in str(hotkey or "").split("+"):
        k = _canonical_key_name(raw)
        if k:
            keys.add(k)
    return keys


def _is_ref_combo_active() -> bool:
    if not _ref_combo_keys:
        return False
    return _ref_combo_keys.issubset(_keys_down)


def _launch_star_worker_atomic() -> None:
    global _ref_toggle_in_progress
    try:
        star_worker()
    finally:
        with _ref_dispatch_lock:
            _ref_toggle_in_progress = False


def _dispatch_ref_toggle() -> None:
    global _last_ref_toggle_ts, _ref_toggle_in_progress
    now = time.monotonic()
    elapsed_from_start = now - _app_start_ts
    if elapsed_from_start < _STARTUP_INPUT_LOCKOUT_SEC:
        log_telemetry(
            "ref_hotkey_diag",
            {"ts": now, "reason": "suppressed_startup_lockout", "elapsed": elapsed_from_start},
        )
        return

    with _ref_dispatch_lock:
        if _ref_toggle_in_progress:
            log_telemetry(
                "ref_hotkey_diag",
                {"ts": now, "reason": "suppressed_in_progress"},
            )
            return
        if now - _last_ref_toggle_ts < _REF_TOGGLE_DEBOUNCE_SEC:
            log_telemetry(
                "ref_hotkey_diag",
                {"ts": now, "reason": "suppressed_debounce", "elapsed": now - _last_ref_toggle_ts},
            )
            return
        _last_ref_toggle_ts = now
        _ref_toggle_in_progress = True

    log_telemetry("ref_hotkey_diag", {"ts": now, "reason": "toggle_executed"})
    threading.Thread(target=_launch_star_worker_atomic, daemon=True).start()


def _on_keyboard_event(event) -> None:
    global _prev_ref_combo_active
    try:
        key = _canonical_key_name(getattr(event, "name", ""))
        etype = str(getattr(event, "event_type", "") or "").lower()
        if not key or etype not in ("down", "up"):
            return

        if etype == "down":
            _keys_down.add(key)
        else:
            _keys_down.discard(key)

        combo_active = _is_ref_combo_active()
        log_telemetry(
            "ref_hotkey_diag",
            {
                "ts": time.monotonic(),
                "event_type": etype,
                "key": key,
                "keys_down": sorted(_keys_down),
                "combo_active": combo_active,
                "prev_combo_active": _prev_ref_combo_active,
            },
        )

        # Edge-trigger only: dispatch on false -> true transition.
        if combo_active and not _prev_ref_combo_active:
            _dispatch_ref_toggle()

        _prev_ref_combo_active = combo_active
    except Exception as e:
        log_telemetry("ref_hotkey_event_error", {"error": str(e)})


def worker() -> None:
    if not _solve_lock.acquire(blocking=False):
        return
    try:
        cfg = get_config()
        api_key = resolve_api_key(cfg)
        if not api_key:
            set_status("Missing API key (config.json or OPENAI_API_KEY).")
            return

        client = OpenAI(api_key=api_key)

        raw_clip, _ = safe_clipboard_read()
        if isinstance(raw_clip, Image.Image):
            img = normalize_image_for_api(raw_clip, cfg)
            solve_pipeline(client, img)
            return

        text = ""
        try:
            text = (pyperclip.paste() or "").strip()
        except Exception:
            text = ""

        if text:
            solve_pipeline(client, text)
        else:
            set_status("No image or text found on clipboard.")
    except Exception as e:
        log_telemetry("worker_crash", {"error": str(e)})
        set_status(f"Worker error: {e}")
    finally:
        _solve_lock.release()


def star_worker() -> None:
    if not _star_lock.acquire(blocking=False):
        return
    try:
        cfg = get_config()
        api_key = resolve_api_key(cfg)
        if not api_key:
            set_status("Missing API key; STAR unavailable.")
            return
        client = OpenAI(api_key=api_key)
        toggle_star_worker(client)
    except Exception as e:
        log_telemetry("star_worker_crash", {"error": str(e)})
        set_status(f"STAR error: {e}")
    finally:
        _star_lock.release()


def on_quit(icon, _item):
    global _KEYBOARD_HOOK_HANDLE
    STOP_EVENT.set()
    if KEYBOARD_AVAILABLE:
        for h in _HOTKEY_HANDLES:
            try:
                keyboard.remove_hotkey(h)
            except Exception:
                pass
        if _KEYBOARD_HOOK_HANDLE is not None:
            try:
                keyboard.unhook(_KEYBOARD_HOOK_HANDLE)
            except Exception:
                pass
            _KEYBOARD_HOOK_HANDLE = None
    try:
        icon.stop()
    except Exception:
        pass


def setup_hotkeys(icon):
    global _KEYBOARD_HOOK_HANDLE, _ref_combo_keys, _prev_ref_combo_active
    global _last_ref_toggle_ts, _ref_toggle_in_progress, _app_start_ts
    cfg = get_config()
    run_hk = str(cfg.get("run_hotkey", "ctrl+shift+x")).lower()
    star_hk = str(cfg.get("star_hotkey", "ctrl+shift+s")).lower()
    quit_hk = str(cfg.get("quit_hotkey", "ctrl+shift+q")).lower()

    if not KEYBOARD_AVAILABLE:
        set_status("keyboard module not installed. Hotkeys disabled.")
        return

    try:
        # Keep run/quit on keyboard's built-in hotkey binding.
        _HOTKEY_HANDLES.append(keyboard.add_hotkey(run_hk, lambda: _debounced(worker)))
        _HOTKEY_HANDLES.append(keyboard.add_hotkey(quit_hk, lambda: on_quit(icon, None)))

        # STAR/REF uses a single edge-triggered dispatch path to avoid duplicate firings.
        _ref_combo_keys = _parse_combo_keys(star_hk)
        _keys_down.clear()
        _app_start_ts = time.monotonic()
        _prev_ref_combo_active = False
        _last_ref_toggle_ts = 0.0
        _ref_toggle_in_progress = False
        _KEYBOARD_HOOK_HANDLE = keyboard.hook(_on_keyboard_event)
        log_telemetry("ref_hotkey_config", {"star_hotkey": star_hk, "combo_keys": sorted(_ref_combo_keys)})
        set_status("Hotkeys active")
    except Exception as e:
        log_telemetry("hotkey_register_error", {"error": str(e)})
        set_status(f"Hotkey registration failed: {e}")


def main():
    if not ensure_single_instance():
        msg = "App is already running."
        try:
            pyperclip.copy(msg)
        except Exception:
            pass
        ctypes.windll.user32.MessageBoxW(0, msg, "Error", 0x10)
        sys.exit(1)

    cfg = get_config()
    api_key = resolve_api_key(cfg)
    if not api_key:
        msg = "OpenAI API key not found.\nApp will start, but solve/star features require a key."
        try:
            pyperclip.copy(msg)
        except Exception:
            pass
        ctypes.windll.user32.MessageBoxW(
            0,
            msg,
            "Missing API Key",
            0x30
        )

    icon = pystray.Icon(
        APP_NAME,
        Image.new("RGB", (64, 64), "teal"),
        APP_NAME,
        menu=pystray.Menu(item("Quit", lambda: on_quit(icon, None)))
    )

    set_app_icon(icon)
    try:
        meta = load_starred_meta()
        set_reference_active(bool(meta.get("reference_active", False)))
    except Exception as e:
        log_telemetry("reference_state_init_error", {"error": str(e)})
    setup_hotkeys(icon)
    icon.run()


if __name__ == "__main__":
    main()
