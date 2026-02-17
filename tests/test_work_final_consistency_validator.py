import unittest

import llm_pipeline


class WorkFinalConsistencyValidatorTests(unittest.TestCase):
    def test_open_marker_with_inclusive_bracket_is_mismatch(self):
        evidence = {
            "left_endpoint": {"x": "-2", "y": "0", "marker": "open"},
            "right_endpoint": {"x": "4", "y": "-5", "marker": "closed"},
            "asymptotes": [],
            "discontinuities": [],
            "scale": {"x_tick": "1", "y_tick": "1"},
            "confidence": 0.9,
        }
        work = "Domain: (-2, 4]"
        final = "Domain: [-2, 4]"

        mismatches = llm_pipeline._validate_work_final_consistency(evidence, work, final)

        self.assertTrue(any(m["mismatch_type"] == "endpoint_inclusion_conflict" for m in mismatches))

    def test_closed_marker_with_exclusive_bracket_is_mismatch(self):
        evidence = {
            "left_endpoint": {"x": "-2", "y": "0", "marker": "closed"},
            "right_endpoint": {"x": "4", "y": "-5", "marker": "open"},
            "asymptotes": [],
            "discontinuities": [],
            "scale": {"x_tick": "1", "y_tick": "1"},
            "confidence": 0.85,
        }
        work = "Domain: [-2, 4)"
        final = "Domain: (-2, 4)"

        mismatches = llm_pipeline._validate_work_final_consistency(evidence, work, final)

        self.assertTrue(any(m["mismatch_type"] == "endpoint_inclusion_conflict" and m["side"] == "left" for m in mismatches))

    def test_arrow_with_bounded_interval_is_mismatch(self):
        evidence = {
            "left_endpoint": {"x": "unclear", "y": "unclear", "marker": "arrow"},
            "right_endpoint": {"x": "4", "y": "-5", "marker": "closed"},
            "asymptotes": [],
            "discontinuities": [],
            "scale": {"x_tick": "1", "y_tick": "1"},
            "confidence": 0.7,
        }
        mismatches = llm_pipeline._validate_work_final_consistency(evidence, "Domain: (-inf, 4]", "Domain: [0, 4]")

        self.assertTrue(any(m["mismatch_type"] == "arrow_bound_conflict" for m in mismatches))

    def test_asymptote_included_in_final_domain_is_mismatch(self):
        evidence = {
            "left_endpoint": {"x": "-3", "y": "0", "marker": "open"},
            "right_endpoint": {"x": "3", "y": "0", "marker": "open"},
            "asymptotes": ["x=2"],
            "discontinuities": [],
            "scale": {"x_tick": "1", "y_tick": "1"},
            "confidence": 0.88,
        }
        mismatches = llm_pipeline._validate_work_final_consistency(evidence, "Domain: (-3, 3)", "Domain: (-3, 3)")

        self.assertTrue(any(m["mismatch_type"] == "asymptote_inclusion_conflict" for m in mismatches))

    def test_interval_disagreement_between_work_and_final_is_mismatch(self):
        evidence = {
            "left_endpoint": {"x": "-2", "y": "0", "marker": "closed"},
            "right_endpoint": {"x": "4", "y": "-5", "marker": "open"},
            "asymptotes": [],
            "discontinuities": [],
            "scale": {"x_tick": "1", "y_tick": "1"},
            "confidence": 0.95,
        }
        work = "Domain: [-2, 4)\nRange: (-5, 4]"
        final = "Domain: (-2, 4)\nRange: (-5, 4]"

        mismatches = llm_pipeline._validate_work_final_consistency(evidence, work, final)

        self.assertTrue(any(m["mismatch_type"] == "interval_disagreement_domain" for m in mismatches))


if __name__ == "__main__":
    unittest.main()
