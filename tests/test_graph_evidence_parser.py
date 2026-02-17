import unittest
from unittest.mock import patch

import llm_pipeline


class GraphEvidenceParserTests(unittest.TestCase):
    def test_extract_graph_evidence_block_valid(self):
        text = (
            "Problem\n"
            "WORK:\n"
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=-2, y=0, marker=closed\n"
            "  RIGHT_ENDPOINT: x=4, y=-5, marker=open\n"
            "  ASYMPTOTES: none\n"
            "  DISCONTINUITIES: none\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "  CONFIDENCE: 0.91\n"
            "Observed markers confirm endpoint inclusion/exclusion.\n"
            "FINAL ANSWER:\n"
            "Domain: [-2, 4)\n"
            "Range: (-5, 4]\n"
        )

        evidence = llm_pipeline._extract_graph_evidence_block(text)

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["left_endpoint"]["marker"], "closed")
        self.assertEqual(evidence["right_endpoint"]["marker"], "open")
        self.assertEqual(evidence["asymptotes"], [])
        self.assertEqual(evidence["discontinuities"], [])
        self.assertEqual(evidence["scale"]["x_tick"], "1")
        self.assertAlmostEqual(float(evidence["confidence"]), 0.91)

    def test_extract_graph_evidence_block_malformed_endpoint(self):
        text = (
            "WORK:\n"
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=-2, y=0\n"
            "  RIGHT_ENDPOINT: x=4, y=-5, marker=open\n"
            "  ASYMPTOTES: none\n"
            "  DISCONTINUITIES: none\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "  CONFIDENCE: 0.91\n"
            "FINAL ANSWER: Domain: [-2, 4)\n"
        )

        with patch.object(llm_pipeline, "log_telemetry") as mocked_log:
            evidence = llm_pipeline._extract_graph_evidence_block(text)

        self.assertIsNone(evidence)
        self.assertTrue(any(call.args[0] == "graph_evidence_parse_fail" for call in mocked_log.call_args_list))

    def test_extract_graph_evidence_block_missing_required_field(self):
        text = (
            "WORK:\n"
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=-2, y=0, marker=closed\n"
            "  RIGHT_ENDPOINT: x=4, y=-5, marker=open\n"
            "  ASYMPTOTES: none\n"
            "  DISCONTINUITIES: none\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "FINAL ANSWER: Domain: [-2, 4)\n"
        )

        with patch.object(llm_pipeline, "log_telemetry") as mocked_log:
            evidence = llm_pipeline._extract_graph_evidence_block(text)

        self.assertIsNone(evidence)
        self.assertTrue(any(call.args[0] == "graph_evidence_parse_fail" for call in mocked_log.call_args_list))

    def test_extract_graph_evidence_block_respects_2000_char_safety_bound(self):
        text = (
            "WORK:\n"
            "GRAPH_EVIDENCE:\n"
            + ("A" * 2100)
            + "\nLEFT_ENDPOINT: x=-2, y=0, marker=closed\n"
            + "RIGHT_ENDPOINT: x=4, y=-5, marker=open\n"
            + "ASYMPTOTES: none\n"
            + "DISCONTINUITIES: none\n"
            + "SCALE: x_tick=1, y_tick=1\n"
            + "CONFIDENCE: 0.9\n"
        )

        with patch.object(llm_pipeline, "log_telemetry"):
            evidence = llm_pipeline._extract_graph_evidence_block(text)

        self.assertIsNone(evidence)

    def test_extract_graph_evidence_block_accepts_optional_fields(self):
        text = (
            "WORK:\n"
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=-2, y=0, marker=closed\n"
            "  RIGHT_ENDPOINT: x=4, y=-5, marker=open\n"
            "  ASYMPTOTES: y=2\n"
            "  DISCONTINUITIES: none\n"
            "  INTERCEPTS: (x=2, y=0); (x=0, y=-4)\n"
            "  KEY_POINTS: (x=5, y=13)\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "  CONFIDENCE: 0.88\n"
            "FINAL ANSWER:\n"
            "Domain: (-∞, ∞)\n"
        )

        evidence = llm_pipeline._extract_graph_evidence_block(text)

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["intercepts"], ["(x=2, y=0)", "(x=0, y=-4)"])
        self.assertEqual(evidence["key_points"], ["(x=5, y=13)"])
        self.assertEqual(evidence["asymptotes"], ["y=2"])

    def test_extract_graph_evidence_block_tolerates_unknown_fields(self):
        text = (
            "WORK:\n"
            "GRAPH_EVIDENCE:\n"
            "  LEFT_ENDPOINT: x=-2, y=0, marker=closed\n"
            "  UNKNOWN_FLAG: keep_this_ignored\n"
            "  RIGHT_ENDPOINT: x=4, y=-5, marker=open\n"
            "  ASYMPTOTES: none\n"
            "  DISCONTINUITIES: none\n"
            "  SCALE: x_tick=1, y_tick=1\n"
            "  CONFIDENCE: 0.88\n"
            "FINAL ANSWER:\n"
            "Domain: (-∞, ∞)\n"
        )

        evidence = llm_pipeline._extract_graph_evidence_block(text)

        self.assertIsNotNone(evidence)
        self.assertEqual(evidence["left_endpoint"]["x"], "-2")
        self.assertEqual(evidence["right_endpoint"]["x"], "4")


if __name__ == "__main__":
    unittest.main()
