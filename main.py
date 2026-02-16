import ctypes
import sys
import threading
import time
import uuid
from typing import Dict, Optional, Set

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
from llm_pipeline import clear_reference_state, load_starred_meta, solve_pipeline, toggle_star_worker
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
_TRAY_ICON = None

# Hotkeys are intentionally fixed in source; runtime editing is removed.
RUN_HOTKEY = "ctrl+shift+x"
REF_TOGGLE_HOTKEY = "ctrl+shift+s"
QUIT_HOTKEY = "ctrl+shift+q"
CYCLE_MODEL_HOTKEY = "ctrl+shift+m"

STOP_EVENT = threading.Event()
_solve_lock = threading.Lock()
_star_lock = threading.Lock()
_model_lock = threading.Lock()
_active_solve_state_lock = threading.Lock()
_active_solve_client: Optional[OpenAI] = None
_active_solve_cancel_event: Optional[threading.Event] = None
_active_solve_id: str = ""
_active_solve_model: str = ""

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


def _verify_model_clipboard(model_name: str) -> bool:
    expected = f"MODEL ACTIVE: {model_name}"
    try:
        actual = (pyperclip.paste() or "").strip()
    except Exception as e:
        log_telemetry("model_clipboard_verify", {"expected": expected, "ok": False, "error": str(e)})
        return False
    ok = actual == expected
    log_telemetry(
        "model_clipboard_verify",
        {"expected": expected, "actual_sample": actual[:120], "ok": ok},
    )
    return ok


def _announce_model_active(model_name: str) -> bool:
    line = f"MODEL ACTIVE: {model_name}"
    if not safe_clipboard_write(line):
        log_telemetry("model_active_clipboard_error", {"model": model_name})
    set_status(line)
    return _verify_model_clipboard(model_name)


def _model_name_matches(requested_model: str, response_model: str) -> bool:
    req = str(requested_model or "").strip().lower()
    got = str(response_model or "").strip().lower()
    if not req or not got:
        # Do not hard-fail when response metadata is missing.
        return True
    # Accept exact model or provider suffix variants of the requested model only.
    return got == req or got.startswith(req + "-")


def _probe_model_runtime(model_name: str, call_model: Optional[str] = None, require_match: bool = True) -> tuple[bool, str]:
    cfg = get_config()
    api_key = resolve_api_key(cfg)
    if not api_key:
        return False, "missing API key"

    timeout = int(cfg.get("request_timeout", 25))
    probe_timeout = max(5, min(timeout, 12))
    probe_model = str(call_model or model_name).strip() or str(model_name)
    client: Optional[OpenAI] = None
    try:
        client = OpenAI(api_key=api_key, max_retries=0)
        resp = client.responses.create(
            model=probe_model,
            input=[{"role": "user", "content": [{"type": "input_text", "text": "ok"}]}],
            max_output_tokens=16,
            timeout=probe_timeout,
        )
        response_model = str(getattr(resp, "model", "") or "")
        if require_match and not _model_name_matches(model_name, response_model):
            reason = f"probe model mismatch expected '{model_name}' got '{response_model or probe_model}'"
            log_telemetry(
                "model_probe_failed",
                {
                    "requested_model": model_name,
                    "called_model": probe_model,
                    "response_model": response_model,
                    "error": reason,
                },
            )
            return False, reason
        # Best-effort telemetry to prove a token-using call hit the requested model.
        log_telemetry(
            "model_probe_ok",
            {
                "requested_model": model_name,
                "called_model": probe_model,
                "response_model": response_model,
            },
        )
        return True, ""
    except Exception as e:
        reason = str(e) or "probe failed"
        log_telemetry("model_probe_failed", {"requested_model": model_name, "error": reason})
        return False, reason
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _persist_config_changes(changes: Dict[str, object], source: str) -> Optional[Dict[str, object]]:
    try:
        return update_config_values(changes)
    except Exception as e:
        log_telemetry("config_persist_error", {"source": source, "error": str(e), "keys": sorted(list(changes.keys()))})
        return None


def _register_active_solve(client: OpenAI, cancel_event: threading.Event, solve_id: str, model_name: str) -> None:
    global _active_solve_client, _active_solve_cancel_event, _active_solve_id, _active_solve_model
    with _active_solve_state_lock:
        _active_solve_client = client
        _active_solve_cancel_event = cancel_event
        _active_solve_id = str(solve_id or "")
        _active_solve_model = str(model_name or "")
    log_telemetry("solve_active_registered", {"solve_id": solve_id, "model": model_name})


