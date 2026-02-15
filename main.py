import ctypes
import json
import sys
import threading
import time
from typing import Dict, Optional, Set, Tuple

import pyperclip
import pystray
from PIL import Image
from openai import OpenAI
from pystray import MenuItem as item

from config import (
    APP_NAME,
    MODEL,
    get_config,
    reload_config,
    resolve_api_key,
    update_config_values,
)
from llm_pipeline import clear_reference_state, toggle_star_worker, solve_pipeline
from utils import (
    log_telemetry,
    normalize_image_for_api,
    safe_clipboard_read,
    safe_clipboard_write,
    set_app_icon,
    set_reference_active,
    set_status,
)

try:
    import keyboard

    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False


_SINGLE_INSTANCE_MUTEX = None
_HOTKEY_HANDLES = []
_MODIFIER_KEYS = {"ctrl", "alt", "shift", "windows"}

STOP_EVENT = threading.Event()
_solve_lock = threading.Lock()
_star_lock = threading.Lock()
_model_lock = threading.Lock()

_last_action_ts: Dict[str, float] = {}
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


def _debounced(action_name: str, launch_fn) -> None:
    cfg = get_config()
    debounce_ms = int(cfg.get("hotkey_debounce_ms", 250))
    now = time.time() * 1000.0
    with _debounce_lock:
        last_ts = _last_action_ts.get(action_name, 0.0)
        if now - last_ts < debounce_ms:
            return
        _last_action_ts[action_name] = now
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
        raw = raw.strip()
        if not raw:
            continue
        key = _canonical_key_name(raw)
        if key:
            keys.add(key)
    return keys


def _normalize_hotkey_combo(combo: str) -> str:
    raw_parts = str(combo or "").split("+")
    parts = []
    for raw in raw_parts:
        p = raw.strip()
        if not p:
            raise ValueError("invalid hotkey syntax")
        key = _canonical_key_name(p)
        if not key:
            raise ValueError("invalid hotkey syntax")
        parts.append(key)

    if not parts:
        raise ValueError("hotkey is empty")
    if len(set(parts)) != len(parts):
        raise ValueError("hotkey contains duplicate keys")
    if not any(k in _MODIFIER_KEYS for k in parts):
        raise ValueError("hotkey must include a modifier")
    if all(k in _MODIFIER_KEYS for k in parts):
        raise ValueError("hotkey must include a non-modifier key")

    return "+".join(parts)


def _collect_hotkeys_from_cfg(cfg: Dict[str, object]) -> Dict[str, str]:
    return {
        "run_hotkey": str(cfg.get("run_hotkey", "ctrl+shift+x") or "ctrl+shift+x"),
        "star_hotkey": str(cfg.get("star_hotkey", "ctrl+shift+s") or "ctrl+shift+s"),
        "quit_hotkey": str(cfg.get("quit_hotkey", "ctrl+shift+q") or "ctrl+shift+q"),
        "cycle_model_hotkey": str(cfg.get("cycle_model_hotkey", "ctrl+shift+m") or "ctrl+shift+m"),
    }


def _validate_hotkey_assignments(hotkeys: Dict[str, str]) -> Tuple[bool, str, Dict[str, str]]:
    normalized: Dict[str, str] = {}
    for key_name, combo in hotkeys.items():
        try:
            normalized[key_name] = _normalize_hotkey_combo(combo)
        except ValueError as e:
            return False, f"{key_name} {e}", {}

    seen: Dict[str, str] = {}
    for key_name, combo in normalized.items():
        if combo in seen:
            return False, f"conflict between {seen[combo]} and {key_name}", {}
        seen[combo] = key_name

    return True, "", normalized


def _normalize_available_models(cfg: Dict[str, object]) -> list:
    raw_models = cfg.get("available_models")
    models = []
    if isinstance(raw_models, list):
        for raw in raw_models:
            m = str(raw or "").strip()
            if m and m not in models:
                models.append(m)

    current_model = str(cfg.get("model", MODEL) or MODEL).strip() or MODEL
    if not models:
        models = [MODEL]
    if current_model and current_model not in models:
        models.insert(0, current_model)
    if not models:
        models = [MODEL]
    return models


