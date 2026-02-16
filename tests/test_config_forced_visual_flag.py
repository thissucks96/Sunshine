import unittest

import config


class ConfigForcedVisualFlagTests(unittest.TestCase):
    def test_forced_visual_extraction_flag_defaults_false(self):
        normalized = config._normalize_config({})  # pylint: disable=protected-access
        self.assertIn("ENABLE_FORCED_VISUAL_EXTRACTION", normalized)
        self.assertFalse(bool(normalized.get("ENABLE_FORCED_VISUAL_EXTRACTION")))


if __name__ == "__main__":
    unittest.main()
