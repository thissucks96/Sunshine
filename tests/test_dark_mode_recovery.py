import unittest

from PIL import Image

import llm_pipeline


class DarkModeRecoveryTests(unittest.TestCase):
    def test_dark_mode_detection_by_filename(self):
        img = Image.new("RGB", (32, 32), color=(240, 240, 240))
        self.assertTrue(llm_pipeline._is_dark_mode_image("graph is present dark mode (2).png", img))

    def test_dark_mode_detection_by_luma(self):
        img = Image.new("RGB", (64, 64), color=(20, 20, 20))
        for x in range(8, 56):
            img.putpixel((x, 32), (240, 240, 240))
        self.assertTrue(llm_pipeline._is_dark_mode_image("plain_name.png", img))

    def test_parse_and_rerank_candidates_prefers_integer_consensus(self):
        raw = (
            "KEY_POINT_CANDIDATES: "
            "(x=1.98, y=-1.98); (x=2.02, y=-2.02); (x=2.01, y=-2.01)"
        )
        candidates = llm_pipeline._parse_candidate_xy_pairs(raw)
        reranked = llm_pipeline._rerank_dark_mode_key_point(candidates)
        self.assertIsNotNone(reranked)
        self.assertAlmostEqual(2.0, reranked["x"])
        self.assertAlmostEqual(-2.0, reranked["y"])

    def test_snap_value_threshold(self):
        self.assertEqual(2.0, llm_pipeline._snap_value(2.1, threshold=0.15))
        self.assertEqual(-2.0, llm_pipeline._snap_value(-1.9, threshold=0.15))
        self.assertEqual(2.2, llm_pipeline._snap_value(2.2, threshold=0.15))

    def test_upsert_graph_evidence_field_line_inserts_before_scale(self):
        text = (
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=unclear, y=unclear, marker=arrow\n"
            "  RIGHT_ENDPOINT: x=unclear, y=unclear, marker=arrow\n"
            "  ASYMPTOTES: y=2\n"
            "  DISCONTINUITIES: none\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "  CONFIDENCE: 0.70\n"
        )
        updated = llm_pipeline._upsert_graph_evidence_field_line(
            text, "KEY_POINTS", "(x=2, y=-2)"
        )
        self.assertIn("KEY_POINTS: (x=2, y=-2)", updated)
        self.assertLess(updated.find("KEY_POINTS"), updated.find("SCALE"))

    def test_upsert_graph_evidence_field_line_replaces_existing(self):
        text = (
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=unclear, y=unclear, marker=arrow\n"
            "  RIGHT_ENDPOINT: x=unclear, y=unclear, marker=arrow\n"
            "  ASYMPTOTES: y=2\n"
            "  DISCONTINUITIES: none\n"
            "  KEY_POINTS: none\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "  CONFIDENCE: 0.70\n"
        )
        updated = llm_pipeline._upsert_graph_evidence_field_line(
            text, "KEY_POINTS", "(x=2, y=-2)"
        )
        self.assertIn("KEY_POINTS: (x=2, y=-2)", updated)
        self.assertNotIn("KEY_POINTS: none", updated)


if __name__ == "__main__":
    unittest.main()