def _active_model_name(cfg: Optional[Dict[str, object]] = None) -> str:
    c = cfg or get_config()
    return str(c.get("model", MODEL) or MODEL).strip() or MODEL


def _announce_model_active(model_name: str) -> None:
    line = f"MODEL ACTIVE: {model_name}"
    if not safe_clipboard_write(line):
        log_telemetry("model_active_clipboard_error", {"model": model_name})
    set_status(line)


def _persist_config_changes(changes: Dict[str, object], source: str) -> Optional[Dict[str, object]]:
    try:
        return update_config_values(changes)
    except Exception as e:
        log_telemetry("config_persist_error", {"source": source, "error": str(e), "keys": sorted(list(changes.keys()))})
        return None


def cycle_model_worker(icon) -> None:
    if not _model_lock.acquire(blocking=False):
        return
    try:
        cfg = get_config()
        models = _normalize_available_models(cfg)
        old_model = _active_model_name(cfg)

        if old_model not in models:
            models.insert(0, old_model)
        if not models:
            models = [MODEL]

        try:
            old_idx = models.index(old_model)
        except ValueError:
            old_idx = 0
        new_model = models[(old_idx + 1) % len(models)]

        updated = _persist_config_changes({"model": new_model, "available_models": models}, source="cycle_model")
        if updated is None:
            set_status("MODEL CHANGE FAILED: unable to persist config")
            return

        log_telemetry("model_changed", {"old": old_model, "new": new_model, "source": "hotkey"})
        if old_model != new_model:
            set_status(f"MODEL CHANGED: {old_model} -> {new_model}")
        _announce_model_active(new_model)
        _refresh_tray_menu(icon)
    finally:
        _model_lock.release()


def _set_model_from_ui(icon, model_name: str, source: str) -> None:
    with _model_lock:
        cfg = get_config()
        models = _normalize_available_models(cfg)
        target_model = str(model_name or "").strip()
        if not target_model:
            set_status("MODEL CHANGE FAILED: empty model")
            return
        if target_model not in models:
            set_status(f"MODEL CHANGE FAILED: unknown model '{target_model}'")
            return

        old_model = _active_model_name(cfg)
        updated = _persist_config_changes({"model": target_model, "available_models": models}, source=source)
        if updated is None:
            set_status("MODEL CHANGE FAILED: unable to persist config")
            return

        if old_model != target_model:
            log_telemetry("model_changed", {"old": old_model, "new": target_model, "source": source})
            set_status(f"MODEL CHANGED: {old_model} -> {target_model}")
        if source == "tray":
            log_telemetry("model_selected_from_tray", {"old": old_model, "new": target_model})

        _announce_model_active(target_model)
        _refresh_tray_menu(icon)


def _show_hotkey_input_dialog(title: str, prompt: str, initial_value: str) -> Optional[str]:
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        value = simpledialog.askstring(title, prompt, initialvalue=initial_value, parent=root)
        root.destroy()
        return value
    except Exception as e:
        log_telemetry("hotkey_update_failed", {"reason": "input_dialog_error", "error": str(e)})
        set_status("HOTKEY UPDATE FAILED: input dialog unavailable")
        return None


