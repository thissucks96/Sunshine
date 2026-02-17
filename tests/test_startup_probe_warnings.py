import unittest
from unittest.mock import patch

import main


class StartupProbeWarningsTests(unittest.TestCase):
    def test_startup_warns_when_selected_model_is_offline(self):
        cfg = {"model": "gpt-4o"}
        with patch.object(main, "_active_model_name", return_value="gpt-4o"), patch.object(
            main, "_probe_model_runtime", side_effect=[(False, "offline"), (True, "")]
        ), patch.object(main, "set_status") as mock_status:
            main._run_startup_model_probes(cfg)

        messages = [args[0] for args, _ in mock_status.call_args_list]
        self.assertIn("Selected model [gpt-4o] is offline; please select another.", messages)

    def test_startup_warns_when_graph_extraction_model_is_offline(self):
        cfg = {"model": "gpt-4o"}
        with patch.object(main, "_active_model_name", return_value="gpt-4o"), patch.object(
            main, "_probe_model_runtime", side_effect=[(True, ""), (False, "offline")]
        ), patch.object(main, "set_status") as mock_status:
            main._run_startup_model_probes(cfg)

        messages = [args[0] for args, _ in mock_status.call_args_list]
        self.assertIn("5.2 is offline; High-precision Graph Extraction is disabled.", messages)


if __name__ == "__main__":
    unittest.main()