def _clear_active_solve(solve_id: Optional[str] = None) -> None:
    global _active_solve_client, _active_solve_cancel_event, _active_solve_id, _active_solve_model
    cleared = False
    with _active_solve_state_lock:
        if solve_id and _active_solve_id and solve_id != _active_solve_id:
            return
        if _active_solve_client is not None or _active_solve_cancel_event is not None:
            cleared = True
        _active_solve_client = None
        _active_solve_cancel_event = None
        _active_solve_id = ""
        _active_solve_model = ""
    if cleared:
        log_telemetry("solve_active_cleared", {"solve_id": solve_id or ""})


def _cancel_active_solve(reason: str) -> bool:
    with _active_solve_state_lock:
        cancel_event = _active_solve_cancel_event
        client = _active_solve_client
        solve_id = _active_solve_id
        model_name = _active_solve_model
        if cancel_event is None:
            return False
        if cancel_event.is_set():
            return False
        cancel_event.set()
    try:
        if client is not None:
            client.close()
    except Exception as e:
        log_telemetry("solve_cancel_close_error", {"solve_id": solve_id, "reason": reason, "error": str(e)})
    log_telemetry("solve_cancel_requested", {"solve_id": solve_id, "model": model_name, "reason": reason})
    return True


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

        if old_model != new_model:
            _cancel_active_solve(f"model_switch_hotkey_preprobe:{old_model}->{new_model}")

        ok_probe, reason = _probe_model_runtime(new_model)
        if not ok_probe:
            set_status(f"MODEL CHANGE FAILED: {reason}")
            return

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
        old_model = _active_model_name(cfg)
        target_model = str(model_name or "").strip()
        if not target_model:
            set_status("MODEL CHANGE FAILED: empty model")
            return
        if target_model not in models:
            set_status(f"MODEL CHANGE FAILED: unknown model '{target_model}'")
            return

        if old_model != target_model:
            _cancel_active_solve(f"model_switch_{source}_preprobe:{old_model}->{target_model}")

        ok_probe, reason = _probe_model_runtime(target_model)
        if not ok_probe:
            set_status(f"MODEL CHANGE FAILED: {reason}")
            return

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


def _is_ref_combo_active() -> bool:
    if not _ref_combo_keys:
        return False
    return _ref_combo_keys.issubset(_keys_down)


def _launch_star_worker_atomic() -> None:
    global _ref_toggle_in_progress
    try:
        star_worker()
    finally:
        if _TRAY_ICON is not None:
            _refresh_tray_menu(_TRAY_ICON)
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
        log_telemetry("solve_skip_busy", {"reason": "solve_in_progress"})
        set_status("Solve skipped: previous request still running.")
        return
    solve_id = f"solve-{uuid.uuid4().hex[:10]}"
    cancel_event = threading.Event()
    client: Optional[OpenAI] = None
    try:
        cfg = get_config()
        api_key = resolve_api_key(cfg)
        if not api_key:
            set_status("Missing API key (config.json or OPENAI_API_KEY).")
            return

        model_name = _active_model_name(cfg)
        client = OpenAI(api_key=api_key, max_retries=0)
        _register_active_solve(client, cancel_event, solve_id, model_name)
        log_telemetry("solve_worker_start", {"solve_id": solve_id, "model": model_name})
        raw_clip, _ = safe_clipboard_read()
        if isinstance(raw_clip, Image.Image):
            img = normalize_image_for_api(raw_clip, cfg)
            solve_pipeline(client, img, cancel_event=cancel_event, request_id=solve_id)
            return

        try:
            text = (pyperclip.paste() or "").strip()
        except Exception:
            text = ""

        if text:
            solve_pipeline(client, text, cancel_event=cancel_event, request_id=solve_id)
        else:
            set_status("No image or text found on clipboard.")
    except Exception as e:
        log_telemetry("worker_crash", {"solve_id": solve_id, "error": str(e)})
        set_status(f"Worker error: {e}")
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        _clear_active_solve(solve_id)
        _solve_lock.release()


def star_worker() -> None:
    if not _star_lock.acquire(blocking=False):
        return
    client: Optional[OpenAI] = None
    try:
        cfg = get_config()
        api_key = resolve_api_key(cfg)
        if not api_key:
            set_status("Missing API key; STAR unavailable.")
            return
        client = OpenAI(api_key=api_key, max_retries=0)
        toggle_star_worker(client)
    except Exception as e:
        log_telemetry("star_worker_crash", {"error": str(e)})
        set_status(f"STAR error: {e}")
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
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

    if not KEYBOARD_AVAILABLE:
        if announce:
            set_status("keyboard module not installed. Hotkeys disabled.")
        return False

    _unregister_hotkeys()
    try:
        # Bind fixed hotkeys from source; no runtime config-based overrides.
        run_hk = RUN_HOTKEY
        quit_hk = QUIT_HOTKEY
        star_hk = REF_TOGGLE_HOTKEY
        cycle_hk = CYCLE_MODEL_HOTKEY

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
    def _toggle_and_refresh():
        before_state = _is_ref_active_session()
        try:
            star_worker()
        finally:
            after_state = _is_ref_active_session()
            if after_state != before_state:
                # Explicit state feedback requested for menu-triggered REF toggles.
                set_status("REF ON" if after_state else "REF OFF")
            if _TRAY_ICON is not None:
                _refresh_tray_menu(_TRAY_ICON)

    threading.Thread(target=_toggle_and_refresh, daemon=True).start()