def _set_hotkey_from_tray(icon, key_name: str, label: str) -> None:
    cfg = get_config()
    old_hotkey = str(cfg.get(key_name, "") or "")
    raw_value = _show_hotkey_input_dialog(
        title="Set Hotkey",
        prompt=f"Enter new {label} hotkey (example: ctrl+alt+r)",
        initial_value=old_hotkey,
    )
    if raw_value is None:
        log_telemetry("hotkey_update_failed", {"key_name": key_name, "reason": "cancelled"})
        set_status("HOTKEY UPDATE FAILED: cancelled")
        return

    try:
        new_hotkey = _normalize_hotkey_combo(raw_value)
    except ValueError as e:
        reason = str(e)
        log_telemetry("hotkey_update_failed", {"key_name": key_name, "reason": reason})
        set_status(f"HOTKEY UPDATE FAILED: {reason}")
        return

    proposed = _collect_hotkeys_from_cfg(cfg)
    proposed[key_name] = new_hotkey
    valid, reason, normalized = _validate_hotkey_assignments(proposed)
    if not valid:
        log_telemetry("hotkey_conflict", {"key_name": key_name, "reason": reason, "attempted": new_hotkey})
        set_status(f"HOTKEY UPDATE FAILED: {reason}")
        return

    updated = _persist_config_changes({key_name: normalized[key_name]}, source="hotkey_update")
    if updated is None:
        log_telemetry("hotkey_update_failed", {"key_name": key_name, "reason": "persist_failed"})
        set_status("HOTKEY UPDATE FAILED: unable to persist config")
        return

    if not setup_hotkeys(icon, announce=False):
        rollback = _persist_config_changes({key_name: old_hotkey}, source="hotkey_update_rollback")
        if rollback is not None:
            setup_hotkeys(icon, announce=False)
        log_telemetry("hotkey_update_failed", {"key_name": key_name, "reason": "runtime_rebind_failed"})
        set_status("HOTKEY UPDATE FAILED: runtime rebind failed")
        return

    log_telemetry("hotkey_updated", {"key_name": key_name, "old": old_hotkey, "new": normalized[key_name]})
    set_status(f"HOTKEY UPDATED: {label} = {normalized[key_name]}")
    _refresh_tray_menu(icon)


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
            log_telemetry("ref_hotkey_diag", {"ts": now, "reason": "suppressed_in_progress"})
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


def _unregister_hotkeys() -> None:
    global _KEYBOARD_HOOK_HANDLE
    if not KEYBOARD_AVAILABLE:
        return
    for h in list(_HOTKEY_HANDLES):
        try:
            keyboard.remove_hotkey(h)
        except Exception:
            pass
    _HOTKEY_HANDLES.clear()
    if _KEYBOARD_HOOK_HANDLE is not None:
        try:
            keyboard.unhook(_KEYBOARD_HOOK_HANDLE)
        except Exception:
            pass
        _KEYBOARD_HOOK_HANDLE = None


def setup_hotkeys(icon, announce: bool = True) -> bool:
    global _KEYBOARD_HOOK_HANDLE, _ref_combo_keys, _prev_ref_combo_active
    global _last_ref_toggle_ts, _ref_toggle_in_progress, _app_start_ts
    cfg = get_config()
    hotkeys = _collect_hotkeys_from_cfg(cfg)
    valid, reason, normalized = _validate_hotkey_assignments(hotkeys)
    if not valid:
        log_telemetry("hotkey_conflict", {"reason": reason, "hotkeys": hotkeys})
        if announce:
            set_status(f"HOTKEY UPDATE FAILED: {reason}")
        return False

    if not KEYBOARD_AVAILABLE:
        if announce:
            set_status("keyboard module not installed. Hotkeys disabled.")
        return False

    _unregister_hotkeys()
    try:
        run_hk = normalized["run_hotkey"]
        quit_hk = normalized["quit_hotkey"]
        star_hk = normalized["star_hotkey"]
        cycle_hk = normalized["cycle_model_hotkey"]

        _HOTKEY_HANDLES.append(keyboard.add_hotkey(run_hk, lambda: _debounced("run", worker)))
        _HOTKEY_HANDLES.append(keyboard.add_hotkey(quit_hk, lambda: on_quit(icon, None)))
        _HOTKEY_HANDLES.append(
            keyboard.add_hotkey(cycle_hk, lambda: _debounced("cycle_model", lambda: cycle_model_worker(icon)))
        )

        _ref_combo_keys = _parse_combo_keys(star_hk)
        _keys_down.clear()
        _app_start_ts = time.monotonic()
        _prev_ref_combo_active = False
        _last_ref_toggle_ts = 0.0
        _ref_toggle_in_progress = False
        _KEYBOARD_HOOK_HANDLE = keyboard.hook(_on_keyboard_event)

        log_telemetry(
            "ref_hotkey_config",
            {
                "star_hotkey": star_hk,
                "combo_keys": sorted(_ref_combo_keys),
                "run_hotkey": run_hk,
                "quit_hotkey": quit_hk,
                "cycle_model_hotkey": cycle_hk,
            },
        )
        if announce:
            set_status("Hotkeys active")
        return True
    except Exception as e:
        log_telemetry("hotkey_register_error", {"error": str(e)})
        if announce:
            set_status(f"Hotkey registration failed: {e}")
        _unregister_hotkeys()
        return False


