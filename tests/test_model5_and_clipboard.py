import tempfile
import unittest
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

import llm_pipeline
import utils


class _FakeResponses:
    def __init__(self) -> None:
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text="ok", output=[])


class _FakeClient:
    def __init__(self) -> None:
        self.responses = _FakeResponses()


class _FakeNotifyIcon:
    HAS_NOTIFICATION = True

    def __init__(self) -> None:
        self.calls = []

    def notify(self, msg, title=None):
        self.calls.append((msg, title))


class ModelAndClipboardTests(unittest.TestCase):
    def test_responses_text_omits_temperature_for_gpt5_family_and_raises_token_floor(self):
        client = _FakeClient()
        out = llm_pipeline._responses_text(
            client=client,
            model_name="gpt-5-mini",
            input_payload=[{"role": "user", "content": [{"type": "input_text", "text": "ok"}]}],
            timeout=20,
            temperature=0.7,
            max_output_tokens=32,
            flow_name="test",
            request_id="test-gpt5-family",
        )
        self.assertEqual(out, "ok")
        self.assertEqual(len(client.responses.calls), 1)
        sent = client.responses.calls[0]
        self.assertNotIn("temperature", sent)
        self.assertEqual(int(sent.get("max_output_tokens", 0)), 128)
        self.assertNotIn("reasoning", sent)

    def test_responses_text_keeps_temperature_for_non_gpt5(self):
        client = _FakeClient()
        out = llm_pipeline._responses_text(
            client=client,
            model_name="gpt-4o-mini",
            input_payload=[{"role": "user", "content": [{"type": "input_text", "text": "ok"}]}],
            timeout=20,
            temperature=0.2,
            max_output_tokens=48,
            flow_name="test",
            request_id="test-gpt52",
        )
        self.assertEqual(out, "ok")
        self.assertEqual(len(client.responses.calls), 1)
        sent = client.responses.calls[0]
        self.assertIn("temperature", sent)
        self.assertAlmostEqual(float(sent.get("temperature", 0.0)), 0.2)
        self.assertEqual(int(sent.get("max_output_tokens", 0)), 48)
        self.assertNotIn("reasoning", sent)

    def test_visual_ref_prefix_is_in_final_clipboard_entry(self):
        writes = []

        def _fake_clipboard_write(text: str, attempts: int = 4, delay_sec: float = 0.08) -> bool:
            writes.append(text)
            return True

        def _fake_responses_text(**_kwargs):
            return "Problem\nWORK:\nstep\nFINAL ANSWER: 4"

        with tempfile.TemporaryDirectory() as td:
            image_path = f"{td}/ref.png"
            Image.new("RGB", (8, 8), "white").save(image_path, format="PNG")

            cfg = {
                "retries": 0,
                "request_timeout": 20,
                "model": "gpt-4o-mini",
                "temperature": 0.0,
                "max_output_tokens": 2200,
                "clipboard_history_settle_sec": 0.0,
                "notify_on_complete": False,
                "max_image_side": 4096,
                "max_image_pixels": 16_000_000,
            }
            meta = {
                "reference_active": True,
                "reference_type": llm_pipeline.REFERENCE_TYPE_IMG,
                "text_path": "",
                "image_path": image_path,
                "reference_summary": "sample visual ref",
            }

            with patch.object(llm_pipeline, "get_config", return_value=cfg), patch.object(
                llm_pipeline, "load_starred_meta", return_value=meta
            ), patch.object(llm_pipeline, "_responses_text", side_effect=_fake_responses_text), patch.object(
                llm_pipeline, "_clipboard_write_retry", side_effect=_fake_clipboard_write
            ), patch.object(
                llm_pipeline, "mark_prompt_success", return_value=None
            ), patch.object(
                llm_pipeline, "set_status", return_value=None
            ), patch.object(
                llm_pipeline, "set_reference_active", return_value=None
            ), patch.object(
                llm_pipeline.time, "sleep", return_value=None
            ):
                llm_pipeline.solve_pipeline(client=object(), input_obj="2 + 2 = ?")

        self.assertGreaterEqual(len(writes), 2)
        self.assertTrue(writes[0].startswith("* REF IMG: sample visual ref\n"))
        self.assertTrue(writes[-1].startswith("4\n"))
        self.assertTrue(writes[-1].endswith("* REF IMG: sample visual ref"))

    def test_status_mirrors_structured_clipboard_payload(self):
        unique_message = "status mirror unit test"
        fake_icon = _FakeNotifyIcon()
        writes = []

        def _fake_copy(text: str, max_attempts: int = 3, delay: float = 0.05) -> bool:
            writes.append(text)
            return True

        with patch.object(utils, "_APP_ICON", fake_icon), patch.object(
            utils, "safe_clipboard_write", side_effect=_fake_copy
        ), patch.object(
            utils, "set_error_active", return_value=None
        ), patch.object(
            utils, "log_telemetry", return_value=None
        ), patch.object(
            utils,
            "get_config",
            return_value={
                "status_notify_enabled": True,
                "status_notify_max_chars": 72,
                "status_notify_clear_sec": 0.0,
                "status_notify_title": "SNS",
            },
        ), patch.object(
            utils, "_LAST_STATUS_MESSAGE", ""
        ), patch.object(
            utils, "_LAST_STATUS_TS", 0.0
        ):
            utils.set_status(unique_message)

        self.assertEqual(len(fake_icon.calls), 1)
        self.assertEqual(len(writes), 1)
        payload = writes[0]
        self.assertIn("NOTIFICATION_TYPE: STATUS", payload)
        self.assertIn("SOURCE: set_status", payload)
        self.assertIn(f"MESSAGE: {unique_message}", payload)

    def test_duplicate_status_still_notifies_and_rewrites_clipboard(self):
        fake_icon = _FakeNotifyIcon()
        writes = []

        def _fake_copy(text: str, max_attempts: int = 3, delay: float = 0.05) -> bool:
            writes.append(text)
            return True

        with patch.object(utils, "_APP_ICON", fake_icon), patch.object(
            utils, "safe_clipboard_write", side_effect=_fake_copy
        ), patch.object(
            utils, "set_error_active", return_value=None
        ), patch.object(
            utils, "log_telemetry", return_value=None
        ), patch.object(
            utils,
            "get_config",
            return_value={
                "status_notify_enabled": True,
                "status_notify_max_chars": 72,
                "status_notify_clear_sec": 0.0,
                "status_notify_title": "SNS",
            },
        ), patch.object(
            utils, "_LAST_STATUS_MESSAGE", ""
        ), patch.object(
            utils, "_LAST_STATUS_TS", 0.0
        ):
            utils.set_status("duplicate status")
            utils.set_status("duplicate status")

        self.assertEqual(len(fake_icon.calls), 2)
        self.assertEqual(len(writes), 2)

    def test_status_uses_clipboard_when_window_prompts_disabled(self):
        fake_icon = _FakeNotifyIcon()
        writes = []

        def _fake_copy(text: str, max_attempts: int = 3, delay: float = 0.05) -> bool:
            writes.append(text)
            return True

        with patch.object(utils, "_APP_ICON", fake_icon), patch.object(
            utils, "safe_clipboard_write", side_effect=_fake_copy
        ), patch.object(
            utils, "set_error_active", return_value=None
        ), patch.object(
            utils, "log_telemetry", return_value=None
        ), patch.object(
            utils,
            "get_config",
            return_value={
                "status_notify_enabled": True,
                "status_notify_max_chars": 72,
                "status_notify_clear_sec": 0.0,
                "status_notify_title": "SNS",
                "window_prompts_enabled": False,
                "clipboard_prompts_enabled": True,
            },
        ), patch.object(
            utils, "_LAST_STATUS_MESSAGE", ""
        ), patch.object(
            utils, "_LAST_STATUS_TS", 0.0
        ):
            utils.set_status("window prompts off")

        self.assertEqual(len(fake_icon.calls), 0)
        self.assertEqual(len(writes), 1)

    def test_status_disables_clipboard_mirroring_when_clipboard_prompts_off(self):
        fake_icon = _FakeNotifyIcon()
        writes = []

        def _fake_copy(text: str, max_attempts: int = 3, delay: float = 0.05) -> bool:
            writes.append(text)
            return True

        with patch.object(utils, "_APP_ICON", fake_icon), patch.object(
            utils, "safe_clipboard_write", side_effect=_fake_copy
        ), patch.object(
            utils, "set_error_active", return_value=None
        ), patch.object(
            utils, "log_telemetry", return_value=None
        ), patch.object(
            utils,
            "get_config",
            return_value={
                "status_notify_enabled": True,
                "status_notify_max_chars": 72,
                "status_notify_clear_sec": 0.0,
                "status_notify_title": "SNS",
                "window_prompts_enabled": True,
                "clipboard_prompts_enabled": False,
            },
        ), patch.object(
            utils, "_LAST_STATUS_MESSAGE", ""
        ), patch.object(
            utils, "_LAST_STATUS_TS", 0.0
        ):
            utils.set_status("clipboard prompts off")

        self.assertEqual(len(fake_icon.calls), 1)
        self.assertEqual(len(writes), 0)

    def test_compound_inequality_output_is_formatted_for_small_ui(self):
        raw = (
            "Solve each of the given compound inequalities. Enter your answers using interval notation.\n\n"
            "-7x + 4 < 18 or -3x - 5 < -32\n"
            "WORK:\n"
            "-7x + 4 < 18 => -7x < 14 => x > -2.\n"
            "-3x - 5 < -32 => -3x < -27 => x > 9.\n"
            "Union: x > -2 or x > 9 => x > -2.\n"
            "FINAL ANSWER:\n"
            "(-2, ∞)"
        )
        formatted = llm_pipeline._maybe_format_compound_inequality_ui(raw)
        self.assertIn("Solve -7x + 4 < 18:", formatted)
        self.assertIn("Subtract 4 from both sides", formatted)
        self.assertIn("Divide by -7 (flip inequality)", formatted)
        self.assertIn("OR means union: x > -2 or x > 9 = x > -2", formatted)
        self.assertIn("Question Context:", formatted)
        self.assertIn("FINAL ANSWER:\n(-2, ∞)", formatted)
        self.assertEqual("(-2, ∞)", llm_pipeline._extract_final_answer_text(formatted))

    def test_compound_inequality_multiline_work_is_formatted_for_small_ui(self):
        raw = (
            "Solve each of the given compound inequalities. Enter your answers using interval notation.\n\n"
            "-7x + 4 < 18 or -3x - 5 < -32\n"
            "WORK:\n"
            "-7x + 4 < 18\n"
            "-7x < 14\n"
            "x > -2\n\n"
            "-3x - 5 < -32\n"
            "-3x < -27\n"
            "x > 9\n\n"
            "Union: x > -2 (since x > 9 is subset of x > -2)\n"
            "FINAL ANSWER:\n"
            "(-2, ∞)"
        )
        formatted = llm_pipeline._maybe_format_compound_inequality_ui(raw)
        self.assertIn("Solve -7x + 4 < 18:", formatted)
        self.assertIn("Subtract 4 from both sides", formatted)
        self.assertIn("Solve -3x - 5 < -32:", formatted)
        self.assertIn("Add 5 to both sides", formatted)
        self.assertIn("OR means union: x > -2 or x > 9 = x > -2", formatted)
        self.assertIn("Question Context:", formatted)
        self.assertEqual("(-2, ∞)", llm_pipeline._extract_final_answer_text(formatted))

    def test_cancelled_between_clipboard_writes_skips_final_write(self):
        writes = []
        statuses = []
        cancel = Event()

        def _fake_clipboard_write(text: str, attempts: int = 4, delay_sec: float = 0.08) -> bool:
            writes.append(text)
            if len(writes) == 1:
                cancel.set()
            return True

        def _fake_responses_text(**_kwargs):
            return "Problem\nWORK:\nstep\nFINAL ANSWER: 4"

        cfg = {
            "retries": 0,
            "request_timeout": 20,
            "model": "gpt-4o-mini",
            "temperature": 0.0,
            "max_output_tokens": 2200,
            "clipboard_history_settle_sec": 0.6,
            "notify_on_complete": False,
            "max_image_side": 4096,
            "max_image_pixels": 16_000_000,
        }
        meta = {
            "reference_active": False,
            "reference_type": None,
            "text_path": "",
            "image_path": "",
            "reference_summary": "",
        }

        with patch.object(llm_pipeline, "get_config", return_value=cfg), patch.object(
            llm_pipeline, "load_starred_meta", return_value=meta
        ), patch.object(llm_pipeline, "_responses_text", side_effect=_fake_responses_text), patch.object(
            llm_pipeline, "_clipboard_write_retry", side_effect=_fake_clipboard_write
        ), patch.object(
            llm_pipeline, "mark_prompt_success", return_value=None
        ), patch.object(
            llm_pipeline, "set_status", side_effect=statuses.append
        ), patch.object(
            llm_pipeline, "set_reference_active", return_value=None
        ), patch.object(
            llm_pipeline.time, "sleep", return_value=None
        ):
            llm_pipeline.solve_pipeline(
                client=object(),
                input_obj="2 + 2 = ?",
                cancel_event=cancel,
                request_id="cancel-write-race",
            )

        self.assertEqual(len(writes), 1)
        self.assertIn("Solve canceled: model switched.", statuses)

    def test_gpt5_family_respects_configured_solve_retries(self):
        statuses = []
        cfg = {
            "retries": 3,
            "request_timeout": 20,
            "model": "gpt-5-mini",
            "temperature": 0.0,
            "max_output_tokens": 2200,
            "clipboard_history_settle_sec": 0.6,
            "notify_on_complete": False,
            "max_image_side": 4096,
            "max_image_pixels": 16_000_000,
        }
        meta = {
            "reference_active": False,
            "reference_type": None,
            "text_path": "",
            "image_path": "",
            "reference_summary": "",
        }

        with patch.object(llm_pipeline, "get_config", return_value=cfg), patch.object(
            llm_pipeline, "load_starred_meta", return_value=meta
        ), patch.object(llm_pipeline, "_responses_text", side_effect=Exception("boom")) as mock_call, patch.object(
            llm_pipeline, "set_status", side_effect=statuses.append
        ), patch.object(
            llm_pipeline, "set_reference_active", return_value=None
        ), patch.object(
            llm_pipeline, "mark_prompt_success", return_value=None
        ):
            llm_pipeline.solve_pipeline(client=object(), input_obj="2 + 2 = ?")

        self.assertEqual(mock_call.call_count, 4)
        self.assertTrue(any("Solve failed: boom" in s for s in statuses))


if __name__ == "__main__":
    unittest.main()
