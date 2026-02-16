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


class ModelAndClipboardTests(unittest.TestCase):
    def test_responses_text_omits_temperature_for_gpt5_and_raises_token_floor(self):
        client = _FakeClient()
        out = llm_pipeline._responses_text(
            client=client,
            model_name="gpt-5",
            input_payload=[{"role": "user", "content": [{"type": "input_text", "text": "ok"}]}],
            timeout=20,
            temperature=0.7,
            max_output_tokens=32,
            flow_name="test",
            request_id="test-gpt5",
        )
        self.assertEqual(out, "ok")
        self.assertEqual(len(client.responses.calls), 1)
        sent = client.responses.calls[0]
        self.assertNotIn("temperature", sent)
        self.assertEqual(int(sent.get("max_output_tokens", 0)), 128)
        self.assertEqual(((sent.get("reasoning") or {}).get("effort")), "low")

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
        self.assertTrue(writes[-1].startswith("* REF IMG: sample visual ref\n"))

    def test_status_always_mirrors_to_clipboard(self):
        unique_message = "status mirror unit test"
        with patch.object(utils, "safe_clipboard_write", return_value=True) as mock_copy, patch.object(
            utils, "show_notification", return_value=None
        ), patch.object(
            utils, "set_error_active", return_value=None
        ), patch.object(
            utils, "log_telemetry", return_value=None
        ), patch.object(
            utils, "get_config", return_value={}
        ):
            utils.set_status(unique_message)

        mock_copy.assert_called_with(unique_message)

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

    def test_gpt5_uses_single_solve_attempt_even_if_retries_configured(self):
        statuses = []
        cfg = {
            "retries": 3,
            "request_timeout": 20,
            "model": "gpt-5",
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

        self.assertEqual(mock_call.call_count, 1)
        self.assertTrue(any("Solve failed: boom" in s for s in statuses))


if __name__ == "__main__":
    unittest.main()
