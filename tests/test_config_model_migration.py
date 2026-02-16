import unittest

import config


class ConfigModelMigrationTests(unittest.TestCase):
    def test_exact_gpt5_is_migrated_to_gpt52(self):
        normalized = config._normalize_config(  # pylint: disable=protected-access
            {
                "model": "gpt-5",
                "available_models": ["gpt-4o-mini", "gpt-5", "gpt-5.2"],
            }
        )
        self.assertEqual(normalized.get("model"), "gpt-5.2")
        self.assertNotIn("gpt-5", normalized.get("available_models", []))
        self.assertIn("gpt-5.2", normalized.get("available_models", []))


if __name__ == "__main__":
    unittest.main()
