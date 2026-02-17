import unittest

import config


class ConfigForcedVisualFlagTests(unittest.TestCase):
    def test_forced_visual_extraction_flag_defaults_false(self):
        normalized = config._normalize_config({})  # pylint: disable=protected-access
        self.assertIn("ENABLE_FORCED_VISUAL_EXTRACTION", normalized)
        self.assertFalse(bool(normalized.get("ENABLE_FORCED_VISUAL_EXTRACTION")))

    def test_auto_graph_detect_ref_prime_flag_defaults_false(self):
        normalized = config._normalize_config({})  # pylint: disable=protected-access
        self.assertIn("ENABLE_AUTO_GRAPH_DETECT_REF_PRIME", normalized)
        self.assertFalse(bool(normalized.get("ENABLE_AUTO_GRAPH_DETECT_REF_PRIME")))

    def test_graph_identifier_min_confidence_is_clamped(self):
        normalized = config._normalize_config(  # pylint: disable=protected-access
            {"graph_identifier_min_confidence": 2.0}
        )
        self.assertEqual(normalized.get("graph_identifier_min_confidence"), 1.0)


if __name__ == "__main__":
    unittest.main()