def _on_tray_solve_now(_icon, _item):
    _debounced("run", worker)


def _on_tray_star_toggle(_icon, _item):
    threading.Thread(target=star_worker, daemon=True).start()


def _on_tray_select_model(icon, _item, model_name: str):
    _set_model_from_ui(icon, model_name, source="tray")


def _on_tray_refresh_model_list(icon, _item):
    cfg = reload_config()
    model_name = _active_model_name(cfg)
    _announce_model_active(model_name)
    _refresh_tray_menu(icon)


def _on_tray_set_run_hotkey(icon, _item):
    _set_hotkey_from_tray(icon, "run_hotkey", "run")


def _on_tray_set_star_hotkey(icon, _item):
    _set_hotkey_from_tray(icon, "star_hotkey", "STAR")


def _on_tray_set_quit_hotkey(icon, _item):
    _set_hotkey_from_tray(icon, "quit_hotkey", "quit")


def _on_tray_set_cycle_model_hotkey(icon, _item):
    _set_hotkey_from_tray(icon, "cycle_model_hotkey", "cycle model")


def _on_tray_show_current_config(_icon, _item):
    cfg = get_config()
    cfg_txt = json.dumps(cfg, indent=2)
    if safe_clipboard_write(cfg_txt):
        set_status("Current config copied to clipboard")
    else:
        set_status("Failed to copy current config")


def _is_model_checked(model_name: str) -> bool:
    return _active_model_name() == str(model_name)


def _make_model_select_action(model_name: str):
    def _action(icon, menu_item):
        _on_tray_select_model(icon, menu_item, model_name)

    return _action


def _build_tray_menu():
    cfg = get_config()
    models = _normalize_available_models(cfg)

    model_items = [
        item(
            m,
            _make_model_select_action(m),
            checked=lambda *_args, model_name=m: _is_model_checked(model_name),
            radio=True,
        )
        for m in models
    ]
    model_items.append(item("Refresh Model List", _on_tray_refresh_model_list))

    return pystray.Menu(
        item("Solve Now", _on_tray_solve_now),
        item("STAR Toggle", _on_tray_star_toggle),
        item("Model", pystray.Menu(*model_items)),
        item(
            "Hotkeys",
            pystray.Menu(
                item("Set Run Hotkey", _on_tray_set_run_hotkey),
                item("Set STAR Hotkey", _on_tray_set_star_hotkey),
                item("Set Quit Hotkey", _on_tray_set_quit_hotkey),
                item("Set Cycle Model Hotkey", _on_tray_set_cycle_model_hotkey),
            ),
        ),
        item("Show Current Config", _on_tray_show_current_config),
        item("Quit", on_quit),
    )


def _refresh_tray_menu(icon) -> None:
    if icon is None:
        return
    try:
        icon.menu = _build_tray_menu()
        if hasattr(icon, "update_menu"):
            icon.update_menu()
    except Exception as e:
        log_telemetry("tray_menu_update_error", {"error": str(e)})


def on_quit(icon, _item):
    clear_reference_state(source="exit", status_message="REF CLEARED ON EXIT")
    STOP_EVENT.set()
    _unregister_hotkeys()
    try:
        icon.stop()
    except Exception:
        pass


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
        ctypes.windll.user32.MessageBoxW(0, msg, "Missing API Key", 0x30)

    icon = pystray.Icon(APP_NAME, Image.new("RGB", (64, 64), "teal"), APP_NAME, menu=_build_tray_menu())

    set_app_icon(icon)
    clear_reference_state(source="startup", status_message="REF CLEARED ON STARTUP")
    set_reference_active(False)

    setup_hotkeys(icon)
    _announce_model_active(_active_model_name(cfg))
    log_telemetry("startup_model", {"model": _active_model_name(cfg)})
    icon.run()


if __name__ == "__main__":
    main()