def _on_tray_select_model(icon, _item, model_name: str):
    _set_model_from_ui(icon, model_name, source="tray")


def _on_tray_refresh_model_list(icon, _item):
    cfg = reload_config()
    model_name = _active_model_name(cfg)
    _announce_model_active(model_name)
    _refresh_tray_menu(icon)


def _on_tray_auto_model_placeholder(_icon, _item):
    # Placeholder slot for future dynamic model routing.
    set_status("AUTO routing placeholder")


def _is_model_checked(model_name: str) -> bool:
    return _active_model_name() == str(model_name)


def _is_ref_active_session() -> bool:
    try:
        return bool(load_starred_meta().get("reference_active", False))
    except Exception as e:
        log_telemetry("ref_state_read_error", {"error": str(e)})
        return False


def _make_model_select_action(model_name: str):
    def _action(icon, menu_item):
        _on_tray_select_model(icon, menu_item, model_name)

    return _action


def _build_tray_menu():
    cfg = get_config()
    models = _normalize_available_models(cfg)
    ref_active = _is_ref_active_session()
    ref_label = "REF ON" if ref_active else "REF OFF"

    model_items = [item("AUTO", _on_tray_auto_model_placeholder)]
    model_items.extend([
        item(
            m,
            _make_model_select_action(m),
            checked=lambda *_args, model_name=m: _is_model_checked(model_name),
            radio=True,
        )
        for m in models
    ])
    model_items.append(item("Refresh Model List", _on_tray_refresh_model_list))

    return pystray.Menu(
        item("Solve Now", _on_tray_solve_now),
        item(ref_label, _on_tray_star_toggle, default=True),
        item("Model", pystray.Menu(*model_items)),
        # No Quit menu item: close is handled by right-click tray policy.
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


def _close_icon_only(icon) -> None:
    # Close app without mutating REF state for tray click-close behavior.
    STOP_EVENT.set()
    _unregister_hotkeys()
    try:
        icon.stop()
    except Exception:
        pass


def _install_tray_click_policy(icon) -> None:
    # Windows backend only: middle-click opens menu, left/right clicks close app.
    try:
        from pystray._util import win32 as tray_win32
    except Exception:
        return

    WM_MBUTTONUP = 0x0208
    # Bind the original backend handler from the class so left-click can still open the menu.
    orig_notify = icon.__class__._on_notify.__get__(icon, icon.__class__)
    if orig_notify is None:
        return

    def _custom_on_notify(wparam, lparam):
        if lparam == WM_MBUTTONUP:
            # Middle-click is the only menu-open action.
            return orig_notify(wparam, tray_win32.WM_RBUTTONUP)
        if lparam == tray_win32.WM_RBUTTONUP:
            # Right-click closes app without clearing REF state.
            _close_icon_only(icon)
            return
        if lparam == tray_win32.WM_LBUTTONUP:
            # Left-click also closes app without clearing REF state.
            _close_icon_only(icon)
            return
        return orig_notify(wparam, lparam)

    try:
        icon._on_notify = _custom_on_notify  # type: ignore[attr-defined]
        handlers = getattr(icon, "_message_handlers", None)
        if isinstance(handlers, dict):
            handlers[tray_win32.WM_NOTIFY] = _custom_on_notify
    except Exception as e:
        log_telemetry("tray_click_policy_error", {"error": str(e)})


def on_quit(icon, _item):
    clear_reference_state(source="exit", status_message="REF CLEARED ON EXIT")
    STOP_EVENT.set()
    _unregister_hotkeys()
    try:
        icon.stop()
    except Exception:
        pass


def main():
    global _TRAY_ICON
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
    _TRAY_ICON = icon
    _install_tray_click_policy(icon)

    set_app_icon(icon)
    clear_reference_state(source="startup", status_message="REF CLEARED ON STARTUP")
    set_reference_active(False)

    setup_hotkeys(icon)
    _announce_model_active(_active_model_name(cfg))
    log_telemetry("startup_model", {"model": _active_model_name(cfg)})
    icon.run()


if __name__ == "__main__":
    main()
