import unittest
from unittest.mock import patch

import llm_pipeline


class SolvePipelineGraphEvidenceIntegrationTests(unittest.TestCase):
    def test_prompt_injection_is_flag_gated(self):
        payload_off = llm_pipeline._build_solve_payload(
            input_obj="Find domain and range.",
            reference_active=False,
            reference_type=None,
            reference_text="",
            reference_img_b64="",
            enable_graph_evidence_parsing=False,
        )
        payload_on = llm_pipeline._build_solve_payload(
            input_obj="Find domain and range.",
            reference_active=False,
            reference_type=None,
            reference_text="",
            reference_img_b64="",
            enable_graph_evidence_parsing=True,
        )

        sys_off = payload_off[0]["content"][0]["text"]
        sys_on = payload_on[0]["content"][0]["text"]

        self.assertNotIn("GRAPH_EVIDENCE:", sys_off)
        self.assertIn("GRAPH_EVIDENCE:", sys_on)

    def test_retry_guard_receives_original_candidate_text(self):
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
            "ENABLE_GRAPH_EVIDENCE_PARSING": True,
            "ENABLE_CONSISTENCY_WARNINGS": False,
            "ENABLE_CONSISTENCY_BLOCKING": False,
        }
        meta = {
            "reference_active": False,
            "reference_type": None,
            "text_path": "",
            "image_path": "",
            "reference_summary": "",
        }
        writes = []
        seen = {}

        candidate = (
            "Prompt\n"
            "WORK:\n"
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=-2, y=0, marker=closed\n"
            "  RIGHT_ENDPOINT: x=4, y=-5, marker=open\n"
            "  ASYMPTOTES: none\n"
            "  DISCONTINUITIES: none\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "  CONFIDENCE: 0.90\n"
            "Domain: [-2, 4)\n"
            "Range: (-5, 4]\n"
            "FINAL ANSWER:\n"
            "Domain: [-2, 4)\n"
            "Range: (-5, 4]\n"
        )

        def _fake_retry_guard(_input_obj, model_text):
            seen["candidate"] = model_text
            return False

        with patch.object(llm_pipeline, "get_config", return_value=cfg), patch.object(
            llm_pipeline, "load_starred_meta", return_value=meta
        ), patch.object(
            llm_pipeline, "_responses_text", return_value=candidate
        ), patch.object(
            llm_pipeline, "_needs_graph_domain_range_retry", side_effect=_fake_retry_guard
        ), patch.object(
            llm_pipeline, "_clipboard_write_retry", side_effect=lambda text, attempts=4, delay_sec=0.08: writes.append(text) or True
        ), patch.object(
            llm_pipeline, "mark_prompt_success", return_value=None
        ), patch.object(
            llm_pipeline, "set_status", return_value=None
        ), patch.object(
            llm_pipeline, "set_reference_active", return_value=None
        ), patch.object(
            llm_pipeline.time, "sleep", return_value=None
        ):
            llm_pipeline.solve_pipeline(client=object(), input_obj="graph request")

        self.assertIn("GRAPH_EVIDENCE:", seen.get("candidate", ""))
        self.assertTrue(any("GRAPH_EVIDENCE:" in w for w in writes))

    def test_warning_telemetry_is_noop_when_flags_false(self):
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
            "ENABLE_GRAPH_EVIDENCE_PARSING": False,
            "ENABLE_CONSISTENCY_WARNINGS": False,
            "ENABLE_CONSISTENCY_BLOCKING": False,
        }
        meta = {
            "reference_active": False,
            "reference_type": None,
            "text_path": "",
            "image_path": "",
            "reference_summary": "",
        }
        events = []
        candidate = (
            "WORK:\n"
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=-2, y=0, marker=open\n"
            "  RIGHT_ENDPOINT: x=4, y=-5, marker=closed\n"
            "  ASYMPTOTES: none\n"
            "  DISCONTINUITIES: none\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "  CONFIDENCE: 0.95\n"
            "Domain: (-2, 4]\n"
            "FINAL ANSWER:\n"
            "Domain: [-2, 4]\n"
        )

        def _capture_event(name, data):
            events.append((name, data))

        with patch.object(llm_pipeline, "get_config", return_value=cfg), patch.object(
            llm_pipeline, "load_starred_meta", return_value=meta
        ), patch.object(
            llm_pipeline, "_responses_text", return_value=candidate
        ), patch.object(
            llm_pipeline, "_needs_graph_domain_range_retry", return_value=False
        ), patch.object(
            llm_pipeline, "_clipboard_write_retry", return_value=True
        ), patch.object(
            llm_pipeline, "mark_prompt_success", return_value=None
        ), patch.object(
            llm_pipeline, "set_status", return_value=None
        ), patch.object(
            llm_pipeline, "set_reference_active", return_value=None
        ), patch.object(
            llm_pipeline.time, "sleep", return_value=None
        ), patch.object(
            llm_pipeline, "log_telemetry", side_effect=_capture_event
        ):
            llm_pipeline.solve_pipeline(client=object(), input_obj="graph request")

        self.assertFalse(any(name == "validator_mismatch_warning" for name, _ in events))

    def test_warning_telemetry_emits_when_enabled_and_mismatch_found(self):
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
            "ENABLE_GRAPH_EVIDENCE_PARSING": True,
            "ENABLE_CONSISTENCY_WARNINGS": True,
            "ENABLE_CONSISTENCY_BLOCKING": False,
        }
        meta = {
            "reference_active": False,
            "reference_type": None,
            "text_path": "",
            "image_path": "",
            "reference_summary": "",
        }
        events = []
        candidate = (
            "WORK:\n"
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=-2, y=0, marker=open\n"
            "  RIGHT_ENDPOINT: x=4, y=-5, marker=closed\n"
            "  ASYMPTOTES: none\n"
            "  DISCONTINUITIES: none\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "  CONFIDENCE: 0.95\n"
            "Domain: (-2, 4]\n"
            "FINAL ANSWER:\n"
            "Domain: [-2, 4]\n"
        )

        def _capture_event(name, data):
            events.append((name, data))

        with patch.object(llm_pipeline, "get_config", return_value=cfg), patch.object(
            llm_pipeline, "load_starred_meta", return_value=meta
        ), patch.object(
            llm_pipeline, "_responses_text", return_value=candidate
        ), patch.object(
            llm_pipeline, "_needs_graph_domain_range_retry", return_value=False
        ), patch.object(
            llm_pipeline, "_clipboard_write_retry", return_value=True
        ), patch.object(
            llm_pipeline, "mark_prompt_success", return_value=None
        ), patch.object(
            llm_pipeline, "set_status", return_value=None
        ), patch.object(
            llm_pipeline, "set_reference_active", return_value=None
        ), patch.object(
            llm_pipeline.time, "sleep", return_value=None
        ), patch.object(
            llm_pipeline, "log_telemetry", side_effect=_capture_event
        ):
            llm_pipeline.solve_pipeline(client=object(), input_obj="graph request")

        self.assertTrue(any(name == "validator_mismatch_warning" for name, _ in events))


if __name__ == "__main__":
    unittest.main()
