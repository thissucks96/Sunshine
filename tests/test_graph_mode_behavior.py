import tempfile
import time
import unittest
from unittest.mock import patch

from PIL import Image

import llm_pipeline


_VALID_GRAPH_EVIDENCE = (
    "GRAPH_EVIDENCE:\n"
    "  LEFT_ENDPOINT: x=-2, y=0, marker=closed\n"
    "  RIGHT_ENDPOINT: x=4, y=-5, marker=open\n"
    "  ASYMPTOTES: none\n"
    "  DISCONTINUITIES: none\n"
    "  SCALE: x_tick=1, y_tick=1\n"
    "  CONFIDENCE: 0.90\n"
)


class GraphModeBehaviorTests(unittest.TestCase):
    def test_set_graph_mode_on_off_updates_meta(self):
        with tempfile.TemporaryDirectory() as td, patch.object(llm_pipeline, "app_home_dir", return_value=td):
            meta = llm_pipeline.load_starred_meta()
            self.assertFalse(bool(meta.get("graph_mode", False)))

            turned_on = llm_pipeline.set_graph_mode(True)
            self.assertTrue(turned_on)
            meta_on = llm_pipeline.load_starred_meta()
            self.assertTrue(bool(meta_on.get("graph_mode", False)))

            turned_off = llm_pipeline.set_graph_mode(False)
            self.assertFalse(turned_off)
            meta_off = llm_pipeline.load_starred_meta()
            self.assertFalse(bool(meta_off.get("graph_mode", False)))
            self.assertIsNone(meta_off.get("graph_evidence"))
            self.assertEqual(int(meta_off.get("last_primed_ts", 0)), 0)

    def test_graph_mode_prime_runs_extraction_and_caches_evidence(self):
        cfg = {
            "model": "gpt-4o-mini",
            "reference_summary_model": "gpt-4o-mini",
            "classify_timeout": 8,
            "ocr_timeout": 12,
            "max_image_side": 4096,
            "max_image_pixels": 16_000_000,
        }
        graph_img = Image.new("RGB", (16, 16), "white")

        with tempfile.TemporaryDirectory() as td, patch.object(
            llm_pipeline, "app_home_dir", return_value=td
        ), patch.object(
            llm_pipeline, "get_config", return_value=cfg
        ), patch.object(
            llm_pipeline, "safe_clipboard_read", return_value=(graph_img, None)
        ), patch.object(
            llm_pipeline, "_summarize_visual_reference", return_value="graph panel reference"
        ), patch.object(
            llm_pipeline, "extract_graph_evidence", return_value=_VALID_GRAPH_EVIDENCE
        ) as mock_extract, patch.object(
            llm_pipeline, "set_status", return_value=None
        ) as mock_set_status:
            meta = llm_pipeline.load_starred_meta()
            meta["graph_mode"] = True
            llm_pipeline.save_starred_meta(meta)

            llm_pipeline.toggle_star_worker(client=object())
            updated = llm_pipeline.load_starred_meta()
            self.assertTrue(mock_set_status.called)
            self.assertEqual(mock_extract.call_args.kwargs.get("model_name"), "gpt-5.2")

        self.assertTrue(bool(updated.get("reference_active")))
        self.assertEqual(updated.get("reference_type"), llm_pipeline.REFERENCE_TYPE_IMG)
        self.assertEqual(updated.get("graph_evidence"), _VALID_GRAPH_EVIDENCE.strip())
        self.assertGreater(int(updated.get("last_primed_ts", 0)), 0)
        self.assertTrue(int(updated.get("last_primed_ts", 0)) <= int(time.time()))

    def test_build_solve_payload_injects_cached_graph_evidence_when_valid(self):
        with patch.object(llm_pipeline, "get_config", return_value={"ENABLE_FORCED_VISUAL_EXTRACTION": False}):
            payload = llm_pipeline._build_solve_payload(
                input_obj="Find the domain and range.",
                reference_active=False,
                reference_type=None,
                reference_text="",
                reference_img_b64="",
                graph_mode=True,
                graph_evidence_text=_VALID_GRAPH_EVIDENCE,
                enable_graph_evidence_parsing=False,
            )
        first = payload[1]["content"][0]
        self.assertEqual(first.get("type"), "input_text")
        self.assertIn("GRAPH MODE CACHED EVIDENCE", first.get("text", ""))

    def test_build_solve_payload_skips_cached_graph_evidence_when_invalid_or_absent(self):
        with patch.object(llm_pipeline, "get_config", return_value={"ENABLE_FORCED_VISUAL_EXTRACTION": False}):
            payload_invalid = llm_pipeline._build_solve_payload(
                input_obj="Find domain and range.",
                reference_active=False,
                reference_type=None,
                reference_text="",
                reference_img_b64="",
                graph_mode=True,
                graph_evidence_text="INVALID_GRAPH",
                enable_graph_evidence_parsing=False,
            )
            payload_absent = llm_pipeline._build_solve_payload(
                input_obj="Find domain and range.",
                reference_active=False,
                reference_type=None,
                reference_text="",
                reference_img_b64="",
                graph_mode=True,
                graph_evidence_text=None,
                enable_graph_evidence_parsing=False,
            )

        texts_invalid = [p.get("text", "") for p in payload_invalid[1]["content"] if p.get("type") == "input_text"]
        texts_absent = [p.get("text", "") for p in payload_absent[1]["content"] if p.get("type") == "input_text"]
        self.assertFalse(any("GRAPH MODE CACHED EVIDENCE" in t for t in texts_invalid))
        self.assertFalse(any("GRAPH MODE CACHED EVIDENCE" in t for t in texts_absent))

    def test_auto_graph_identifier_routes_ref_prime_to_graph_extraction_when_confident(self):
        cfg = {
            "model": "gpt-4o-mini",
            "reference_summary_model": "gpt-4o-mini",
            "ENABLE_AUTO_GRAPH_DETECT_REF_PRIME": True,
            "classify_timeout": 8,
            "ocr_timeout": 12,
            "max_image_side": 4096,
            "max_image_pixels": 16_000_000,
        }
        graph_img = Image.new("RGB", (16, 16), "white")

        with tempfile.TemporaryDirectory() as td, patch.object(
            llm_pipeline, "app_home_dir", return_value=td
        ), patch.object(
            llm_pipeline, "get_config", return_value=cfg
        ), patch.object(
            llm_pipeline, "safe_clipboard_read", return_value=(graph_img, None)
        ), patch.object(
            llm_pipeline, "detect_graph_presence", return_value="YES"
        ) as mock_detect, patch.object(
            llm_pipeline, "_summarize_visual_reference", return_value="graph panel reference"
        ), patch.object(
            llm_pipeline, "extract_graph_evidence", return_value=_VALID_GRAPH_EVIDENCE
        ) as mock_extract, patch.object(
            llm_pipeline, "set_status", return_value=None
        ):
            llm_pipeline.toggle_star_worker(client=object())
            updated = llm_pipeline.load_starred_meta()

        self.assertTrue(str(mock_detect.call_args.kwargs.get("image_path", "")).endswith(".png"))
        self.assertEqual(mock_extract.call_args.kwargs.get("model_name"), "gpt-5.2")
        self.assertEqual(updated.get("reference_type"), llm_pipeline.REFERENCE_TYPE_IMG)
        self.assertEqual(updated.get("graph_evidence"), _VALID_GRAPH_EVIDENCE.strip())

    def test_auto_graph_identifier_falls_back_to_normal_ref_when_no(self):
        cfg = {
            "model": "gpt-4o-mini",
            "reference_summary_model": "gpt-4o-mini",
            "ENABLE_AUTO_GRAPH_DETECT_REF_PRIME": True,
            "classify_timeout": 8,
            "ocr_timeout": 12,
            "max_image_side": 4096,
            "max_image_pixels": 16_000_000,
        }
        graph_img = Image.new("RGB", (16, 16), "white")

        with tempfile.TemporaryDirectory() as td, patch.object(
            llm_pipeline, "app_home_dir", return_value=td
        ), patch.object(
            llm_pipeline, "get_config", return_value=cfg
        ), patch.object(
            llm_pipeline, "safe_clipboard_read", return_value=(graph_img, None)
        ), patch.object(
            llm_pipeline, "detect_graph_presence", return_value="NO"
        ), patch.object(
            llm_pipeline, "_responses_text", return_value="VISUAL"
        ), patch.object(
            llm_pipeline, "_summarize_visual_reference", return_value="visual reference"
        ), patch.object(
            llm_pipeline, "extract_graph_evidence", return_value=_VALID_GRAPH_EVIDENCE
        ) as mock_extract, patch.object(
            llm_pipeline, "set_status", return_value=None
        ):
            llm_pipeline.toggle_star_worker(client=object())
            updated = llm_pipeline.load_starred_meta()

        self.assertIsNone(updated.get("graph_evidence"))
        self.assertEqual(updated.get("reference_type"), llm_pipeline.REFERENCE_TYPE_IMG)
        self.assertFalse(mock_extract.called)

    def test_detect_graph_presence_uses_fixed_model_and_binary_output(self):
        cfg = {"max_image_side": 4096, "max_image_pixels": 16_000_000}
        with tempfile.TemporaryDirectory() as td:
            img_path = f"{td}\\probe.png"
            Image.new("RGB", (8, 8), "white").save(img_path, format="PNG")
            with patch.object(
                llm_pipeline, "get_config", return_value=cfg
            ), patch.object(
                llm_pipeline, "_responses_text", return_value="YES"
            ) as mock_resp:
                result = llm_pipeline.detect_graph_presence(
                    image_path=img_path,
                    client=object(),
                    timeout=8,
                )
        self.assertEqual(result, "YES")
        self.assertEqual(mock_resp.call_args.kwargs.get("model_name"), "gpt-4o-mini")


if __name__ == "__main__":
    unittest.main()
